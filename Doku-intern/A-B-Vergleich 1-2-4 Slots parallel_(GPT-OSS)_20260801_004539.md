# Parallel-Slots A/B/C-Messung

bisher liefert nur das Modell GPT-OSS-20b tatsächlich einen Lauf mit n=4 Slots paralle. 
Fragestellung: gibt es einen Zeitvorteil bei der Benchmark-Messung?

> UPDATE 2026-08-04: Server-Log-Analyse zeigt, dass auch andere Modelle
> (GLM 4.7 Flash u.a.) mit `n_slots=4` geladen werden – die Parallelität wurde
> nur nie genutzt, weil der Benchmark sequenziell sendet. Fix: `--num-parallel`
> in custom_benchmark.py (Thread-Pool). Messung: GLM 4.7 Flash erzielt 1.85x
> Speedup (0.54x Wall-Time) – siehe `A-B-Vergleich Thread-Pool vs sequenziell_(GLM-4.7-Flash)_20260804_122724.md`.

Daher direkter A/B/C-Vergleich: 1/2/4 Slots parallel (in LMS GUI: 'max concurrent prediction')

- Datum: 2026-08-01T00:45:39
- Modell: `openai/gpt-oss-20b`
- Benchmark-Regime: `ds1000` (SampleSize=20)
- Slots: [1, 2, 4] | Wiederholungen: 2 (AB/BA-Reihenfolge)

| Slots | Wall-Time (s) | Aggregat tok/s | Verhaeltnis | Mittlere Latenz (s) | Median (s) | Max RAM (GB) |
|-------|--------------:|---------------:|------------:|--------------------:|-----------:|-------------:|
|   1   |    692.8      |       30.8     |   1.00x     |         40.2        |    42.9    |    13.1      |
|   2   |    666.3      |       40.7     |   0.96x     |         65.9        |    93.4    |    13.9      |
|   4   |    517.6      |       46.3     |   0.75x     |         99.5        |   102.6    |    14.3      |

Verhaeltnis = Wall-Time relativ zu Slots=1 (kleiner = schneller).
AB/BA-Reihenfolge neutralisiert mögliche Thermik-Drift des GPUs.

---
Setup komplett:

**A/B-Harness** (`src/tools/parallel_ab.py`):
- Gleiche Bedingungen wie der echte Lauf: echte DS1000-Tasks, identische Prompt-Konstruktion (`_make_datascience_prompt`), `temperature=0.0`, `max_tokens=2048`, gpt-oss-Reasoning-Params
- Slots 1/2/4 in **AB/BA-Reihenfolge** (2 Durchläufe, GPU-Thermik-Drift neutralisiert), SampleSize=20
- Messwerte: Wall-Time, Aggregat-Tok/s, mittlere/Median-Latenz, max. System-RAM (prüft auch, ob RAM bei K>1 explodiert)
- Respektiert den Single-Instance-Lock → läuft nie gegen den Benchmark-Lauf


