# Parallel Slots Optimierung (np) – LM Studio

## Problem

LM Studio setzt `Max Concurrent Predictions` (np/parallel) standardmäßig auf **4**.
Bei **sequentiellen Batch-Jobs** (z.B. Benchmarks, ein Request nach dem anderen)
hängt die optimale Einstellung von der **Architektur** ab.

## Kern-Erkenntnis: Dense vs MoE

| Architektur | Optimales np | Grund |
|---|---|---|
| **Dense** (alle Parameter aktiv) | **np=1** | LCP-Cache-Reuse spart Prompt-Tokens; GPU ist bereits ausgelastet |
| **MoE** (nur Subset aktiv) | **np=4** | LCP-Cache-Reuse nicht unterstützt; Batching füllt die GPU besser |

### Messung Dense: Qwen2.5 Coder 14B (08./09.07.2026)

| Merkmal | Q5_0 (np=4) | Q6_K (np=1) |
|---|---|---|
| Eval Speed | **~8–9.6 t/s** | **~12.8–13.4 t/s** |
| `cache size limit reached` | Ja (häufig) | Keine |
| LCP-Cache-Treffer (f_keep) | Slot-wechselnd | **0.52–0.94** |
| VRAM-Auslastung | Höher | Geringer (~3-4 GB weniger) |

> **Hinweis:** Q6_K ist rechenintensiver als Q5_0 – die gemessene
> Geschwindigkeitssteigerung ist **allein auf np=1** zurückzuführen.

### Messung MoE: google_gemma-4-26b-a4b-it Q3_K_S (04./09.07.2026)

| Merkmal | np=4 (04.07.) | np=1 (09.07.) |
|---|---|---|
| Eval Speed | **~5.3 t/s** | **~2.1 t/s** |
| Prompt Eval | 21.8 t/s | 98 t/s (LCP hilft prompt, aber nicht eval) |
| KV-Cache-Reuse | Nicht unterstützt (MoE) | Nicht unterstützt (MoE) |

np=4 ist **2.5× schneller** bei MoE, weil die GPU durch Batchen von 4 Tokens
besser ausgelastet wird. LCP-Cache-Reuse entfällt bei MoE ohnehin.

## Mechanismus

### KV-Cache & Slots

LM Studio nutzt llama.cpp mit **Slot-basiertem KV-Cache**. Jeder Slot
besitzt einen eigenen KV-Cache-Bereich. Bei np=N werden N Slots alloziert,
auch wenn nur einer gleichzeitig aktiv ist.

### Slot-Selection

Bei jedem Request wählt der Server einen Slot aus:

- **LCP-Similarity** (Longest Common Prefix): Der Prompt des vorherigen
  Requests wird mit dem aktuellen verglichen. Bei Übereinstimmung wird
  der KV-Cache des Prefix wiederverwendet (`f_keep` = Anteil aus Cache).
  **Funktioniert nur bei Dense-Modellen** – MoE unterstützt kein Cache-Reuse.
- **LRU** (Least Recently Used): Falls kein passender Prefix gefunden wird,
  wird der am längsten ungenutzte Slot gewählt → Cache verloren.

### np=1 vs np=4 – Dense

| Aspekt | np=4 | np=1 |
|---|---|---|
| Slot-Bestand | 4 Slots | 1 Slot |
| LCP-Treffer | Zufällig (je nach LRU-Rotation) | **Immer** (keine Alternative) |
| f_keep | Stark schwankend | 0.80–0.95 (stabil) |
| KV-Cache VRAM | 4× Grundbedarf | 1× Grundbedarf |

### np=1 vs np=4 – MoE

| Aspekt | np=4 | np=1 |
|---|---|---|
| GPU-Auslastung | **Hoch** (4 Tokens parallel) | Niedrig (1 Token) |
| Cache-Reuse | Entfällt (MoE) | Entfällt (MoE) |
| Eval Speed | **~2-3× höher** | Niedriger |

### Log-Beleg Dense

**Mit np=1:** Ausschließlich LCP-Selection – der Prefix bleibt erhalten:

```
selected slot by LCP similarity, sim_best = 0.959 (> 0.100 thold), f_keep = 0.936
selected slot by LCP similarity, sim_best = 0.941 (> 0.100 thold), f_keep = 0.897
```

`f_keep = 0.936` bedeutet: 93,6 % der Prompt-Tokens wurden aus dem KV-Cache
übernommen – nur 6,4 % mussten neu prefilled werden.

**Mit np=4:** Häufig LRU-Selection (Slot-Wechsel):

```
selected slot by LRU, t_last = 337789914
```

Auch bei LCP-Treffern wird zwischen verschiedenen Slots (0,1,2,3)
gewechselt, was den nutzbaren Cache verkleinert.

### Log-Beleg MoE

```
slot print_timing: id 0 | eval time = 81194.31 ms / 174 tokens (2.14 t/s)   # np=1
slot print_timing: id 3 | eval time = 41573.83 ms / 220 tokens (5.29 t/s)   # np=4
```

## Empfehlung

1. **Dense Modelle** (Qwen, Llama, Mistral, Phi, Granite-4.1): **np=1**
   → LCP-Cache-Reuse senkt Prompt-Overhead, GPU bereits ausgelastet
2. **MoE Modelle** (Gemma-4, LFM, ERNIE, Qwen3-Coder-REAP, Mellum2,
   North-Mini-Code, GLM-4.7-Flash-REAP, DeepSeek-Coder-V2-Lite): **np=4**
   → Batching nutzt GPU besser, kein Cache-Reuse zu verlieren
3. **Interaktiver Chat / parallele Nutzer:** np=4 (Default) belassen

## Automatische Konfiguration

Die JSON-Configs in `user-concrete-model-default-config` sind per Skript
korrigiert: MoE-Modelle haben `numParallelSessions=4`, Dense-Modelle `=1`.
Die Erkennung erfolgt über das Feld `llm.load.numExperts` – ist es vorhanden,
gilt das Modell als MoE.

## Anhang: Fix für PowerShell-Logging

Das Batch-Skript `run_missing_benchmarks.ps1` zeigte kaum Log-Ausgabe,
weil Python bei Piped-Stdout blockpuffert (4K/8K).

**Fix:** Python mit `-u` (unbuffered) aufrufen:

```powershell
& $Python -u run_benchmarks_v12.py `
    --sample-size 100 `
    --seed 42 `
    --model $ModelArg `
    --benchmarks $BenchArg `
    2>&1 | Tee-Object -FilePath $LogFile -Append
```

Alternativ: `$env:PYTHONUNBUFFERED=1` vor dem Skriptstart setzen.
