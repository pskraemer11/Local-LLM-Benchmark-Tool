# Code-Review 2026-07-28 — ISO/IEC 9126 Quality Review

> **Status:** Deep-Dive Codeanalyse nach Phase p8 (Rename-Cleanup, CI/CD, weitere Registry-Bereinigung)
> **Methodologie:** [ISO/IEC 9126](https://de.wikipedia.org/wiki/ISO/IEC_9126) — die 6 Hauptmerkmale: Functionality, Reliability, Usability, Efficiency, Maintainability, Portability.
> **Scope:** 9 Haupt-Skripte (7.925 LOC code-only) + 14 Test-Dateien (3.948 LOC, 559 Tests gruen) + YAML-Registry (124 Eintraege). Stand 28.07.2026.
> **Vorgaenger-Reviews:** `doc-git/Reviews/Code-Review_2026-07-27.md` (8.5/10), `doc-git/Reviews/Code-Review_2026-07-20.md` (7.75/10)

---

## 1. Inventur & Stand

### 1.1 Quellcode-Inventar (9 Skripte, code-Lines ohne Kommentare/Leerzeilen)

| Datei                       |   LOC  | Funcs | Classes | Typ-Hints | Docstrings | Bemerkung                              |
|-----------------------------|-------:|------:|--------:|-----------|------------|----------------------------------------|
| `run_benchmarks.py`         |  1.162 |   33  |    0    |   97%     | ~34%       | `main()` 329 Z. — groesste Funktion    |
| `custom_benchmark.py`       |  1.736 |   55  |    2    |   88%     | ~44%       | `generate_answer()` mit 16 Parametern  |
| `consolidate_results.py`    |  1.333 |   39  |    1    |   81%     | ~48%       | `read_data()` 206 Z.                   |
| `registry_tool.py`          |  1.477 |   44  |    0    |   93%     | ~55%       | `cmd_validate()` 156 Z.                |
| `assemble_blueprint.py`     |    880 |   23  |    0    |  *59%*    | ~65%       | *Schwaechste Typ-Hint-Abdeckung*         |
| `benchmark_config.py`       |    336 |    4  |    0    |  100%     | ~75%       | Kleinste Datei, beste Quote            |
| `model_manager.py`          |    453 |   13  |    0    |   92%     | ~77%       | Beste Docstring-Abdeckung              |
| `csv_writer.py`             |    382 |   11  |    0    |  *55%*    | ~55%       | *Zweitschwaechste Typ-Hints*             |
| `tools/lmeval_proxy.py`     |    166 |   12  |    1    |   k.A.    | k.A.       | Proxy fuer LM-Eval Native API          |
|-----------------------------|-------:|------:|--------:|-----------|------------|----------------------------------------|
| *GESAMT*                    | *7.925*| *234* |   *4*   | *~87%*    | *~50-60%*|                                        |

** => im Anschluss an Review alle nachgebessert mit 100% Typ-Hints!


### 1.2 Test-Inventar (14 Test-Dateien)

| Metrik                    | Wert          |
|---------------------------|--------------:|
| Test-Dateien              |    14         |
| Test-Funktionen           |   559         |
| Test-LOC                  | 3.948         |
| Test-to-Source Ratio      |   1:2         |
| Status                    | **Alle gruen** (4.06s)     |
| CI/CD                     |`.github/workflows/ci.yml`  |
                            |   mit pytest + ruff + mypy |

### 1.3 Registry-Stand

| Aspekt                            | Wert          | Delta zu 27.07. |
|-----------------------------------|--------------:|----------------:|
| Registrierte Modelle              | **124**       |    +9           |
| Davon mit `quants`                |    88 (71%)   |    +9           |
| Davon mit `reasoning`             |   124 (100%)  |     —           |
| Davon mit `capabilities`          |   124 (100%)  |     —           |
| Davon mit `blueprint`             |   124 (100%)  |     —           |
| Davon mit `context_length`        |   124 (100%)  |     —           |
| Davon mit `truncation`            |   115 (93%)   |     —           |
| Davon mit `arch`                  |   124 (100%)  |     —           |
| Davon mit `n_layers`/`hidden_dim` |    87 (70%)   |   +12           |
| Davon mit `template`              |    18 (15%)   |     —           |
| Davon mit `experts` (MoE)         |    33 (27%)   |     —           |
| Reasoning-Modi: `thinking`        |    61         |     —           |
| Reasoning-Modi: `instruct`        |    63         |     —           |

### 1.4 Behebungen seit letztem Review

#### 1.4.1 Rename-Cleanup (p8)

Drei `_v13`-Suffix-Dateien auf saubere Namen umbenannt:

| Alter Name                     | Neuer Name               | Aktion                           |
|--------------------------------|--------------------------|----------------------------------|
| `run_benchmarks_v13.py`        | `run_benchmarks.py`      | `git mv` + Versionierung entfernt |
| `custom_benchmark_v13.py`      | `custom_benchmark.py`    | `git mv` + Versionierung entfernt |
| `consolidate_results_v13.py`   | `consolidate_results.py` | `git mv` + Versionierung entfernt |

**Versionierungs-Logik entfernt:** `VERSION`, `VERSION_SUFFIX`, `VERSION_FILE` aus allen 3 Dateien geloescht. Kein `version.txt`-Schreibzugriff mehr.

#### 1.4.2 CI/CD-Pipeline (neu)

`.github/workflows/ci.yml` mit 4 Jobs:
- **test**: pytest auf Python 3.11/3.12/3.13 mit `lm-eval`, `evalplus`, `nvidia-ml-py3`
- **lint**: `ruff --select E,F` (Errors + Pyflakes)
- **typecheck**: `mypy` lenient auf `benchmark_config.py`, `csv_writer.py`
- **summary**: Aggregierter Status aller Jobs

#### 1.4.3 Registry auf 124 Eintraege erweitert (+9)

Neue Eintraege (aus `registry_tool.py sync` oder manuell):
- Intel AutoRound-Varianten (Qwen3, Qwen3-Coder, Mirothinker)
- Zusaetzliche MoE-Varianten (Qwen3-Coder-Reap, GLM-4.7-Flash-Reap)
- MXFP4-Eintrag (`jetbrains/mellum2-12b-a2.5b-thinking-mxfp4`)

#### 1.4.4 `truncation`-Luecken geschlossen

9 Eintraege ohne `truncation` identifiziert (alles Intel AutoRound + 2 neue MXFP4-Eintraege). ~93% Abdeckung, 9% noch offen.

#### 1.4.5 `tools/lmeval_proxy.py` Native API Integration

Proxy fuer LM-Eval Native API Endpoint:
- `reasoning='off'` via NATIVE API (`/api/v1/chat/completions`)
- Timeout 300s → 900s fuer MATH-500 (8192 Tokens bei 10 tok/s = 819s)
- Single `except Exception:` in Error-Body-Parsing (akzeptabel)

#### 1.4.6 DS1000 broken API Filter

`custom_benchmark.py`: Filter fuer Tasks mit broken APIs (z.B. `interp2d` in `code_context`) — verhindert silent failures.

#### 1.4.7 Chat-Template-Injektion fuer Gemma-4 + Granite

`assemble_blueprint.py`: `find_all_configs_for_registry_key()` + Chat-Template-Injektion fuer Modelle ohne Jinja-Template in LMS.

---

## 2. ISO/IEC 9126 — Bewertung pro Hauptmerkmal

### 2.1 Functionality · Bewertung: 8.5/10 · Sehr gut

| Sub-Merkmal       | Bewertung | Befund                                                                                        |
|-------------------|----------:|-----------------------------------------------------------------------------------------------|
| Suitability       |    9/10   | Vier unabhaengige Pipelines, 9 Benchmarks, DS1000-broken-API-Filter                           |
| Accuracy          |    9/10   | Bootstrap-CIs, Median/P90, gewichtete Konsolidierung; VRAM-Formel fuer `useUnifiedKvCache`    |
| Interoperability  |    8/10   | OpenAI-kompatibel + Native API; JSON-Configs bidirektional LMS ↔ Registry                     |
| Security          |    8/10   | `_validate_model_identifier()` verhindert Subprocess-Injection; `_VALID_MODEL_KEY_RE`         |
| Compliance        |    8/10   | CI/CD mit 3 Python-Versionen; `pyproject.toml` deklariert Python ≥3.11                        |

**Staerken:**
- **CI/CD-Pipeline** (neu): GitHub Actions mit test/lint/typecheck — erstmalige automatisierte Qualitaetssicherung
- **Registry-Datenqualitaet**: 100% der 124 Eintraege haben `reasoning`, `capabilities`, `blueprint`, `context_length`, `arch`
- **`get_quant()`-Rewrite**: 5-Stufen-Prioritaet mit YAML-Cache (seit p7)
- **DS1000-broken-API-Filter**: Tasks mit kaputten APIs werden vor dem Run aussortiert

**Schwaechen:**
- **EXCLUDE_KEYWORDS-Drift** (Prio 2, unveraendert): Keyword-Listen in 3 Dateien ohne Single Source of Truth
- **`_infer_num_parallel()`**: Unterschaetzt fuer MoE-Modelle mit 16+ Experts (unveraendert)
- **36 Eintraege ohne `quants`**: `registry_tool.py sync` noch nicht ausgefuehrt
- **9 Eintraege ohne `truncation`**: Intel AutoRound + MXFP4-Eintraege

---

### 2.2 Reliability · Bewertung: 9/10 · Sehr gut

| Sub-Merkmal     | Bewertung | Befund                                                                        |
|-----------------|----------:|-------------------------------------------------------------------------------|
| Maturity        |    9/10   | 559 Tests gruen, p1-p8 dokumentiert, CI/CD validiert                          |
| Availability    |    9/10   | Task-Retry mit Exponential-Backoff; Modell-Re-Load bei unerwartetem Unload    |
| Fault-tolerance |    9/10   | Bare-Except-Reduktion auf 3 verbleibende (von 35 in p1)                       |
| Recoverability  |    9/10   | Channel-Error Auto-Fallback; SIGALRM-Fix; Proxy-Timeout-Erhoehung             |

**Staerken:**
- **Bare-Except-Reduktion**: 3 verbleibende `except Exception:`:
  1. `custom_benchmark.py:1080` — String-Literal im Code-Generator (akzeptabel, wird in generierte Dateien geschrieben)
  2. `model_manager.py:128` — Error-Body-JSON-Parsing in REST-API-Helper (akzeptabel, Fallback auf Text)
  3. `tools/lmeval_proxy.py:57` — Error-Body-Parsing im Proxy (akzeptabel, Fallback auf `str(e)`)
- **Proxy-Timeout**: 300s → 900s fuer MATH-500 (8192 Tokens bei 10 tok/s)
- **559 Tests in 4.06s**: Alle gruen, schnelle Ausfuehrung

**Schwaechen:**
- **`test_model_manager.py:895`**: `is_model_ready(timeout=5)` Assertion entfernt (ungemockt, traf reale LMS-API)
- **`is_api_available()`**: Breiter Catch in `model_manager.py:128` ist beabsichtigt aber notorisch schwer testbar

---

### 2.3 Usability · Bewertung: 7/10 · Gut

| Sub-Merkmal       | Bewertung | Befund                                                          |
|-------------------|----------:|-----------------------------------------------------------------|
| Understandability |    8/10   | Umfangreiche `doc-git/` Dokumentation (7+ Markdown-Dateien)     |
| Learnability      |    7/10   | Quick-Start im README, CLI-Tabelle; kein Tutorial-Notebook      |
| Operability       |    7/10   | Interactive + Non-Interactive Mode; `--json`-Output             |
| Attractiveness    |    6/10   | Terminal-Output ASCII-only, keine Farben/Progress-Bars          |
| Error-Handling UX |    8/10   | `[INFO]`/`[WARN]`/`[ERROR]`/`[OK]`/`[CHANNEL-ERROR]`-Prefixe    |

**Staerken:**
- **Registry-Tool**: Interaktives CLI fuer Registry-Pflege (`cmd_*`-Funktionen)
- **`--json`-Flag**: Strukturierte Ausgabe fuer Scripting
- **`read_model_yaml()`**: Automatische Erkennung von `model.yaml` aus LMS-Hub

**Schwaechen:**
- **Keine visuellen Indikatoren**: Keine Farben, kein Progress-Bar bei langen Pipelines
- **Subprocess-Output unstrukturiert**: Agentic-Pipeline druckt JSON-Envelope mehrfach
- **`generate_answer()` mit 16 Parametern**: extrem schwer manuell aufzurufen

---

### 2.4 Efficiency · Bewertung: 8/10 · Sehr gut

| Sub-Merkmal    | Bewertung | Befund                                                        |
|----------------|----------:|---------------------------------------------------------------|
| Time behaviour |    9/10   | YAML-Cache verhindert Re-Parsing; GGUF-Header-Reader ~1ms     |
| Resource usage |    8/10   | VRAM-Formel fuer `useUnifiedKvCache`; 5Hz Monitor             |
| Capacity       |    8/10   | 16 GB VRAM ausreichend fuer 27-30B Q3_K_S MoE                 |

**Staerken:**
- **YAML-Cache** (`get_quant()`): `model_registry.yaml` wird einmalig geparst
- **GGUF-Header-Reader**: ~1ms vs ~5-7s mit `GGUFReader` — 3500-7000x Speedup
- **Median/P90 statt Mean/Max**: Robuster gegen Ausreisser

**Schwaechen:**
- **`time.sleep(10)` nach Modell-Load** (unveraendert): Fixed Sleep statt adaptive Polling
- **`PIPELINE_TIMEOUTS["agentic_subprocess"]=3600`**: 60min Wartezeit bei haengendem Szenario

---

### 2.5 Maintainability · Bewertung: 8.5/10 · Sehr gut

**Phase p8 (Rename-Cleanup) abgeschlossen. CI/CD-Pipeline neu. Code-Qualitaetsanalyse erstmalig durchgefuehrt.**

| Sub-Merkmal   | Bewertung | Befund                                                                         |
|---------------|----------:|--------------------------------------------------------------------------------|
| Analyzability |   8/10    | Type Hints ~87%, aber 2 Dateien <60%; viele `main()`-Funktionen >200 Z.        |
| Changeability |   9/10    | Single-Source-of-Truth in `benchmark_config.py` und `model_registry.yaml`      |
| Stability     |   9/10    | 559 Tests gruen, CI/CD validiert                                               |
| Testability   |   9/10    | 14 Test-Dateien, `pytest >= 8.0`, mypy/ruff in CI                              |

**Staerken:**
- **Rename-Cleanup**: `_v13`-Suffix entfernt, Versionierungs-Logik geloescht. Sauberes Root-Verzeichnis.
- **CI/CD-Pipeline** (neu): Automatisierte Qualitaetssicherung bei jedem Push/PR
- **Type Hints**: ~87% der Funktionen haben Return-Type-Annotationen
- **Exception Handling**: Nur 3 verbleibende `except Exception:` — alle dokumentiert und akzeptabel
- **`get_quant()`-Rewrite**: Klare 5-Stufen-Prioritaet mit YAML-Cache

**Schwaechen (Code-Qualitaet):**
- **18+ Funktionen >100 Zeilen**: Die groessten sind `run_benchmarks.main()` (329 Z.), `custom_benchmark.main()` (248 Z.), `consolidate_results.read_data()` (206 Z.)
- **`generate_answer()` mit 16 Parametern**: Staerkster Design-Smell im gesamten Projekt
- **Globale mutable State**: 10+ Modul-Variablen (`IS_THINKING_ENABLED`, `_REGISTRY_CACHE`, etc.) — akzeptabel fuer single-threaded, aber hinderlich fuer Parallelisierung
- **Code-Duplizierung**: `run_task()` in `custom_benchmark.py` hat `data_science`/`codereval`-Zweige mit ~80% identischem Code
- **Typ-Hint-Luecken**: `assemble_blueprint.py` (59%) und `csv_writer.py` (55%) haben deutliche Nachholbedarf
- **`registry_tool.py` ↔ `assemble_blueprint.py`**: Ueberlappende Funktionalitaet (normalize_model_name)

---

### 2.6 Portability · Bewertung: 7/10 · Akzeptabel mit Einschraenkungen

| Sub-Merkmal    | Bewertung | Befund                                                              |
|----------------|----------:|---------------------------------------------------------------------|
| Adaptability   |    6/10   | Hardcoded `127.0.0.1:1234` und `C:\Users\pskra\.lmstudio`-Pfade     |
| Installability |    9/10   | `pyproject.toml` + `requirements-dev.txt`; CI/CD installiert        |
| Conformance    |    7/10   | Python ≥3.11; OpenAI-kompatibel + LM Studio-spezifisch              |
| Replaceability |    7/10   | LM Studio-only; adapter-Schicht in `model_manager.py`               |

**Staerken:**
- **`os.path.join`, `Path`-Verwendung konsequent**
- **`.gitignore`**: schliesst `lms_models.txt`, `__pycache__`, `embedding-eval/` aus
- **CI/CD auf Ubuntu**: Linux-Kompatibilitaet getestet (3 Python-Versionen)

**Schwaechen:**
- **`run_benchmarks.py:1002`**: hardcoded `"--base-url", "http://127.0.0.1:1234/v1"`
- **LM-Studio-only**: Kein vLLM/Ollama/TGI-Fallback
- **Windows-Patches im DS1000-Framework** nicht fuer Linux dokumentiert
- **Hardcoded user-Pfade**: `C:\Users\pskra` in mehreren Konfigurationen

---

## 3. Konsolidierte Befunde — Prioritaetsliste

| Prio | Befund                                                | Kategorie       | Aufwand | Status                              |
|:----:|-------------------------------------------------------|-----------------|---------|-------------------------------------|
| *P1* | *`_v13`-Rename + Versionierung entfernt*              | Maintainability | Klein   | **ERLEDIGT (p8)**                   |
| *P1* | *CI/CD-Pipeline fehlt*                                | Maintainability | Mittel  | **ERLEDIGT (p8): .github/workflows/ci.yml** |
| *P1* | *letzte bare `except Exception:`-Blöcke*              | Reliability     | Klein   | **ERLEDIGT (p8): 3 uebrig, alle akzeptabel** |
|  P2  | EXCLUDE_KEYWORDS in 3 Dateien dupliziert              | Functionality   | Klein   | Offen                               |
|  P2  | `time.sleep(10)` statt adaptive Polling               | Efficiency      | Mittel  | Offen                               |
|  P2  | `_infer_num_parallel()` unterschaetzt fuer MoE        | Functionality   | Klein   | Offen                               |
|  P2  | 36 Registry-Eintraege ohne `quants`                   | Functionality   | Klein   | Offen (sync ausstehend)             |
|  P2  | 9 Eintraege ohne `truncation`                         | Functionality   | Klein   | Offen (neu)                         |
|  P3  | `generate_answer()` mit 16 Parametern                 | Maintainability | Mittel  | Offen (neu)                         |
|  P3  | `main()`-Funktionen >200 Zeilen (3 Stellen)           | Maintainability | Mittel  | Offen (neu)                         |
|  P3  | `assemble_blueprint.py` + `csv_writer.py` Typ-Hints   | Maintainability | Klein   | Offen (neu)                         |
|  P3  | Globale Mutable-State-Variablen (10+)                 | Maintainability | Mittel  | Offen (neu)                         |
|  P3  | Kein visueller Progress-Bar                           | Usability       | Mittel  | Offen                               |
|  P3  | `run_task()` Duplikation (data_science/codereval)     | Maintainability | Mittel  | Offen (neu)                         |
|  P4  | DS-1000-Windows-Patches nicht fuer Linux              | Portability     | Klein   | Offen                               |
|  P4  | `registry_tool.py` ↔ `assemble_blueprint.py` Konsolidierung | Maintainability | Mittel | Offen                          |

---

## 4. Empfehlungen

### 4.1 Sofort (vor naechstem Benchmark-Run)

1. **`python registry_tool.py sync`** ausfuehren → 36 Eintraege ohne `quants` auffrischen.
2. **`truncation` fuer 9 Intel AutoRound/MXFP4-Eintraege** ergaenzen.
3. **Tests ausfuehren** (`python -m pytest tests/ --tb=short -q`) — 559/559 gruen bestaetigen.

### 4.2 Maintenance-Sprint

4. **`generate_answer()` Refactoring**: 16 Parameter → Config-Objekt oder `**kwargs`. Groesster Design-Smell.
5. **`main()`-Funktionen splitten**: `run_benchmarks.py:329` Z., `custom_benchmark.py:248` Z., `consolidate_results.py:143` Z. — jede sollte in Orchestrations-Phasen zerlegt werden.
6. **Typ-Hints in `assemble_blueprint.py` und `csv_writer.py`** auf 100% bringen.
7. **`run_task()`-Duplikation aufloesen**: Gemeinsame Logik fuer `data_science`/`codereval`-Zweige extrahieren.
8. **Globale State-Variablen** kapseln: `IS_THINKING_ENABLED`, `_REGISTRY_CACHE`, etc. in Klassen oder Config-Objekte.

### 4.3 Mittelfristig

9. **EXCLUDE_KEYWORDS Single Source of Truth**: Zentrale Liste in `benchmark_config.py`, Import in `run_benchmarks.py` und `consolidate_results.py`.
10. **`_infer_num_parallel()` revisited**: MoE-spezifische Heuristik fuer qwen3moe (16 Experts), ernie4_5-moe (14 Experts).
11. **`time.sleep(10)` → adaptive Polling**: Ersetzen durch Polling-Schleife mit Timeout.

### 4.4 Langfristig

12. **LMS-unabhaengige Test-Fixtures**: `responses`-Mocks fuer CI ohne LMS.
13. **`run_benchmarks.py:1002`**: hardcoded URL durch `from model_manager import API_BASE` ersetzen.
14. **`registry_tool.py` ↔ `assemble_blueprint.py` Konsolidierung**: gemeinsame Helper in eigenes Modul.

---

## 5. Code-Qualitaets-Detailanalyse (erstmalig)

### 5.1 Type-Hint-Abdeckung pro Datei

| Datei                       | Abdeckung | Bewertung |
|-----------------------------|----------:|-----------|
| `benchmark_config.py`       |    100%   | Hervorragend |
| `run_benchmarks.py`         |     97%   | Hervorragend |
| `registry_tool.py`          |     93%   | Sehr gut   |
| `model_manager.py`          |     92%   | Sehr gut   |
| `custom_benchmark.py`       |     88%   | Gut        |
| `consolidate_results.py`    |     81%   | Gut        |
| `assemble_blueprint.py`     |     59%   | **Nachbessern** |
| `csv_writer.py`             |     55%   | **Nachbessern** |
| **GESAMT**                  |   **~87%**| Sehr gut   |

### 5.2 Exception-Handling-Qualitaet

| Datei                       | `except Exception:` | Bewertung |
|-----------------------------|--------------------:|-----------|
| `run_benchmarks.py`         | 0                   | Perfekt   |
| `custom_benchmark.py`       | 1 (String-Literal)  | Akzeptabel |
| `consolidate_results.py`    | 0                   | Perfekt   |
| `registry_tool.py`          | 0                   | Perfekt   |
| `assemble_blueprint.py`     | 0                   | Perfekt   |
| `benchmark_config.py`       | 0                   | Perfekt   |
| `model_manager.py`          | 1 (Error-Body-Parse)| Akzeptabel |
| `csv_writer.py`             | 0                   | Perfekt   |
| `tools/lmeval_proxy.py`     | 1 (Error-Body-Parse)| Akzeptabel |
| **GESAMT**                  | **3**               | **Sehr gut (von 35 in p1)** |

**Alle 3 verbleibenden sind dokumentiert und akzeptabel (kein `pass`, immer Fallback-Logik).**

### 5.3 Groesste Funktionen (>100 Zeilen)

| Funktion                                 | Datei                     | Zeilen | Problem |
|------------------------------------------|---------------------------|-------:|---------|
| `main()`                                 | `run_benchmarks.py`       |  329   | 7 Concerns: Model-Load, Registry-Validation (7 Checks), Benchmark-Dispatch, Summary |
| `main()`                                 | `custom_benchmark.py`     |  248   | 4 Concerns: Config, Model-Load, Pipeline-Dispatch, Error-Handling |
| `read_data()`                            | `consolidate_results.py`  |  206   | 2 Concerns: CSV-Parsing + Data-Transformation |
| `cmd_validate()`                         | `registry_tool.py`        |  156   | 3 Concerns: Schema-Check, GGUF-Read, Reporting |
| `create_blueprint_definitions()`          | `assemble_blueprint.py`   |  154   | Meist Daten-Definition (akzeptabel) |
| `assemble_prompts()`                     | `assemble_blueprint.py`   |  152   | 4 Concerns: Registry-Lookup, Blueprint-Selection, Prompt-Assembly, Validation |
| `run_task()`                             | `custom_benchmark.py`     |  148   | Duplizierte data_science/codereval-Zweige |
| `main()`                                 | `consolidate_results.py`  |  143   | 4 Modi: normal, compare, merge, paired bootstrap |
| `cmd_fill_arch()`                        | `registry_tool.py`        |  138   | GGUF-Lesung + Registry-Update |
| `benchmark_model()`                      | `custom_benchmark.py`     |  135   | Pipeline-Orchestrierung |
| `_unwrap_solution_for_insert()`          | `custom_benchmark.py`     |  129   | DS1000-Insert-Logik |
| `find_latest_csvs()`                     | `consolidate_results.py`  |  124   | CSV-Discovery + Filter |
| `_worker()`                              | `custom_benchmark.py`     |  116   | Streaming + Rate-Limiting (nested) |

### 5.4 Funktionen mit zu vielen Parametern (>6)

| Funktion                       | Datei                     | Parameter |
|--------------------------------|---------------------------|----------:|
| `generate_answer()`            | `custom_benchmark.py`     | **16**    |
| `_stream_chat_completion()`    | `custom_benchmark.py`     | 10        |
| `get_model_config()`           | `benchmark_config.py`     | 9         |
| `_call_lm_studio()`            | `custom_benchmark.py`     | 7         |
| `run_lmeval()`                 | `run_benchmarks.py`       | 7         |
| `_download_with_progress()`    | `custom_benchmark.py`     | 7         |
| `cmd_validate()`               | `registry_tool.py`        | 6         |

---

## 6. Statistischer Vergleich

| Metrik                         | Review   | Review   | Review   | Delta zu |
|                                |2026-07-20|2026-07-27|2026-07-28| 27.07.   |
|--------------------------------|----------|----------|----------|----------|
| *Gesamtbewertung (ISO/IEC 9126)*| 7.75/10  | *8.5/10* | *8.5/10* |    —     |
| Functionality                  |  8/10    |  8.5/10  |  8.5/10  |    —     |
| Reliability                    |  8/10    |  9/10    |  9/10    |    —     |
| Usability                      |  7/10    |  7/10    |  7/10    |    —     |
| Efficiency                     |  8/10    |  8/10    |  8/10    |    —     |
| Maintainability                |  8.5/10  |  9/10    |  8.5/10  | **-0.5** |
| Portability                    |  7/10    |  7/10    |  7/10    |    —     |
| Tests (gruen)                  | 547      | 564      | 559      |  -5      |
| Registry-Eintraege             | 108      | 115      | **124**  |  +9      |
| Kern-LOC (9 Skripte, code-only)|   —      |    —     | 7.925    |    —     |
| Test-LOC (14 Dateien)          |   —      | 5.566*   | 3.948    |    —     |
| Bare `except Exception:`       |  16+     |   6      |   **3**  |  -3 (↓50%) |
| CI/CD-Pipeline                 | Nein     | Nein     | **Ja**   |  +1      |

*\* Anmerkung 27.07.: 5.566 LOC war vermutlich Total-Lines (incl. Blanklines/Kommentare). 3.948 LOC ist code-only.*

**Wichtiger Hinweis zu Maintainability -0.5:** Die Reduktion von 9/10 auf 8.5/10 ist keine Regression, sondern eine **praezisere Bewertung** dank der erstmaligen tiefgehenden Code-Qualitaetsanalyse. Die 18+ Funktionen >100 Zeilen, `generate_answer()` mit 16 Parametern, und 10+ globale State-Variablen waren bereits vorher vorhanden, wurden aber nicht detailliert erfasst.

---

## 7. Reviewer-Zusammenfassung

**Gesamtbewertung nach ISO/IEC 9126 (subjektiv, 0-10):**

| Merkmal         | Bewertung | Tendenz |
|-----------------|----------:|---------|
| Functionality   |    8.5    | Stabil  |
| Reliability     |    9      | Stabil  |
| Usability       |    7      | Stabil  |
| Efficiency      |    8      | Stabil  |
| Maintainability |    8.5    | *Praezisiert* |
| Portability     |    7      | Stabil  |
| *Gesamt*        |   *8.5*   | Stabil  |

**Kommentar:** Der Codebase-Zustand bleibt auf hohem Niveau (8.5/10). Die drei Neuerungen dieses Reviews — Rename-Cleanup (p8), CI/CD-Pipeline, und erste tiefgehende Code-Qualitaetsanalyse — verbessern die Maintainability-Nachhaltigkeit.

**Erstmalig** wurden konkrete Code-Smells quantifiziert: 18+ Funktionen >100 Zeilen, `generate_answer()` mit 16 Parametern, 10+ globale Mutable-State-Variablen. Diese waren in frueheren Reviews nicht explizit erfasst, weil der Fokus auf Registry-Korrektheit und Exception-Handling lag.

**Hauptverbesserungspotenzial** bleibt in der **Maintainability** (Code-Smell-Reduktion) und **Portability** (Hardcoded-Pfade, LM-Studio-Lock-In). Die CI/CD-Pipeline ist ein wichtiger Schritt, um Regressionen automatisiert zu erkennen.

**Naechster logischer Schritt:** Ein Refactoring-Sprint (p9) mit Fokus auf:
1. `generate_answer()` → Config-Objekt
2. `main()`-Splitting in 3 Dateien
3. Typ-Hints in den 2 Nachzueglern
4. Duplikation in `run_task()` aufloesen
