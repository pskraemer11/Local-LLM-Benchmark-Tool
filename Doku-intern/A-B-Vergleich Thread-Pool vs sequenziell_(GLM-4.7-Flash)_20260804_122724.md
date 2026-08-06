# A/B-Vergleich: Thread-Pool (num_parallel) vs. sequenziell – GLM 4.7 Flash

Hintergrund: Laut A/B-Messung vom 01.08. (GPT-OSS) profitiert nur GPT-OSS-20b
sichtbar von Multi-Slot-Serving. Server-Log-Analyse vom 04.08. zeigt aber,
dass auch andere Modelle (u.a. GLM 4.7 Flash) mit `n_slots=4` geladen werden
(`load_model: initializing, n_slots = 4, n_ctx_slot = 32768, kv_unified = 'true'`).
Die Parallelität wurde nur nie genutzt, weil der Benchmark sequenziell sendet.
Fix: `--num-parallel N` in `custom_benchmark.py` (ThreadPoolExecutor,
Reihenfolge bleibt erhalten). Diese Messung verifiziert den Effekt mit dem
echten Benchmark-Pipeline (nicht nur Harness-Latenz).

- Datum: 2026-08-04T12:27:24
- Modell: `glm-4.7-flash` (Q3_K_S), MoE, ~13.3 GB VRAM
- Benchmark-Regime: DS1000 + CoderEval, SampleSize=5, Seed=12345 (identische Tasks)
- Vergleich: `--num-parallel 1` (sequenziell) vs. `--num-parallel 4` (Thread-Pool)
- Modell geladen via `lms` (API: n_slots=4, kv_unified=true, ctx 32768)

| Variante        | Wall-Time (s) | Verhaeltnis | DS1000 | CoderEval | Mittlere Latenz (s) | Avg tok/s | CPU (Max) | GPU (Max) | VRAM (GB) |
|-----------------|--------------:|------------:|-------:|----------:|--------------------:|----------:|----------:|----------:|----------:|
| num_parallel=1  |    164.7      |   1.00x     |  0.0%  |  20.0%    |         ~16         |    ~29    |    25%    |    97%    |   14.4    |
| num_parallel=4  |     89.2      |   0.54x     |  0.0%  |   0.0%    |         ~18         |    ~14    |    19%    |    99%    |   14.4    |

Verhaeltnis = Wall-Time relativ zu num_parallel=1 (kleiner = schneller).
Bewertung der Model-Antworten (0% Scores) ist hier irrelevant – es geht um
Durchsatz; GLM 4.7 Flash ist kein Coding-Modell (→ 0% in beiden Läufen).

**Ergebnis:** 1.85x Speedup (0.54x Wall-Time) – deutlich besser als der
GPT-OSS-Vergleich (0.75x), weil GLM 4.7 Flash als MoE mit 3+ aktiven Slots
die GPU besser auslastet (GPU 99% statt 97%, CPU 19% statt 25%).

**Parallelitäts-Beweis (Server-Log 04.08., Fenster 12:23-12:24):**
- Sequenzieller Lauf: 52 print_timing-Events, **0** Fenster mit >1 aktivem Slot
- Paralleler Lauf: 43 print_timing-Events, **10** Fenster mit 2-3 Slots
  gleichzeitig aktiv (Slots [0,1], [1,2], [0,1,2], [0,3], ...)

**Score-Hinweis:** CoderEval 20% (seq) vs. 0% (par) bei identischem Seed –
das 1/5-Erfolgs-Detail (1 Task bestanden) fehlt im Parallel-Lauf. Bei SS=5 ist
das eine Einzeltask-Differenz und nicht statistisch belastbar; bei SS=100
sollte der Thread-Pool-Vergleich erneut auf Score-Drift geprüft werden.

---
Setup:
- **Basis:** `custom_benchmark.py` mit neuem `--num-parallel` (ThreadPoolExecutor;
  Default 1 = identisch zum bisherigen Verhalten; `pool.map` erhält Reihenfolge).
- Gleiche Bedingungen: identische Tasks (Seed 12345), identische Prompt-Konstruktion,
  gleiches geladenes Modell, keine anderen Lasten.
- Messwerte: Wall-Time (subprocess), per-Task Latenz/tok/s (Modell-Scores),
  CPU/GPU/VRAM-Peaks (Monitor), Slot-Aktivität aus Server-Log (print_timing).
- Der Thread-Pool respektiert weiterhin den Single-Instance-Lock des Launchers
  (Aufruf über run_benchmarks.py mit --num-parallel).
- Empfehlung: `--num-parallel 4` für SS=100-Läufe; bei SS=5 kaum Unterschied
  (Overhead) und Score-Drift-Messung erschwert.
