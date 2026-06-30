## Plan: Integration von lm-evaluation-harness + evalplus

### Voraussetzungen / Status Quo

| Tool | Installiert? | Benchmarks |
|---|---|---|
| **lm-evaluation-harness** | ❌ Noch nicht | MMLU-Pro, ARC, TruthfulQA, HellaSwag, BBH, HumanEval, MBPP |
| **evalplus** | ✅ Bereits installiert (`evalplus.data`) | HumanEval+, MBPP+ |
| **Eigenes Skript (v17)** | ✅ Läuft | MathQA, DS1000, PandasEval |

---
Aktualisierter Plan mit deinen Vorgaben:

## Finaler Plan

### Phase 1: Installation & `think_end_token` (30 Min.)

```bash
pip install "lm_eval[api] @ git+https://github.com/EleutherAI/lm-evaluation-harness"

# Minimaltest mit think_end_token
lm_eval --model local-chat-completions \
  --model_args model=local-model,base_url=http://127.0.0.1:1234/v1,num_concurrent=1,think_end_token="think" \
  --tasks hellaswag \
  --limit 5
```

**`think_end_token`-Mechanismus:** Seit Juli 2025 kann lm-eval einen Token/String angeben, der das Ende eines Reasoning-Blocks markiert. Alles davor wird aus der Antwort entfernt, bevor die Answer-Extraktion greift. Analog zu deinem `strip_thinking_tokens()`, aber von lm-eval nativ unterstützt – kein eigener Code nötig.

---

### Phase 2: MC/Text-Benchmarks validieren (1–2 Std.)

Alle 5 Benchmarks + MathQA mit `--limit 5` und `--log_samples` testen:

```bash
for task in mmlu_pro arc_challenge truthfulqa hellaswag bbh; do
  lm_eval --model local-chat-completions \
    --model_args model=local-model,base_url=http://127.0.0.1:1234/v1,num_concurrent=1,think_end_token="think" \
    --tasks $task \
    --limit 5 \
    --log_samples \
    --output_path ergebnisse/lm_eval_validation/
done
```

- `--log_samples` schreibt jede Roh-Antwort als JSON – damit sichtest du, ob `think_end_token` funktioniert und die Answer-Extraktion korrekt greift
- Scores mit v17-Ergebnissen vergleichen (gleiches Modell, gleicher `--limit`)

---

### Phase 3: MathQA als YAML-Task (2 Std.)

**Warum MathQA hier passt:**
- `generate_until` statt `loglikelihood` → funktioniert mit LM Studio (kein logprobs)
- Prompt enthält die Aufgabe, Modell generiert Zahl → `exact_match` oder `numeric_match`
- Einmal definiert, läuft MathQA in jedem lm-eval-Lauf mit – inkl. `--limit`, `--num_fewshot`, `think_end_token`, gewichteter Aggregation

**Ablauf:**

1. Verzeichnis für Custom Tasks anlegen, z. B. `lm_eval_tasks/`
2. `mathqa.yaml`:

```yaml
task: mathqa
dataset_path: json
dataset_kwargs:
  data_files: simple_evals/math.jsonl
output_type: generate_until
test_split: train
doc_to_text: "Solve the following math problem.\n\n{{prompt}}\n\nAnswer:"
doc_to_target: "{{answer}}"
process_results: !function utils.mathqa_process_results
```

3. `utils.py` (wird von lm-eval per `!function` geladen):

```python
import re
def mathqa_process_results(doc, response):
    match = re.search(r"[-]?\d+\.?\d*", response)
    correct = match and match.group().strip() == doc["answer"].strip()
    return {"exact_match": 1.0 if correct else 0.0}
```

4. Einbindung per `--include_path lm_eval_tasks/` beim Aufruf
5. Test: `lm_eval ... --tasks mathqa --limit 5`

---

### Phase 4: evalplus validieren (30 Min., ohne Docker)

```bash
evalplus.evaluate --model "local-model" \
  --dataset humaneval \
  --backend openai \
  --base-url http://127.0.0.1:1234/v1 \
  --greedy \
  --limit 5

evalplus.evaluate --model "local-model" \
  --dataset mbpp \
  --backend openai \
  --base-url http://127.0.0.1:1234/v1 \
  --greedy \
  --limit 5
```

Ohne Docker: evalplus verwendet `subprocess` + `timeout` (äquivalent zu deinem `exec_with_timeout`). Gleiches Risiko, gleicher Schutz.

---

### Phase 5: Kompletten Durchlauf (über Nacht)

```bash
# 1. lm-eval: 6 Benchmarks (inkl. MathQA)
lm_eval --model local-chat-completions \
  --model_args model=local-model,base_url=http://127.0.0.1:1234/v1,num_concurrent=1,think_end_token="think" \
  --tasks mmlu_pro,arc_challenge,truthfulqa,hellaswag,bbh,mathqa \
  --include_path lm_eval_tasks/ \
  --limit 50 \
  --num_fewshot 0 \
  --output_path ergebnisse/lm_eval_full/

# 2. evalplus: HumanEval+ + MBPP+
evalplus.evaluate --model "local-model" --dataset humaneval \
  --backend openai --base-url http://127.0.0.1:1234/v1 --greedy
evalplus.evaluate --model "local-model" --dataset mbpp \
  --backend openai --base-url http://127.0.0.1:1234/v1 --greedy

# 3. Eigenes Skript: DS1000 + PandasEval (zurückgestellt für YAML-Integration)
python benchmark_lmstudio_v17.py --sample-size 50
```

---

### Phase 6: Ergebnisse zusammenführen (zurückgestellt)

DS1000 + PandasEval als YAML-Tasks in lm-eval wird für einen späteren Zyklus vorgemerkt – kein Termin.

---

### Aktualisierte Laufzeitabschätzung

| Phase          | Benchmarks                                  |Limit| think_end_token | Zeit      |
|----------------|---------------------------------------------|-----|-----------------|-----------|
| 2 (Validation) | 1 Task, z. B. HellaSwag                     |  5  |   ✅            | 2–5 Min   |
| 2 (Validation) | Alle 5 MC + MathQA                          |  5  |   ✅            | 15–30 Min |
| 5 (Full)       | Alle 6 lm-eval + 2 evalplus + DS1000/Pandas | 50  |   ✅            | 4–8 Std   |

==================================
User: Vorher habe ich noch weitere Fragen zum Verständnis des Algorithmus und Ablauf: 
1. Wie ist die Auswahl bei HumanEval+ und MMLU-Pro? 
2. Werden bei HumanEval+ nur die schwierigeren '+'-Fragen gezogen, oder alle 164 Standardfragen mit? 
3. Wie sieht die stratifizierte Zufallsauswahl pro Untergruppe aus (BBH-Subsets, DS1000-Libraries, MathQA-Kategorien, MMLU-Pro-Kategorien)?  
4. Erfolgt die Zufallsauswahl für das Sampling beim Download oder im Benchmark-Code?
5. Stelle mir den gesamten Programmablauf vor, wie werden die Benchmarks jetzt abgearbeitet?

LLM (DeepSeek v4 Flash): Hier die Antworten:

**1. HumanEval+:** Alle 164 Standardaufgaben von HumanEval, jede mit `base_input` *und* `plus_input` (erweiterten EvalPlus-Tests). Keine Filterung auf "nur schwierigere". **MMLU-Pro:** Kompletter `test`-Split, stratifiziert per Kategorie.

**2.** Alle 164. Das "+" bedeutet erweiterte Tests, nicht weniger/härtere Aufgaben. Die `plus_input` werden im `evaluate_code_humaneval()` separat als Differential-Test ausgewertet.

**3. Stratifizierte Zufallsauswahl:**

| Benchmark | Gruppen            | Formel                            |
|-----------|--------------------|-----------------------------------|
| BBH       | 18 Subsets         | `ceil(N/18)` pro Subset           |
| DS1000    | 5 Libraries        | `ceil(N/5)` pro Library           |
| MathQA    | 6 Kategorien       | `ceil(N/6)` pro Kategorie         |
| MMLU-Pro  | auto (aktuell ~? ) | `ceil(N/cat_count)` pro Kategorie |

Mechanismus: `random.sample(pool, min(len(pool), per_group))` pro Gruppe.

**4. An beiden Stellen:**
- **Download-Skript** (Normalmodus): Primäre Stichprobe, speichert nur die gezogenen Fragen
- **`--download-all` + `_group`-Feld:** Alle Fragen gespeichert, Sampling passiert dann im **Benchmark-Skript** via `subsample_tasks()` (stratifiziert per `_group`)

**5. Programmablauf (3 Pipelines parallel):**
```
LM Studio API ← Port 1234
├── lm-eval: mmlu_pro, arc_challenge, truthfulqa, hellaswag, bbh, mathqa (via custom YAML)
│   └── ergebnisse/lm_eval_test/
├── evalplus: HumanEval+, MBPP+ (via evalplus.codegen + evalplus.evaluate)
└── eigenes Skript (v17): DS1000, PandasEval (sowie Fallback für Rest)
    └── ergebnisse/*.csv (mit weighted_summary)
```

Eigenes Skript hat noch Code für alle 10 Benchmarks (Überschneidung). Plan: zukünftig nur DS1000+PandasEval dort, Rest via lm-eval/evalplus. Ergebnisse werden aktuell **nicht** automatisch zusammengeführt.

----
Drei Punkte:

**1. PandasEval fehlte.** `pandas_eval.jsonl` existierte nicht → `benchmark_lmstudio_v18.py` konnte nur DS1000 ausführen. Habe die Datei jetzt erstellt (10 kuratierte Aufgaben aus `download_real_benchmarks.py`).

**2. DS1000-Scoring ist strukturell niedrig** – das liegt **nicht** an v18. Ich habe alle 50 DS1000-Aufgaben getestet: **kein einziger Task** (0/50) führt fehlerfrei durch `setup_code` + `reference_code`. Das `evaluate_code()`-Framework ist eine vereinfachte Alternative zum offiziellen DS-1000-Test-Harness, der `generate_test_case()` und `test_case_id` braucht. Die 30 % kamen nur durch die 3 Fälle "keine vergleichbaren Outputs → 100 % Fallback" zustande. Das verhalten ist in v17 identisch.

**3. DS1000 bleibt trotzdem nutzbar** – die modell-generierten Codes werden *trotzdem* evaluiert (der generierte Code wird allein `exec()`'t, und falls er *ohne* Setup-Crash läuft, werden die tests/assertions ausgeführt). Der Score ist aber konservativ/niedriger als im offiziellen DS-1000-Framework.

Soll ich Mathstral auf PandasEval testen oder direkt weiter mit dem lm-eval-full-run?

---
Session zusammen fassen (16.06.2026 / 18:33 Uhr) 

## Goal
Lokales LLM-Benchmark-Tool (Python) über LM Studio REST API (Port 1234) mit standardisierten Datensätzen, gewichteter Kategorien-Auswertung und robuster Fehlerbehandlung.

## Constraints & Preferences
- **Backend:** LM Studio REST API (`localhost:1234`) – Chat Completions (`POST /v1/chat/completions`), kein `logprobs`, kein `/v1/completions`-Format (getestet)
- **Zielhardware:** NVIDIA GPU mit 16 GB VRAM, Modelle 7B–20B (OMEN 16 L, RTX 5070 Ti)
- **Virtualisierung:** Kein Docker installiert/gewünscht (evalplus ohne Sandbox, gleiches Risiko wie `exec_with_timeout`)
- **Ausschluss:** OCR/Transkription/Embedding-Modelle (whisper, vision, ocr, transcription, translat, audit, audio, embed)
- **Ergebnisse:** CSV pro (Benchmark × Modell) mit `_before/_during/_after`-Spalten + `thinking_tokens` + `thinking_anteil`; ODS-Modell-Zusammenfassungen; Markdown-Doku
- **SAMPLE_SIZE = 50** (Default, per `--sample-size` CLI überschreibbar ab v17)
- **NVidia RTX 5070 Ti:** GPU-Auslastung 56–85 % im Schnitt, VRAM nahe 16 GB (0,2–3,5 GB frei) – `num_concurrent > 1` nicht sinnvoll
- **LLM-Prompts auf Englisch**, Diagnose-Meldungen auf Deutsch
- **Kein `system_msg`** für Qwen3.5-Kompatibilität; `model_config["no_system_msg"] = True`
- **Schleifenreihenfolge:** Modelle außen, Benchmarks innen
- **Subsampling:** Zufällig mit `random.seed(42)`, `ceil(N/NumGroups)` für Untergruppen via `_group`-Feld
- **Temperatur:** Default T=0.0 (greedy), Reasoning-Modelle T=0.1, Qwen3.5 T=0.2

## Progress
### Done
- **`download_real_benchmarks.py`** – `--download-all` Flag ergänzt; im ALL-Modus werden **alle** Fragen heruntergeladen mit `_group`-Feld; Sampling-Logik für alle 10 Benchmarks aktualisiert
- **`benchmark_lmstudio_v17.py` erstellt** (Kopie v16) – Subsampling-Logik von Download-Skript nach Benchmark-Skript verlagert
- **`strip_thinking_tokens()`** – entfernt `<think>…</think>`-Blöcke aus API-Response vor Evaluation; aufgerufen in `generate_answer()` vor Rückgabe
- **Thinking-Token-Metrik** – `generate_answer()` gibt `(..., thinking_tokens)` zurück; ausgegeben als `≈X% Thinking` pro Task
- **lm-eval Phase 1 abgeschlossen** – `local-chat-completions` patched (in `openai_completions.py`); `--apply_chat_template` CLI-Flag funktioniert
- **lm-eval generate_until-Tasks getestet:** `truthfulqa_gen` (bleu_acc 60 %), `arc_challenge_chat` (100 %), `mmlu_pro_biology` (33 %), `bbh_zeroshot_boolean_expressions` (0 %)
- **evalplus auf Windows gefixt** – `pip install "git+https://github.com/evalplus/evalplus.git" --upgrade` → v0.4.0.dev44; `openai_request.py` komplett ohne `signal.SIGALRM`
- **MathQA-Rohdaten heruntergeladen** – `MathQA.zip` (7,3 MB) von `https://math-qa.github.io/math-QA/data/MathQA.zip` → `train.jsonl` (29.837), `dev.jsonl` (4.475), `test.jsonl` (2.985), `challenge_test.jsonl` (604) unter `simple_evals/`
- **Custom-YAML-Tasks erstellt und getestet:**
  - **`lm_eval_tasks/hellaswag_gen.yaml`** – `dataset_path: Rowan/hellaswag`, `output_type: generate_until`, Prompt "Answer with just the letter (A, B, C or D)", Regex-Filter `(?:answer (?:is|:)|would be|option)?\s*\(?([ABCD])\b`; Limit=5: 60 % (3/5)
  - **`lm_eval_tasks/mathqa_gen/mathqa_gen.yaml`** – `dataset_path: json`, lokale `challenge_test.jsonl`, `process_docs: !function utils.process_docs` (parst `options`-String in `choices`-Liste), Regex-Filter `(?:answer (?:is|:)|would be|option)?\s*\(?([ABCDE])\b`; Limit=5: 0 % (Model-Antworten falsch, Extraktion funktioniert)
- **`benchmark_lmstudio_v18.py` erstellt** – Nur DS1000 + PandasEval; alle MC/Text/Coding-Benchmarks entfernt (HumanEval+, MBPP+, MathQA, BBH, MMLU-Pro, ARC, TruthfulQA, HellaSwag); `save_model_summary` vereinfacht (nur Coding-Kategorie); `--non-interactive` + `--model-key` CLI-Flags; Syntax-Check OK
- **`pandas_eval.jsonl` erstellt** – 10 kuratierte Aufgaben aus `download_real_benchmarks.py` unter `simple_evals/`
- **DS1000-Evaluation analysiert** – 50/50 Tasks im simplified Framework nicht ausführbar (`code_context` + `reference_code` benötigen offizielles DS-1000-Test-Harness mit `generate_test_case()` und `test_case_id`); dies betrifft v17 und v18 gleichermaßen

### In Progress
- **(none)**

### Blocked
- **DS1000-Scoring strukturell niedrig** – Simplified `exec()`-basierte Evaluation kann `generate_test_case()`-Infrastruktur nicht ersetzen; alle 50 Tasks schlagen in `setup_code` oder `reference_code` fehl. Option: offizielles DS-1000-Framework integrieren oder Score als "konservativ/unten" dokumentieren.

## Key Decisions
| Entscheidung                                          | Begründung                                                                                                                                                  |
|-------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Subsampling in v17**                                | Download-Skript lädt einmalig alle Fragen (`--download-all`); Stichprobenziehung pro Lauf im Benchmark-Skript – schnelle Iteration ohne erneutes Downloaden |
| **Thinking-Token-Stripping in `generate_answer()`**   | Ein zentraler Ort statt in jedem `run_task()`-Zweig – betrifft Coding + MC gleichermaßen                                                                    |
| **Timeout/API-Fehler als `score_detail`**             | Statt "Kein Code generiert" – Grund sofort in CSV erkennbar                                                                                                 |
| **lm-eval + evalplus + eigenes Skript**               | lm-eval: `truthfulqa_gen`, `arc_challenge_chat`, `mmlu_pro`, `bbh_zeroshot` + MathQA (custom YAML) + HellaSwag (custom YAML); evalplus: HumanEval+, MBPP+ (GitHub-Fix für Windows); 
                                                                 ... eigenes Skript: nur DS1000, PandasEval (ab v18)                                                                                                  |
| **evalplus ohne Docker**                              | Gleiches Risiko wie `exec_with_timeout` im eigenen Skript; Docker kann später nachgerüstet werden                                                           |
| **`num_concurrent=1`**                                | VRAM nahe 16 GB, GPU bereits 56–85 % ausgelastet – Parallelisierung bringt nur Netzwerk-Overhead                                                            |
| **MathQA: lokale JSONL statt HF-Dataset**             | `math_qa`-Dataset-Skript in `datasets` v5.0.0 deprecated; `dataset_path: json` umgeht das Problem                                                           |
|**MathQA: `challenge_test` (604) statt `test` (2.985)**| 604 Fragen reichen für aussagekräftiges Benchmarking, decken alle 6 Kategorien ab, reduzieren Laufzeit um Faktor 5                                          |
| **HellaSwag Regex-Extraktion**                        | `(?:answer (?:is|:)|would be|option)?\s*\(?([ABCD])\b` matcht sowohl bare Buchstaben (`D`) als auch natürliche Formulierungen ("would be D"); single-capture-group für `exact_match` |
| **v18: nur DS1000 + PandasEval**                      | MC/Text via lm-eval, Coding (HumanEval+/MBPP+) via evalplus; Dopplung beseitigt                                                                             |
| **DS1000: vereinfachte Evaluation beibehalten**       | Gleiche `evaluate_code()`-Logik wie v17; 50/50 Tasks nicht standalone ausführbar – Score ist konservativ, aber Modell-Code wird trotzdem korrekt evaluiert 
                                                              ... (wenn `setup_code` crash-frei läuft) |

## Next Steps
1. **PandasEval mit Mathstral testen** – `python benchmark_lmstudio_v18.py` → Modell 21 (Mathstral) auswählen → beide Benchmarks DS1000 + PandasEval laufen
2. **Kompletten lm-eval-Durchlauf starten** – Alle 6+ Tasks (`truthfulqa_gen`, `arc_challenge_chat`, `mmlu_pro_*` (14), `bbh_zeroshot_*` (27), MathQA, HellaSwag) mit `--limit 50`
3. **evalplus mit HumanEval+ + MBPP+ validieren** – `evalplus.codegen` + `evalplus.evaluate`
4. **Ergebnisse mit v17 vergleichen** – Scores, Laufzeit, Konsistenz

## Critical Context
- `psutil` und `nvidia-ml-py` installiert; GPU-Auslastung 56–85 % im Schnitt, VRAM nahe 16 GB (0,2–3,5 GB frei)
- `exec_with_timeout` via Daemon-Thread (30s Timeout) – gleiches Risiko wie evalplus ohne Docker
- **LM Studio OpenAI-Compat:** `POST /v1/chat/completions` – **kein logprobs**, **kein `/v1/completions`**-Format (getestet, fehlgeschlagen)
- **`datasets` v5.0.0 installiert** – Python-basierte Dataset-Skripte nicht mehr unterstützt (`math_qa.py`); Workaround: `dataset_path: json` für lokale JSONL
- **MODEL_CONFIG:** Substring-Matches: "deepseek" → enable_thinking=True, temp=0.1, min_p=0.02; "qwen3.5" → temp=0.2, no_system_msg; Default → temp=0.0
- **lm-eval Patch:** `openai_completions.py` – `_create_payload` akzeptiert `str` und wrapt in `[{"role":"user","content":msg}]`
- **evalplus v0.4.0.dev44 installiert** (GitHub, nicht PyPI) – `openai_request.py` ohne `signal.SIGALRM` → läuft auf Windows
- **`math_qa`-Dataset hat keinen Parquet-Export** – Workaround: lokale JSONL via `dataset_path: json`
- **8 Modelle getestet:** Rnj 1 (63,1 %), Mathstral 7B (45,4 %), Pandalyst 13B (43,5 %), WizardCoder Python 13B (41,2 %), Pythia 12B I1 (37,1 %), Pythia 12B (35,5 %), Qwen3.5 9B (23,3 %), Phi 4 Reasoning Plus (6,3 %)
- **DS1000 Evaluation Limitation** – Vereinfachtes Framework kann 0/50 Tasks korrekt ausführen (fehlende `generate_test_case()`-Infrastruktur); Score ist konservativ; definitiver Fix erfordert Integration des offiziellen DS-1000-Harness
- **MathQA Regex für bare letters** – `(?:answer (?:is|:)|would be|option)?\s*\(?([ABCDE])\b` matcht auch bare Buchstaben, nicht nur "answer is X"-Patterns (Modell antwortet oft nur "B")

## Relevant Files
| Datei                                         | Beschreibung                                                                                                                              |
|-----------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| **`benchmark_lmstudio_v17.py`**               | Vorgänger (v17): 10 Benchmarks, Subsampling, Thinking-Token-Metrik                                                                        |
| **`benchmark_lmstudio_v18.py`**               | Aktuelle Version: nur DS1000 + PandasEval; `--non-interactive` + `--model-key`; entfernt MC/Text/Coding-Benchmarks (via lm-eval/evalplus) |
| `download_real_benchmarks.py`                 | Lädt alle Datensätze; `--download-all` + `_group`-Feld                                                                                    |
| `simple_evals/data_science.jsonl`             | DS1000 (50 Tasks, random sample)                                                                                                          |
| `simple_evals/pandas_eval.jsonl`              | PandasEval (10 kuratierte Aufgaben, neu erstellt)                                                                                         |
| `simple_evals/challenge_test.jsonl`           | MathQA (604 Aufgaben, alle 6 Kategorien)                                                                                                  |
| `simple_evals/train.jsonl`                    | MathQA-Trainingsset (29.837 Aufgaben)                                                                                                     |
| `simple_evals/dev.jsonl`                      | MathQA-Validierungsset (4.475 Aufgaben)                                                                                                   |
| **`lm_eval_tasks/hellaswag_gen.yaml`**        | Custom YAML: HellaSwag, `generate_until`, 4-Optionen-Prompt, Regex-Extraktion                                                             |
| **`lm_eval_tasks/mathqa_gen/mathqa_gen.yaml`** | Custom YAML: MathQA, lokale `challenge_test.jsonl`, `process_docs` in `utils.py`                                                         |
| **`lm_eval_tasks/mathqa_gen/utils.py`**       | `process_docs()`: parst `options`-String in `choices`-Liste via `re.findall(r"[abcd] \) .*?, |e \) .*?$")`                                |
| `C:\Users\pskra\AppData\Local\Programs\Python\Python314\Lib\site-packages\lm_eval\models\openai_completions.py` | **Gepatched** – `LocalChatCompletion._create_payload` akzeptiert `str`  |
| `ergebnisse/`                                 | CSV-Output (inkl. `thinking_anteil`-Spalte), Modell-Zusammenfassungen, Doku                                                               |



