# Code-Review 2026-08-03 - ISO/IEC 9126 Quality Review

> **Status:** Review nach Phase p8-Umsetzung (MTP-Drafter-Schutz, Qwen-Klassifikation, phi-4-Override, Struktur-Gate, Agentic-Safety, Run-Spec)
> **Methodologie:** [ISO/IEC 9126](https://de.wikipedia.org/wiki/ISO/IEC_9126) - die 6 Hauptmerkmale: Functionality, Reliability, Usability, Efficiency, Maintainability, Portability.
> **Scope:** 10 Haupt-Skripte (10.966 LOC) + Tests (704 gruen) + YAML-Registry (70 Eintraege) + Live-Check gegen `lms ls` (76 Modelle) + Server-Logs 2026-07/08 + Terminalausgabe Run 03.08.2026.
> **Vorgaenger-Reviews:** `doc-git/Reviews/Code-Review_2026-08-02_de.md` (Umsetzungslog), `Code-Review_2026-07-28_de.md`, `Code-Review_2026-07-27_de.md` (8.5/10)

---

## 1. Inventur & Stand (03.08.2026)

### 1.1 Quellcode-Inventar (10 Skripte, src/)

| Datei                      |   LOC  | Funcs | Docstrings | Typ-Hints (Param) | Return-Anno | except-Blöcke | Größte Funktion          |
|----------------------------|-------:|------:|-----------:|------------------:|------------:|--------------:|--------------------------|
| `run_benchmarks.py`        |  2.019 |   58  |    52%     |       100%        |    100%     |      34       | `run_lmeval` (201 Z.)    |
| `custom_benchmark.py`      |  2.176 |   62  |   *29%*    |       *85%*       |    100%     |      30       | `main` (234 Z.)          |
| `consolidate_results.py`   |  1.775 |   45  |    47%     |        98%        |     98%     |      22       | `main` (278 Z.)          |
| `registry_tool.py`         |  1.847 |   48  |    65%     |        96%        |     98%     |       9       | `cmd_validate` (147 Z.)  |
| `assemble_blueprint.py`    |  1.114 |   21  |   100%     |       100%        |    100%     |       6       | `assemble_prompts` (172) |
| `benchmark_config.py`      |    529 |    5  |   100%     |       100%        |    100%     |       1       | `get_quant` (71 Z.)      |
| `model_manager.py`         |    591 |   13  |    85%     |       100%        |    100%     |      20       | `get_available_models`   |
| `csv_writer.py`            |    482 |   12  |    58%     |        98%        |    100%     |       0       | `write_per_task_csv`     |
| `_corr_final.py`           |    263 |    3  |   *0%*     |       100%        |    100%     |       1       | `read_lms_configs` (39)  |
| `type_defs.py`             |    170 |    0  |     -      |         -         |      -      |       0       | -                        |
|----------------------------|-------:|------:|-----------:|------------------:|------------:|--------------:|--------------------------|
| *GESAMT*                   |*10.966*| *267* |  ~58%      |       ~97%        |    ~100%    |     123       |                          |

**Delta zu 28.07.2026:** +3.041 LOC, +33 Funktionen (Struktur-Gate, Run-Spec, MTP-Schutz, Agentic-Safety).

### 1.2 Test-Inventar

| Metrik                    | Wert                              |
|---------------------------|----------------------------------:|
| Test-Suite                | **704 passed** in 5.2s (0 Failed) |
| Delta zu 02.08.2026       | +11 (MTP-Schutz, phi-4-Override)  |
| Test-to-Source Ratio      | ca. 1:2.2                         |

### 1.3 Registry-Stand (model_registry.yaml)

| Aspekt                                    | Wert          |
|-------------------------------------------|--------------:|
| Registry-Eintraege (dict)                 |    70         |
| Mit `reasoning`/`blueprint`/              |    70 (100%)  |
|      `context_length`/`capabilities`      |               |
| Mit `file_size_bytes`                     |    69 (99%)   |
| Mit `truncation`                          |    69 (99%)   |
| Mit `n_layers`                            |    68 (97%)   |
| Mit `quants`                              |    50 (71%)   |
| Mit `max_context_length`                  |    53 (76%)   |
| Mit `pub_url`                             |    45 (64%)   |
| Mit `template`                            |     5 (7%) - davon **2 mit Config-Fehler** |
| Validierung (`registry_tool.py validate`) | **2 Probleme** (nur template_missing_config) |

### 1.4 Live-Abgleich lms ls vs. Registry (03.08.2026, 14:26)

- `lms ls --json`: **76 installierte Modelle** (inkl. ~10 Embeddings).
- Nach `EXCLUDE_KEYWORDS`-Filter: **58** verfuegbar.
- `registry_only=True`: **57** in Registry matchbar, Warnung **"1 Modelle nicht in Registry"**.
- Das fehlende Modell ist der **MTP-Drafter `gemma-4-12b-it-qat@q8_0`** (arch=`gemma4-assistant`,
  Pfad `MTP/gemma-4-12B-it-Q8_0.gguf`) - siehe Befund F1.
- Die Warnung des 03.08.-Runs lautete auf **2** Modelle; nachweisbar ist der Drafter,
  das zweite war vermutlich die inzwischen registrierte UD-Variante `unsloth/gemma-4-12b-it-qat@q4_k_xl`.

### 1.5 Behebungen seit 02.08.2026 (in diesem Review verifiziert)

| Commit     | Inhalt                                                                           | Verifiziert                           |
|------------|----------------------------------------------------------------------------------|---------------------------------------|
| `9cfe8aa5` | Qwen3/Qwen3.6-Klassifikation: Map-Default statt hardcodiert, Arch-Normalisierung | `validate`: reasoning_arch_mismatch 0 |
| `b74ca283` | Registry: UD-Variante + MTP-Hinweis, Drafter entfernt, pub_url-Fixes             | Registry-Check ok                     |
| `fb44d851` | MTP-Drafter-Schutz `_is_support_file` (add/resolve) + 11 Tests                   | Siehe F1 (Luecke)                     |
| `d3a0b567` | phi-4-Override auf `unsloth/phi-4` (Instruct, Q5_K_M), temp 0.8/top_k 50         | Suite 704 gruen                       |

---

## 2. Befunde (nach ISO/IEC 9126)

### F1 - [Reliability/Functionality] MTP-Drafter-Schutz deckt Modelllisten-Pfad nicht ab

**Befund:** 
- `_is_support_file()` (registry_tool.py:279) wird in `cmd_add` (Z.327/338/394) und `_resolve_model_path_multi`/`_resolve_exact` (Z.651) angewendet, 
  **nicht** aber in `model_manager.get_available_models()` (model_manager.py:265-357). Dadurch:

- Der MTP-Drafter `gemma-4-12b-it-qat@q8_0` erscheint weiterhin als eigenes Modell im `lms ls`-Ergebnis und erzeugt bei jedem Lauf die Warnung
  `[WARN] 1 Modelle nicht in Registry - mit python registry_tool.py sync hinzufügen. Ignoriert.`
- Er taucht im Menue von `custom_benchmark.py:2014` auf (dort OHNE `registry_only`-Filter).

**Beleg:** Live-Repro via `get_available_models(exclude_keywords=EXCLUDE_KEYWORDS)` 
  → `Mtp Gemma 4 12B Instruct@Q8_0` / key `gemma-4-12b-it-qat@q8_0` / arch `gemma4-assistant`.

**Bewertung:** Mittel (kein Funktionsausfall, aber permanente Fehlwarnung + Modell-Rauschen).

**Empfehlung:** `_is_support_file`-Logik in `get_available_models` (bzw. als Filter im `AvailableModelInfo`-Dict) anwenden 
    - z.B. zentrale Hilfsfunktion nach `registry_tool.py` ziehen oder dort exportieren und in `model_manager.py` importieren. 
    Danach Lauf ohne Warnung.

---

### F2 - [Reliability] Granite `template_missing_config` (2 von 5 Template-Eintraegen)

**Befund:** `registry_tool.py validate` meldet 2 Probleme:
- `ibm-granite/granite-4.0-h-tiny`: `template='granite-4.0-h-tiny_template.jinja'`, aber `promptTemplate` in `user-concrete-model-default-config` fehlt/leer.
- `ibm-granite/granite-4.1-30b`: dito (`granite-4.1-30b_template.jinja`).

**Bewertung:** Pre-existing, unabhaengig von den Edits dieses Zeitraums. Niedrig bis mittel:
betrifft 2/5 Template-Eintraegen; ohne Config entfaellt die Template-Injection fuer diese Modelle.

**Empfehlung:** Entweder Templates entfernen (falls nicht benoetigt) oder die JSON-Configs in LM Studio wieder befuellen und erneut `sync` ausfuehren.

---

### F3 - [Maintainability] Docstring-Luecken in den groessten Modulen

**Befund:** `custom_benchmark.py` hat nur **29%** Docstring-Abdeckung (62 Funktionen), `consolidate_results.py` 47%, `run_benchmarks.py` 52%, `_corr_final.py` 0%.
Typ-Hint-Abdeckung ist dagegen mit ~97% (Param) exzellent.

**Bewertung:** Mittel. Die drei groessten Dateien (5.970 LOC zusammen) haben die schwaechste Doku - genau dort, wo Orientierung am noetigsten ist.

**Empfehlung:** Fuer `custom_benchmark.py` + `consolidate_results.py` die grossen `main()`-Funktionen (234/278 Z.) in benannte Teilfunktionen 
  zerlegen und Docstrings ergaenzen.

---

### F4 - [Portability] `python -m src.registry_tool` schlaegt fehl

**Befund:** `python -m src.registry_tool validate` aus Repo-Root → `No module named 'utils.terminal'`.
    Lauffaehig ist nur `python registry_tool.py validate` mit Workdir `src/`.

**Bewertung:** Niedrig bis mittel (Konventions/Portability-Problem, dokumentierte Workarounds in HowTo-Phase E).

**Empfehlung:** `sys.path`-Ergaenzung relativ zur Datei (statt CWD-abhaengig) pruefen; alle Einstiegspunkte sollten unabhaengig vom 
    Arbeitsverzeichnis ausfuehrbar sein.

---

### F5 - [Usability/Efficiency] Lauf-Output: Codestral-22B Grammar-Fehler im Server-Log

**Befund:** Server-Log 03.08. (11:18) zeigt mehrfache 400er:
    `Failed to initialize samplers: Unexpected empty grammar stack after accepting piece (29515)` fuer `mistralai/codestral-22b-v0.1` 
    (LM-Studio/llama.cpp-seitig, wiederholend).

**Bewertung:** Extern (nicht im Tool-Code behebbar), aber beobachtet: beeinflusst DS1000-Evaluation mit diesem Modell.

**Empfehlung:** Fuer Codestral-22B im DS1000-Harness-Pfad pruefen, ob Grammar-generierung (JSON-Schema) das Modell ueberfordert; 
    ggf. Modellnotiz in Registry (`notes`) ergaenzen.

---

## 3. Bewertung nach ISO/IEC 9126

| Merkmal          | Bewertung | Begruendung                                                                                                       |
|------------------|:---------:|-------------------------------------------------------------------------------------------------------------------|
| *Functionality*  |  9.0/10   | 4 Pipelines, 10 Benchmarks, Struktur-Gate, Run-Spec, Safety-Modus; Registry-Abdeckung 57/58 installierter Modelle |
| *Reliability*    |  8.5/10   | 704 Tests gruen; F1 (Dauerwarnung MTP-Drafter), F2 (2 Granite-Template-Fehler)                                    |
| *Usability*      |  8.5/10   | CLI-Menue, YAML-Run-Spec, klare Ergebnisdoku; kleine Rest-Ecken (F1-Rauschen)                                     |
| *Efficiency*     |  8.5/10   | Suite 5.2s; Quant-Cache; Lauf-Output zeigt gesunde Telemetrie; Log-Spam `Accumulated N tokens` (extern)           |
| *Maintainability*|  8.0/10   | Typ-Hints ~97%, type_defs.py; aber 29-52% Docstrings in den groessten Modulen, grosse main()-Funktionen           |
| *Portability*    |  8.0/10   | src/-Migration, CI (pytest+ruff+mypy); F4 CWD-abhaengiger Modulaufruf                                             |
| *GESAMT*         | *8.4/10*  | Steigerung ggueber 27.07. (8.5) - Niveau gehalten trotz +3k LOC; 2 neue kleinere Funde                            |

---

## 4. Priorisierte Empfehlungen

| Prio | Massnahme                                                                   |Aufwand | Nutzen                                  |
|:----:|-----------------------------------------------------------------------------|:------:|-----------------------------------------|
|  P1  | `_is_support_file` auch in `get_available_models()` anwenden (F1)           |    S   | Beseitigt Dauerwarnung + Modellrauschen |
|  P2  | Granite-Templates: entfernen oder Configs befuellen (F2)                    |    S   | `validate` wieder 0 Probleme            |
|  P2  | Docstrings in `custom_benchmark.py`/`consolidate_results.py` ergaenzen (F3) |    M   | Wartbarkeit der groessten Module        |
|  P3  | CWD-unabhaengiger Modulaufruf (F4)                                          |    S   | Konsistente CLI-Nutzung                 |
|  P3  | Codestral-22B-Notiz wg. Grammar-Fehlern (F5)                                |    S   | Dokumentation bekannter Limitierung     |

---

## 5. Fazit

Das Projekt befindet sich auf hohem Qualitaetsniveau: Testsuite komplett gruen (704), Registry validiert (bis auf 2 vorbestehende Granite-Template-Fehler), 
Live-Abgleich gegen `lms ls` zeigt 57/58 Modelle korrekt gemappt. 
Einziger neuer, konkret behebbarer Fund ist F1: Der MTP-Drafter-Schutz (Commit `fb44d851`) ist im Listen-Pfad (`get_available_models`) noch nicht aktiv 
und verursacht die Warnung `1 Modelle nicht in Registry` bei jedem Lauf.
Alle Edits des Zeitraums (Qwen-Klassifikation, MTP-Schutz, phi-4-Override, Registry-Pflege) sind durch Tests oder Live-Validierung abgesichert.

*Stand: 03.08.2026, Git `d3a0b567` (origin/main), Working Tree sauber.*
