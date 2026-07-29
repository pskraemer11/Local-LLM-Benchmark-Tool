## Review-Bericht 05.07.2026: Gemma-4-Benchmarks, Quant-Vergleiche & Infrastruktur-Fixes

### 1. Gemma-4-Läufe: Thinking vs. Non-Thinking

**Lauf 04.07. (mit `--thinking`):** 3/3 Modelle erfolgreich durchgelaufen.
Ergebnisse in der konsolidierten Tabelle (`konsolidiert_20260704_022948.md`):

| Modell                                      | Quant  | Overall | Coding |Knowledge| Math | Agentic| tok/s |
|---------------------------------------------|--------|---------|--------|---------|------|--------|-------|
| Gemma 4 26B A4B Instruct UD (unsloth)       | IQ3_S  |   55%   |   66%  |   76%   |  55% |   25%  |   14  |
| Gemma 4 26B A4B Instruct Q3_K_S (bartowski) | Q3_K_S |   37%   |   37%  |    4%   |   0% |   95%  |    1  |
| Gemma 4 19B A4B Instruct REAP I1            | IQ4_NL |   56%   |   70%  |   43%   |   0% |   98%  |   17  |

Auffälligkeiten:
- **Gemma 4 26B UD (IQ3_S)** bester Gemma-Overall (55%), exzellente Effizienz (24.4 %p/h, Rang 2)
- **Gemma 4 19B REAP** bester Agentic-Score (98%) und Coding (70%)
- **Gemma 4 Q3_K_S** fällt bei lm_eval komplett durch (ARC=0%, HellaSwag=0%, TruthfulQA=0%) – lm_eval hat Template-Probleme mit bartowski-Quant

**Lauf 05.07. (ohne `--thinking`):** Modell 1/5 (`google/gemma-4-26b-a4b-it`, unsloth IQ3_S) mit HTTP 500 abgestürzt (s.u.). Restliche 4 Modelle nicht gelaufen (Log abgebrochen).

### 2. HTTP-500-Crash: Ursache & Fix

**Ursache:** `C:\Users\pskra\.lmstudio\hub\models\google\gemma-4-26b-a4b-it\model.yaml` erzeugte ein virtuelles Modell `google/gemma-4-26b-a4b-it`, das mit der physischen Instanz `gemma-4-26b-a4b-it` (unsloth IQ3_S) kollidierte – beide referenzierten dieselbe GGUF-Datei. llama.cpp stürzte beim Inferenzversuch ab (HTTP 500 ohne "Running chat completion" im Server-Log).

**Fix:** Das gesamte Verzeichnis `hub/models/google/gemma-4-26b-a4b-it/` gelöscht. Das mradermacher-model.yaml bleibt, da kein Konflikt (virtuelles `mradermacher/qwen3-coder-reap-25b-a3b-i1` kollidiert mit keiner physischen Instanz).

**Konsequenz:** Der Non-Thinking-Lauf für Gemma-4-Modelle muss wiederholt werden. Statt `--model google/gemma-4-26b-a4b-it` den physischen Key `--model gemma-4-26b-a4b-it` (unsloth) bzw. `--model google_gemma-4-26b-a4b-it` (bartowski) verwenden.

### 3. Quant-Vergleiche (Bootstrap-CI)

**Qwen3 Coder REAP 25B A3B I1** (aus `quant_comparison.md`):

| Quant       | DS1000 |CoderEval| HEval+ | MBPP+ | ARC  |HellaSwag|TruthfulQA| MathQA | MMLU-Pro| Agentic | Overall  |
|-------------|--------|---------|--------|-------|------|---------|----------|--------|---------|---------|----------|
| IQ4_XS (UD) |   10%  |    75%  |   95%  |  71%  |  75% |   40%   |    50%   |   45%  |    46%  |   88%   |  *63.2%* |
| Q3_K_M      |   15%  |    75%  |   95%  |  79%  |  80% |   55%   |    50%   |   40%  |    58%  |   65%   |  *58.4%* |
| Q4_K_S      |   25%  |    75%  |   95%  |  71%  |  80% |   50%   |    50%   |   50%  |    36%  |   85%   |  *65.2%* |

Bootstrap-95%-KI (SampleSize=20):
- DS1000: ±20–25% → Differenzen <15% nicht signifikant
- CoderEval: ±10–15%
- Empfehlung: Gepaarte Analyse (gleiche Items, Differenz bootstrappen) für echte Quant-Vergleiche

**Devstral Small 2 24B Instruct 2512:**

| Quant        | DS1000 |CoderEval| HEval+ | MBPP+ | Overall   | Delta |
|--------------|--------|---------|--------|-------|-----------|-------|
| IQ3_XXS (UD) |   15%  |   67%   |   95%  |  64%  | **58.4%** |   –   |
| Q3_K_S (neu) |   30%  |   75%   |  100%  |  79%  | **67.0%** | +8.6% |

Q3_K_S klar besser – +8.6% Overall bei vertretbarem VRAM-Zuwachs.

### 4. Gemma-4-26B-QAT-Vergleich

| Quant        | DS1000 |CoderEval| HEval+ | MBPP+ | ARC  |HellaSwag|TruthfulQA| MathQA | MMLU-Pro| Overall  |
|--------------|--------|---------|--------|-------|------|---------|----------|--------|---------|----------|
| IQ3_S (UD)   |   10%  |   83%   |  100%  |  71%  |  95% |   60%   |    65%   |   55%  |    86%  |   53.4%  |
| QAT Q4_0     |   10%  |   17%   |   60%  |  64%  |  90% |    5%   |    60%   |   15%  |    75%  |   30.6%  |
| **Delta**    |    0%  |  -67%   |  -40%  |  -7%  |  -5% |  -55%   |    -5%   |  -40%  |   -11%  | *-22.8%* |

QAT Q4_0 ist massiv schlechter als IQ3_S (–22.8% Overall) bei ähnlichem VRAM. Kein Grund, QAT weiterzuverwenden.

### 5. Version v11→v12

Alle Python-Scripte hochgezählt:
- `run_benchmarks_v11.py` → `run_benchmarks_v12.py`
- `custom_benchmark_v11.py` → `custom_benchmark_v12.py`
- `consolidate_results_v11.py` → `consolidate_results_v12.py`
- Alle Referenzen in `benchmark_config.py`, `csv_writer.py`, `model_manager.py`, `rerun_*.py`, `run_all_dense.py`, `tests/` aktualisiert
- Alte v11-Dateien bleiben als Backup erhalten

### 6. Offene Punkte & Empfehlungen

1. **Non-Thinking-Lauf wiederholen** (nach HTTP-500-Fix): `python run_benchmarks_v12.py --model gemma-4-26b-a4b-it,google_gemma-4-26b-a4b-it,gemma-4-19b-a4b-it-reap-i1 --benchmarks DS1000,CoderEval,ARC,HellaSwag,TruthfulQA,MathQA,MMLU-Pro --sample-size 20`
2. **Qwen3-Coder-25B-Vergleichslauf** starten (3 Quants: IQ4_XS, Q3_K_M, Q4_K_S) sofern nicht bereits gelaufen
3. **Gemma-4-12b** scheint aus LMS verschwunden – fehlt für Non-Thinking-Vergleich
4. **Bootstrap-CI** in `consolidate_results_v12.py` implementiert, aber SampleSize=20 gibt zu breite Intervalle für Quant-Vergleiche – gepaarte Analyse nötig
5. **model.yaml** nur noch für mradermacher/qwen3-coder-reap (kein Konflikt) – bei neuen Modellen Konfliktrisiko prüfen
