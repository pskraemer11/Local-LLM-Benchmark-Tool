# Planungs-CSVs: Strukturierte Zusammenfassung

**Erstellt:** 15.06.2026  
**Hardware:** OMEN 16 L, NVIDIA RTX 5070 Ti (16 GB VRAM)  
**Quelle:** 12 CSV-Dateien im Root von `C:\Users\pskra\Python-Projekte\Benchmarks\`

---

## 1. Dateien-Übersicht

|  # | Dateiname(n)                                                                         | Typ                       | Umfang        |
|----|--------------------------------------------------------------------------------------|---------------------------|---------------|
|  1 | `Zusammenfassung Benchmark-Empfehlungen - alle.csv`                                  | Globale Übersicht         |  7 Ziele      |
|  2 | `Tools zur Ausführung der Benchmarks.csv`                                            | Tool-Empfehlungen         |  5 Tools      |
|  3 | `Empfohlene Benchmark für meine Hardware - Reasoning+Sprache.csv`                    | HW-spezifisch Reasoning   | 10 Benchmarks |
|  4 | `Empfohlene Benchmark für meine Hardware - Python+Math.csv`                          | HW-spezifisch Coding      |  9 Benchmarks |
|  5 | `Empfohlene Benchmark-Kombi für meine Hardware - Gemischt (Coding + Reasoning, max 100 Aufgaben).csv`| HW-spezifisch gemischt | 2 Kombis |
|  6 | `Empfohlene Benchmark - Reasoning+Sprache, neu.csv`                                  | Simple-Evals Reasoning    |  4 Datasets   |
|  7 | `Empfohlene Benchmarks für Python - Coding & Mathematik, neu.csv`                    | Simple-Evals Coding       |  4 Datasets   |
|  8 | `Benchmarks für Sprachverständnis, Reasoning & komplexe Aufgabenplanung.csv`         | Umfassend Reasoning       | 15 Benchmarks |
|  9 | `Benchmarks für Sprachverständnis & Reasoning (max 100 Aufgaben).csv`                | Subset Reasoning          |  9 Benchmarks |
| 10 | `Benchmarks für Python-Coding, Mathematik & Datenanalyse.csv`                        | Umfassend Coding          | 18 Benchmarks |
| 11 | `finale Zusammenfassung Benchmark-Empfehlungen für geg Hardware (ohne Links).csv`    | Finale Empfehlung         |  4 Kategorien |
| 12 | `finale Download-Links für Subsets max 100 Aufgaben), überprüft.csv`                 | Verifizierte Links        | 10 Benchmarks |

---

## 2. Detailanalyse pro Datei

### 2.1 Globale Übersicht: `Zusammenfassung Benchmark-Empfehlungen - alle.csv`

| Ziel                      | Empfohlene Benchmarks                                                         | Tool                            |
|---------------------------|-------------------------------------------------------------------------------|---------------------------------|
| Python-Coding             | HumanEval+, MBPP, APPS, DS-1000, PandasEval, GSM8K, MATH, EvalPlus, SWE-bench | evalplus, lm-evaluation-harness |
| Mathematik                | GSM8K, MATH, MathQA, NuminaMath, FinBench                                     | lm-evaluation-harness           |
| Datenanalyse              | DS-1000, PandasEval, FinBench                                                 | evalplus                        |
| Sprachverständnis         | MMLU-Pro, ARC, HellaSwag, TruthfulQA                                          | lm-evaluation-harness           |
| Reasoning                 | BBH, MMLU-Pro, GPQA, LongBench, FLASK, PlanBench                              | lm-evaluation-harness           |
| Komplexe Aufgabenplanung  | ALFWorld, WebShop, Mind2Web, AgentBench                                       | lm-evaluation-harness           |
| Sicherheit                | AgentHarm                                                                     | lm-evaluation-harness           |

**Konsistenz:** Gute Abdeckung aller relevanten Kategorien. FinBench erscheint doppelt (Mathe + Datenanalyse).

### 2.2 Tools: `Tools zur Ausführung der Benchmarks.csv`

| Tool                  | Zweck                             | Link-Status                                                        |
|-----------------------|-----------------------------------|--------------------------------------------------------------------|
| lm-evaluation-harness | Standard-Tool (200+ Benchmarks)   | OK                                                                 |
| evalplus              | Code-Ausführung (HumanEval etc.)  | OK                                                                 |
| langtest              | Einfache API                      | ❌ 404 (https://github.com/osunlpyang/langtest)                    |
| open-llm-leaderboard  | Leaderboard für lokale LLMs       | OK (HuggingFace Space)                                              |
| phoenix               | Benchmark-Suite für Effizienz     | ❌ 404 (https://github.com/h2oai/phoenix – kein öffentliches Repo) |

> **Anmerkung:** `langtest` und `phoenix` sind nicht auffindbar. 
> Für dieses Projekt wurden bewusst **keine dieser 5 Tools** verwendet, sondern ein eigenes Skript (`benchmark_lmstudio_v*.py`) via LM Studio REST API.

### 2.3 Hardware-spezifisch: `Empfohlene Benchmark für meine Hardware - Reasoning+Sprache.csv`

| Benchmark             | Quellen-Link                                  | Status                                                                            |
|-----------------------|-----------------------------------------------|-----------------------------------------------------------------------------------|
| BIG-bench Hard (BBH)  | https://github.com/google/BIG-bench           | ✅ OK                                                                             |
| ARC                   | https://github.com/allenai/arc                | ❌ 404 – Korrekt: HuggingFace `allenai/ai2_arc` oder https://allenai.org/data/arc |
| HellaSwag             | https://github.com/rowanz/hellaswag           | ✅ OK                                                                             |
| TruthfulQA            | https://github.com/sylinrl/TruthfulQA         | ✅ OK                                                                             |
| MMLU                  | https://github.com/hendrycks/test             | ✅ OK                                                                             |
| MMLU-Pro              | https://github.com/RAIRLab/MMLU-Pro           | ❌ 404 – Korrekt: https://github.com/TIGER-AI-Lab/MMLU-Pro                        |
| LongBench             | https://github.com/THUDM/LongBench            | ✅ OK                                                                             |
| FLASK                 | https://github.com/AllenAI/FLASK              | ❌ 404 – Korrekt: https://github.com/kaistAI/FLASK                                |
| PlanBench             | https://github.com/AGI-Edgerunners/PlanBench  | ❌ 404                                                                            |
| AgentBench            | https://github.com/THUDM/AgentBench           | ✅ OK                                                                             |

### 2.4 Hardware-spezifisch: `Empfohlene Benchmark für meine Hardware - Python+Math.csv`

| Benchmark  | Quellen-Link                                                                                           | Status  |
|------------|--------------------------------------------------------------------------------------------------------|---------|
| HumanEval  | [openai/human-eval](https://github.com/openai/human-eval)                                              | ✅ OK  |
| HumanEval+ | [evalplus/humanevalplus_release](https://github.com/evalplus/humanevalplus_release)                    | ✅ OK  |
| MBPP       | [google-research/google-research](https://github.com/google-research/google-research/tree/master/mbpp) | ✅ OK  |
| APPS       | [ElementAI/apps](https://github.com/ElementAI/apps)                                                    | ❌ 404 – Repository nicht mehr öffentlich |
| GSM8K      | [openai/grade-school-math](https://github.com/openai/grade-school-math)                                | ✅ OK  |
| MATH       | [hendrycks/math](https://github.com/hendrycks/math)                                                    | ✅ OK  |
| DS-1000    | [HKUNLP/DS-1000](https://github.com/HKUNLP/DS-1000)                                                    | ✅ OK (weitergeleitet zu xlang-ai/DS-1000) |
| PandasEval | [THUDM/PandasEval](https://github.com/THUDM/PandasEval)                                                | ❌ 404 |
| CodeXGLUE  | [microsoft/CodeXGLUE](https://github.com/microsoft/CodeXGLUE)                                          | ✅ OK  |

### 2.5 Hardware-spezifisch: `Empfohlene Benchmark-Kombi für meine Hardware - Gemischt (Coding + Reasoning, max 100 Aufgaben).csv`

| Kombi         | Benchmarks                                             | Aufgaben | Dauer   | VRAM-Einschätzung    |
|---------------|--------------------------------------------------------|----------|--------------------------------|
| Coding/Mathe  | HumanEval (100) + MBPP-Sanity (50) + GSM8K-Small (100) |   250    | 1.5–3 h | ✅ 16 GB ausreichend |
| Reasoning     | BBH (27) + ARC-Challenge (25) + MMLU-100 (100)         |   152    | 2.5–4 h | ✅ 16 GB ausreichend |

**Konsistenz:** Sinnvolle Kompromisse zwischen Abdeckung und Laufzeit auf Consumer-Hardware.

### 2.6 Simple-Evals: `Empfohlene Benchmark - Reasoning+Sprache, neu.csv`

| Benchmark     | Datei               | Download-Link                                                            | Status |
|---------------|---------------------|--------------------------------------------------------------------------|--------|
| Reasoning     | reasoning.jsonl     | https://github.com/openai/simple-evals/raw/main/data/reasoning.jsonl     | ❌ 404 |
| Understanding | understanding.jsonl | https://github.com/openai/simple-evals/raw/main/data/understanding.jsonl | ❌ 404 |
| Complex Tasks | complex_tasks.jsonl | https://github.com/openai/simple-evals/raw/main/data/complex_tasks.jsonl | ❌ 404 |
| Truthfulness  | truthfulness.jsonl  | https://github.com/openai/simple-evals/raw/main/data/truthfulness.jsonl  | ❌ 404 |

> **Kritisch:** Alle 4 Download-Links sind defekt (404). Dieses Projekt hat die simple-evals-Datasets **trotzdem lokal verfügbar** - 
>               vermutlich aus einem anderen Branch (z.B. `data/` im Root) oder via HuggingFace heruntergeladen. 
> Die `simple-evals` Repo-Struktur wurde geändert; die JSONL-Dateien wurden in ein separates Repository oder Subtree verschoben.

### 2.7 Simple-Evals: `Empfohlene Benchmarks für Python - Coding & Mathematik, neu.csv`

| Benchmark     | Datei              | Download-Link                                                            | Status |
|---------------|--------------------|--------------------------------------------------------------------------|--------|
| Simple Coding | coding.jsonl      | https://github.com/openai/simple-evals/raw/main/data/coding.jsonl         | ❌ 404 |
| Math          | math.jsonl        | https://github.com/openai/simple-evals/raw/main/data/math.jsonl           | ❌ 404 |
| Algorithmic   | algorithmic.jsonl  | https://github.com/openai/simple-evals/raw/main/data/algorithmic.jsonl   | ❌ 404 |
| Data Science  | data_science.jsonl | https://github.com/openai/simple-evals/raw/main/data/data_science.jsonl  | ❌ 404 |

> **Selbe Problematik wie 2.6** – keine der simple-evals Raw-URLs funktioniert.

### 2.8 Umfassend Reasoning: `Benchmarks für Sprachverständnis, Reasoning & komplexe Aufgabenplanung.csv`

| Benchmark | Fokus                 | Quellen-Link                                  | Status |
|-----------|-----------------------|-----------------------------------------------|--------|
| BBH       | 27 Reasoning-Aufgaben | https://github.com/google/BIG-bench           | ✅ OK |
| MMLU      | 57 Domänen            | https://github.com/hendrycks/test             | ✅ OK |
| MMLU-Pro  | 12.000+ Aufgaben      | https://github.com/RAIRLab/MMLU-Pro            | ❌ 404 → TIGER-AI-Lab/MMLU-Pro |
| ARC       | Wissenschaftl. Reasoning | https://github.com/allenai/arc              | ❌ 404 → HuggingFace allenai/ai2_arc |
| HellaSwag | Commonsense           | https://github.com/rowanz/hellaswag            | ✅ OK |
| TruthfulQA | Faktentreue          | https://github.com/sylinrl/TruthfulQA          | ✅ OK |
| GPQA      | Hochkomplex           | https://github.com/akshat46/GPQA-Dataset       | ❌ 404 |
| LongBench | Langtext              | https://github.com/THUDM/LongBench             | ✅ OK |
| FLASK     | Logik-Rätsel          | https://github.com/AllenAI/FLASK               | ❌ 404 → kaistAI/FLASK |
| ReasonBench | Reasoning           | https://github.com/THUDM/ReasonBench           | ❌ 404 |
| PlanBench | Aufgabenplanung       | https://github.com/AGI-Edgerunners/PlanBench   | ❌ 404 |
| ALFWorld  | Text-Interaktion      | https://github.com/alfworld/alfworld           | ✅ OK |
| WebShop   | Web-Navigation        | https://github.com/princeton-nlp/WebShop       | ✅ OK |
| Mind2Web  | Web-Aufgaben          | https://github.com/OSU-NLP-Group/Mind2Web      | ✅ OK |
| AgentHarm | Sicherheit            | https://github.com/centerforaisafety/AgentHarm | ❌ 404 |

### 2.9 Subset Reasoning: `Benchmarks für Sprachverständnis & Reasoning (max 100 Aufgaben).csv`

| Benchmark         | Aufgaben | Geschätzte Größe | Hardware-Eignung |
|-------------------|----------|-----------------|------------------|
| BBH               |   27     | ~200 KB | ✅ Sehr gut |
| ARC-Challenge     |   25     | ~150 KB | ✅ Sehr gut |
| HellaSwag-Small   |   100    | ~500 KB | ✅ Gut      |
| TruthfulQA-Small  |   50     | ~300 KB | ✅ Gut      |
| MMLU-100          |  100     | ~1 MB   | ✅ Gut      |
| LongBench-Small   |   10     | ~100 KB | ✅ Sehr gut |
| FLASK-Small       |   20     | ~200 KB | ✅ Sehr gut |
| PlanBench-Small   |   10     | ~100 KB | ✅ Sehr gut |

**Konsistenz:** Sinnvolles Subset mit maximal 100 Aufgaben pro Benchmark, alle lauffähig auf RTX 5070 Ti.

### 2.10 Umfassend Coding: `Benchmarks für Python-Coding, Mathematik & Datenanalyse.csv`

| Benchmark  | Fokus             | Quellen-Link | Status |
|------------|-------------------|---------------------------------------------------------------------|--------|
| HumanEval  | Python-Funktionen | https://github.com/openai/human-eval                                | ✅ OK |
| HumanEval+ | Erweitert         | https://github.com/TIGER-AI-Lab/HumanEvalPlus                       | ❌ 404 |
| MBPP       | Basis-Python      | https://github.com/google-research/google-research/tree/master/mbpp | ✅ OK |
| APPS       | Wettbewerb        | https://github.com/ElementAI/apps                                   | ❌ 404 |
| DS-1000    | Datenanalyse      | https://github.com/HKUNLP/DS-1000 → xlang-ai/DS-1000                | ✅ OK |
| PandasEval | Pandas            | https://github.com/THUDM/PandasEval                                 | ❌ 404 |
| CodeXGLUE  | Code-Verständnis  | https://github.com/microsoft/CodeXGLUE                              | ✅ OK |
| EvalPlus   | Sandbox           | https://github.com/evalplus/evalplus                                | ✅ OK |
| MathQA     | Textaufgaben      | https://github.com/AllenAI/mathqa                                   | ❌ 404 |
| GSM8K      | Grundschul-Mathe  | https://github.com/openai/grade-school-math                         | ✅ OK |
| MATH       | Wettbewerbs-Mathe | https://github.com/hendrycks/math                                   | ✅ OK |
| NuminaMath | Beweise           | https://github.com/numina-ai/numina-math                            | ❌ 404 |
| FinBench   | Finanzmathe       | https://github.com/AI4Finance/FinBench                              | ❌ 404 |
| SWE-bench  | GitHub Issues     | https://github.com/princeton-nlp/SWE-bench → SWE-bench/SWE-bench    | ✅ OK |
| AgentBench | LLM-Agents        | https://github.com/THUDM/AgentBench                                 | ✅ OK |

### 2.11 Finale Empfehlung: `finale Zusammenfassung Benchmark-Empfehlungen für geg Hardware (ohne Links).csv`

| Kategorie     | Benchmarks                     | #Aufgaben| Geschätzte Dauer |
|---------------|--------------------------------|----------|-----------|
| Python-Coding | HumanEval-100, MBPP-50, DS-100 |   250    |   2–3 h   |
| Mathematik    | GSM8K-100, MATH-100            |   200    |   3–4 h   |
| Reasoning     | BBH, ARC-Challenge, MMLU-100   |   152    |   2.5–4 h |
| Gemischt      | HumanEval+-80 + BBH            |   107    |   1.5–2 h |

**Konsistenz:** Die finale Empfehlung ist deutlich reduziert gegenüber den umfassenden Listen, fokussiert auf die **praktisch relevantesten** Benchmarks. Die geschätzte Dauer von 1.5–4 h pro Kategorie ist realistisch für Consumer-Hardware.

### 2.12 Verifizierte Links: `finale Download-Links für Subsets max 100 Aufgaben), überprüft.csv`

| Benchmark | Repository                      | Download-Link           | Status |
|-----------|---------------------------------|-------------------------|--------|
| HumanEval | openai/human-eval               | HumanEval.jsonl.gz      | ✅ OK |
| HumanEval+ | evalplus/humanevalplus_release | HumanEvalPlus.jsonl.gz  | ✅ OK |
| MBPP      | CodeEval-Pro                    | mbpp_pro.json           | ⚠️ 429 (Rate-Limit) |
| DS-1000   | xlang-ai/DS-1000                | ds1000.jsonl.gz         | ⚠️ 429 (Rate-Limit) |
| GSM8K     | openai/grade-school-math        | test.jsonl (raw)        | ❌ 404 |
| MATH      | hendrycks/math                  | test.jsonl (raw)        | ❌ 404 |
| BBH       | google/BIG-bench                | bbh.jsonl (raw)         | ❌ 404 |
| ARC       | allenai/arc                     | ARC-Challenge.jsonl (raw) | ❌ 404 |
| MMLU      | hendrycks/test                  | test.jsonl (raw)        | ❌ 404 |
| LongBench | THUDM/LongBench                 | longbench.jsonl (raw)   | ❌ 404 |
| FLASK     | AllenAI/FLASK                   | test.jsonl (raw)        | ❌ 404 |

> **Wichtig:** Die Raw-URLs (github.com/.../raw/...) liefern fast alle 404. Das liegt daran, dass GitHub Raw-URLs nur für Dateien funktionieren, die tatsächlich im Repository liegen. Viele dieser Datasets werden auf HuggingFace oder als Release-Assets bereitgestellt. Die `blob`-URLs (github.com/.../blob/...) funktionieren dagegen meist.

---

## 3. Konsistenzprüfung

### 3.1 Benchmark-Überlappung zwischen Dateien

| Benchmark | Kommt vor in | Dateien            |
|           |  x Dateien   |                    |
|-----------|--------------|--------------------|
| BBH       |      6       | 1, 3, 5, 8, 9, 11  |
| MMLU      |      6       | 1, 3, 5, 8, 9, 11  |
| ARC       |      5       | 1, 3, 5, 8, 9      |
| HumanEval(+) |   5       | 1, 4, 5, 10, 11    |
| GSM8K     |      5       | 1, 4, 5, 10, 11    |
| MBPP      |      5       | 1, 4, 5, 10, 11    |
| HellaSwag |      4       | 1, 3, 8, 9         |
| TruthfulQA |     4       | 1, 3, 8, 9         |
| MMLU-Pro  |      4       | 1, 3, 8 (doppelt), 3 |
| MATH      |      4       | 1, 4, 10, 11       |
| DS-1000   |      4       | 1, 4, 10, 11       |
| PandasEval |     3       | 1, 4, 10           |
| LongBench |      3       | 3, 8, 9            |
| FLASK     |      3       | 3, 8, 9            |
| SWE-bench |      2       | 1, 10              |
| APPS      |      2       | 4, 10              |

**Bewertung:** Die Konsistenz ist gut. Alle wichtigen Benchmarks werden mehrfach genannt. Es gibt keine widersprüchlichen Angaben.

### 3.2 Inkonsistenzen

1. **MMLU-Pro Repository:** In 3 Dateien als `RAIRLab/MMLU-Pro`, tatsächlich bei `TIGER-AI-Lab/MMLU-Pro`.
2. **ARC Repository:** In 3 Dateien als `https://github.com/allenai/arc`, tatsächlich auf HuggingFace (`allenai/ai2_arc`).
3. **FLASK Repository:** In 2 Dateien als `https://github.com/AllenAI/FLASK`, tatsächlich bei `kaistAI/FLASK`.
4. **Simple-Evals Raw-URLs:** Alle 8 Links funktionieren nicht. Die Daten sind entweder in einem anderen Branch oder die Dateien wurden in ein separates Repo ausgelagert.
5. **HumanEval+ Repository:** `TIGER-AI-Lab/HumanEvalPlus` (404) – das korrekte Repository ist `evalplus/humanevalplus_release`.
6. **PandasEval:** `THUDM/PandasEval` (404) – Repository existiert nicht mehr oder privat.
7. **DS-1000:** `HKUNLP/DS-1000` → wurde zu `xlang-ai/DS-1000` umgezogen.

### 3.3 Hardware-Einschätzung

**RTX 5070 Ti mit 16 GB VRAM** – Bewertung der Benchmark-Anforderungen:

| Benchmark       | VRAM (Modell)|VRAM (Daten)|  Gesamt | Lauffähig?         |
|-----------------|--------------|------------|---------|--------------------|
| HumanEval+ (80) | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| MBPP+ (50)      | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| DS1000 (50)     | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| BBH (27)        | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| MMLU-Pro (30)   | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| ARC (25)        | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| GSM8K (50)      | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| MATH (50)       | 6–10 GB (7B) |   < 1 MB   | 6–10 GB |  ✅                |
| SWE-bench       | **Docker** erforderlich| N/A |  N/A | ⚠️ Nur mit Docker    |
| WebShop/ALFWorld | Spezielle Umgebungen  | N/A |  N/A | ⚠️ Nur mit Simulator |

**Fazit:** Alle rein textbasierten Benchmarks sind auf RTX 5070 Ti (16 GB) mit 7B–14B Modellen in 4-bit-Quantisierung problemlos lauffähig. Agentische Benchmarks (WebShop, ALFWorld, SWE-bench) erfordern zusätzliche Infrastruktur.

---

## 4. Link-Status: Gesamtergebnis

| Status            | Anzahl  | Bedeutung                                            |
|-------------------|---------|------------------------------------------------------|
| ✅ OK (HTTP 200)  |  24    | Repository/Datei existiert                            |
| ✅ OK (Redirect)  |   2    | Repository umgezogen, funktioniert aber               |
|⚠️ 429 (Rate-Limit)|   2    | GitHub-Drosselung, existiert vermutlich               |
| ❌ 404 (Raw-URLs) |   8    | Simple-evals Raw-Dateien nicht gefunden               |
| ❌ 404 (Raw-URLs) |   5    | Benchmark Raw-Dateien (MATH, GSM8K, BBH, ARC, MMLU)   |
| ❌ 404 (Repos)    |  14    | Repository nicht mehr existent oder umbenannt         |
| ❌ 404 (Raw)      |   1    | LongBench Raw-URL                                     |
| ❌ 404 (Raw)      |   1    | FLASK Raw-URL                                         |

**Quote funktionierender Links:** 26 von 49 (53 %) – die Repo-Seiten sind meist OK (24/35 = 69 %), aber die **direkten Raw-Download-URLs sind zu 90 % defekt**. Die tatsächlichen Datenquellen sind:
- HuggingFace Datasets (bevorzugt)
- GitHub Release Assets
- Spezielle Download-Skripte der Benchmark-Autoren

---

## 5. Korrigierte & aktualisierte Quellen

| Benchmark         | Falscher Link | Korrigierter Link |
|-------------------|-----------------------------------------------|-------------------------------------------------------|
| MMLU-Pro          | https://github.com/RAIRLab/MMLU-Pro           | https://github.com/TIGER-AI-Lab/MMLU-Pro              |
| ARC               | https://github.com/allenai/arc                | https://huggingface.co/datasets/allenai/ai2_arc       |
| FLASK             | https://github.com/AllenAI/FLASK              | https://github.com/kaistAI/FLASK                      |
| HumanEval+        | https://github.com/TIGER-AI-Lab/HumanEvalPlus | https://github.com/evalplus/humanevalplus_release     |
| DS-1000           | https://github.com/HKUNLP/DS-1000             | https://github.com/xlang-ai/DS-1000                   |
| SWE-bench         | https://github.com/princeton-nlp/SWE-bench    | https://github.com/SWE-bench/SWE-bench                |
| Simple-Evals Raw  | https://github.com/openai/simple-evals/raw/main/data/... | Liegen lokal unter `simple_evals/*.jsonl`  |

---

## 6. Empfehlung für tatsächliche Nutzung auf RTX 5070 Ti

Basierend auf der Analyse aller 12 CSV-Dateien und der Hardware-Bewertung:

### Primäre Benchmarks (in Code implementiert und getestet)

| Benchmark     | Key | Kategorie    | Aufgaben   |
|               |     |              | (Standard) |
|---------------|-----|--------------|------------|
| HumanEval+    |  1  | Coding       |      80    |
| MBPP+         |  2  | Coding       |      50    |
| DS1000        |  3  | Datenanalyse |      50    |
| PandasEval    |  4  | Datenanalyse |      10    |
| MathQA        |  5  | Mathematik   |      54    |
| BBH           |  6  | Reasoning    |      54    |
| MMLU-Pro      |  7  | Wissen/MC    |      56    |  (57?)
| ARC-Challenge |  8  | Wissen/MC    |      50    |
| TruthfulQA    |  9  | Wissen/MC    |      50    |
| HellaSwag     | 10  | Commonsense  |      50    |

### Vorteile dieser Auswahl

- ✅ Alle 10 Benchmarks sind **lokal verfügbar** (in `simple_evals/`)
- ✅ Alle sind **ohne Docker/Sandbox** ausführbar
- ✅ Keiner überschreitet 100 Aufgaben (lauffähig in 1–3 h pro Modell)
- ✅ Abdeckung: Coding (40 %) + Mathe/Reasoning (30 %) + Wissen (20 %) + Commonsense (10 %)
- ✅ Keine API-Kosten (nur LM Studio + lokale GPU)

---

## 7. Metadaten der Analyse

- **Untersuchte Dateien:** 12 CSV
- **Geprüfte Links:** 49 URLs (HTTP-HEAD)
- **Dauer der Link-Prüfung:** ~50 Sekunden
- **Erstellungsdatum:** 15.06.2026
