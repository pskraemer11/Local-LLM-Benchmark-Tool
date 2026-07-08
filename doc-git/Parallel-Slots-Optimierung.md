# Parallel Slots Optimierung (np) – LM Studio

## Problem

LM Studio setzt `Max Concurrent Predictions` (np/parallel) standardmäßig auf **4**.
Bei **sequentiellen Batch-Jobs** (z.B. Benchmarks, ein Request nach dem anderen)
werden dadurch unnötig Ressourcen verschwendet:

- KV-Cache für **4 parallele Slots** alloziert (3 ungenutzt)
- Slot-Switching per LRU zerstört Cache-Kontinuität
- Höherer VRAM-Druck → `cache size limit reached`-Evictions

## Erkenntnis

Für **sequentiell arbeitende Skripte** (ein `lms load` → N Requests → `unload`)
ist **np=1 optimal**. Die Messung am 08./09.07.2026 am selben Basis-Modell
(Qwen2.5 Coder 14B) zeigt:

| Merkmal | Q5_0 (np=4) | Q6_K (np=1) |
|---|---|---|
| Eval Speed | **~8–9.6 t/s** | **~12.8–13.4 t/s** |
| `cache size limit reached` | Ja (häufig) | Keine |
| LCP-Cache-Treffer (f_keep) | Slot-wechselnd | **0.52–0.94** |
| VRAM-Auslastung | Höher | Geringer (~3-4 GB weniger) |

> **Hinweis:** Q6_K ist rechenintensiver als Q5_0 – die gemessene
> Geschwindigkeitssteigerung ist **allein auf np=1** zurückzuführen.

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
- **LRU** (Least Recently Used): Falls kein passender Prefix gefunden wird,
  wird der am längsten ungenutzte Slot gewählt → Cache verloren.

### np=1 vs np=4

| Aspekt | np=4 | np=1 |
|---|---|---|
| Slot-Bestand | 4 Slots | 1 Slot |
| LCP-Treffer | Zufällig (je nach LRU-Rotation) | **Immer** (keine Alternative) |
| f_keep | Stark schwankend | 0.80–0.95 (stabil) |
| KV-Cache VRAM | 4× Grundbedarf | 1× Grundbedarf |

### Log-Beleg

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

## Empfehlung

1. **Für sequentielle Batch-Skripte:** np=1 in der GUI setzen
   (My Models → ⚙️ → Max Concurrent Predictions → 1)
2. **Für interaktiven Chat/parallele Nutzer:** np=4 (Default) belassen
3. **Projektweit:** np=1 als Default für alle Benchmark-Läufe

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
