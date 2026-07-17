# Parallel Slots Optimierung (np) – LM Studio

## Problem

LM Studio setzt `Max Concurrent Predictions` (np/parallel) standardmäßig auf **4**.
Bei **sequentiellen Batch-Jobs** (z.B. Benchmarks, ein Request nach dem anderen) hängt die optimale Einstellung von der *LLM-Architektur* und der *Art der Anfragen* ab.

## Kern-Erkenntnis: Dense vs MoE

| Architektur                      | Optimales np | Grund                                                            |
|----------------------------------|--------------|------------------------------------------------------------------|
| **Dense** (alle Parameter aktiv) | **np=1**     | LCP-Cache-Reuse spart Prompt-Tokens; GPU ist bereits ausgelastet |
| **MoE** (nur Subset aktiv)       | **np=4**     | LCP-Cache-Reuse nicht unterstützt; Batching füllt die GPU besser |

### Messung Dense: Qwen2.5 Coder 14B, zwei Quantisierungsvarianten (08./09.07.2026)

| Merkmal                     | Q5_0 (np=4)    | Q6_K (np=1)                |
|-----------------------------|----------------|----------------------------|
| Eval Speed                  | **~8–9.6 t/s** | **~12.8–13.4 t/s**         |
| `cache size limit reached`  | Ja (häufig)    | Keine                      |
| LCP-Cache-Treffer (f_keep)  | Slot-wechselnd | **0.52–0.94**              |
| VRAM-Auslastung             | Höher          | Geringer (~3-4 GB weniger) |

> **Hinweis:** Q6_K ist rechenintensiver als Q5_0 – die gemessene Geschwindigkeitssteigerung ist **allein auf np=1** zurückzuführen.

### Messung MoE: google_gemma-4-26b-a4b-it Q3_K_S (04./09.07.2026)

| Merkmal        | np=4 (04.07.)           | np=1 (09.07.)                              |
|----------------|-------------------------|--------------------------------------------|
| Eval Speed     | **~5.3 t/s**            | **~2.1 t/s**                               |
| Prompt Eval    | 21.8 t/s                | 98 t/s (LCP hilft prompt, aber nicht eval) |
| KV-Cache-Reuse | Nicht unterstützt (MoE) | Nicht unterstützt (MoE)                    |

np=4 ist **2.5× schneller** bei MoE, weil die GPU durch Batchen von 4 Tokens besser ausgelastet wird. 
LCP-Cache-Reuse entfällt bei MoE ohnehin.

## Mechanismus

### KV-Cache & Slots

LM Studio nutzt llama.cpp mit **Slot-basiertem KV-Cache**. Jeder Slot besitzt einen eigenen KV-Cache-Bereich. 
Bei np=N werden N Slots alloziert, auch wenn nur einer gleichzeitig aktiv ist.

**KV-Cache-VRAM (pro Slot):**
```
context_length × layers × KV_heads × head_dim × (bytes_K + bytes_V) / 1024³   (Ergebnis in GB)
```

**Gesamt-VRAM für KV-Cache = np × VRAM pro Slot**

Beispiel (24B Llama-Dense, ~64 Layer, 8 KV-Heads, head_dim=128, k_cache=q8_0=1B, v_cache=iq4_nl=0.5B):
- Pro Token: 64 × 8 × 128 × (1 + 0.5) = 98.304 Bytes ≈ **96 KB**
- Pro Slot bei 49K Kontext: 49.000 × 96 KB ≈ **4,7 GB**
- **np=4 → 18,8 GB** KV-Cache (vs. np=1 → 4,7 GB)

### Slot-Selection

Bei jedem Request wählt der Server einen Slot aus:
- **LCP-Similarity** (Longest Common Prefix): Der Prompt des vorherigen Requests wird mit dem aktuellen verglichen. 
  Bei Übereinstimmung wird der KV-Cache des Prefix wiederverwendet (`f_keep` = Anteil aus Cache).
  **Funktioniert nur bei Dense-Modellen** – MoE unterstützt kein Cache-Reuse.
- **LRU** (Least Recently Used): Falls kein passender Prefix gefunden wird, wird der am längsten ungenutzte Slot gewählt → Cache verloren.

### np=1 vs np=4 – Dense

| Aspekt        | np=4                            | np=1                          |
|---------------|---------------------------------|-------------------------------|
| Slot-Bestand  | 4 Slots                         | 1 Slot                        |
| LCP-Treffer   | Zufällig (je nach LRU-Rotation) | **Immer** (keine Alternative) |
| f_keep        | Stark schwankend                | 0.80–0.95 (stabil)            |
| KV-Cache VRAM | 4× Grundbedarf                  | 1× Grundbedarf                |

### np=1 vs np=4 – MoE

| Aspekt         | np=4                         | np=1              |
|----------------|------------------------------|-------------------|
| GPU-Auslastung | **Hoch** (4 Tokens parallel) | Niedrig (1 Token) |
| Cache-Reuse    | Entfällt (MoE)               | Entfällt (MoE)    |
| Eval Speed     | **~2-3× höher**              | Niedriger         |

## Spezialfall: Benchmarks (lm_eval, EvalPlus) – LCP=0

### Problem

lm_eval-Benchmarks (ARC-Challenge, HellaSwag, TruthfulQA, MATH-500, IFEval) arbeiten mit **Few-Shot-Prompts**:

```
Frage: Was ist 2+2?
Antwort: 4

Frage: Was ist 3+5?
Antwort: 8

Frage: <aktuelle Frage>
Antwort:
```

Jede Frage hat **andere Few-Shot-Beispiele** (werden zufällig aus dem Trainingsset gezogen oder rotiert). Der Prompt unterscheidet sich daher **ab dem ersten Zeichen**. 

**Konsequenz:**
- LCP zwischen Anfrage N und Anfrage N+1 = **0** (kein gemeinsames Präfix)
- **Kein Slot-Match** möglich
- Bei **jeder einzelnen Frage** wird der LRU-Slot evicted und der gesamte Prompt von Grund auf neu berechnet (Prefill)
- Alle N Slots werden durchrotiert, aber nie wiederverwendet

**np=4 vs np=1 bei Benchmark-Load:**

| Aspekt               | np=4                                   | np=1                     |
|----------------------|----------------------------------------|--------------------------|
| LCP-Treffer          | **0** (nie)                            | **0** (nie)              |
| Effektive Nutzung    | 1 Slot aktiv, 3 Slots ungenutzt        | 1 Slot aktiv             |
| KV-Cache VRAM        | **4× Grundbedarf** (3× Verschwendung)  | 1× Grundbedarf           |
| Progressive Slowdown | **Ja** – VRAM-Druck steigt mit der Zeit | Nein (minimaler Cache)   |
| Ergebnis             | Gleiche Geschwindigkeit wie np=1, aber höherer VRAM-Verbrauch | Gleiche Geschwindigkeit, minimaler VRAM |

### Progressive Verlangsamung

Bei np=4 und Benchmarks wurde ein signifikanter **progresiver Slowdown** beobachtet:
- Modell `bartowski/mistralai_magistral-small-2509` (24B Dense): Start **15 tok/s → Ende 5 tok/s**

**Ursache:**
1. Anfangs: KV-Cache fast leer, ~11,5 GB VRAM für Compute-Buffer → 15 tok/s
2. Mit jeder Frage wächst der Page-Table-basierte KV-Cache in den 4 Slots
3. Sobald der freie VRAM zur Neige geht, beginnt **Paging über PCIe** zu System-RAM (36× langsamer als GPU-RAM)
4. Gleichzeitig: Weniger VRAM für Compute-Buffer → kleinere Batches → niedrigerer Durchsatz
5. Ergebnis: **Drastischer Einbruch** der Token-Rate im Laufe eines Benchmarks

**np=2 mildert** den Effekt (halbiert KV-Cache), beseitigt ihn aber nicht bei langen Benchmarks.

## Empfehlung

### Allgemein

1. **Dense Modelle**: **np=1** – LCP-Cache-Reuse senkt Prompt-Overhead (außer bei Benchmarks, s.u.), GPU bereits ausgelastet
2. **MoE Modelle**: **np=4** – Batching nutzt GPU besser, kein Cache-Reuse zu verlieren
3. **Ausnahme ERNIE** (`ernie4_5-moe`): **np=1** – Shared-Expert-Architektur + heterogene Text/Vision-Experten verursachen ineffiziente CUDA-Kernel bei np=4
4. **Interaktiver Chat / parallele Nutzer:** np=4 (Default) belassen

### Für Benchmark-Load (sequentiell, diverse Prompts)

1. **Dense Modelle**: **np=1** – kein LCP-Vorteil bei Benchmarks, aber minimaler KV-Cache-VRAM
2. **MoE Modelle**: **np=2–4**, je nach verfügbarem VRAM – Batching-Vorteil bleibt, aber VRAM-Grenze beachten

### Context-Length in Abhängigkeit von np

KV-Cache-VRAM skaliert linear mit np:
```
VRAM_KV = np × context_length × (Kosten pro Token)
```

Daher muss die Context-Length bei höherem np **reduziert** werden. Faustregel:
```
sichere_context_length = np=1_context_length / np
```

Beispiel für 16 GB VRAM-GPU (Richtwerte, abhängig von Modellgröße und KV-Quantisierung):

| np  | Maximale Context Length (Richtwert) |
|-----|-------------------------------------|
| 1   | wie bisherige Tabelle (16k–262k)    |
| 2   | ~50 % der np=1-Werte                |
| 4   | ~25 % der np=1-Werte                |

## Automatische Konfiguration

Die JSON-Configs in `user-concrete-model-default-config` sind per Skript korrigiert: 
MoE-Modelle haben `numParallelSessions=4`, Dense-Modelle `=1`.

**Hinweis:** Die automatische Konfiguration berücksichtigt keine Benchmark-Spezialfälle.
Pro Modell kann `num_parallel` in der Registry (`model_registry.yaml`) überschrieben werden.

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
