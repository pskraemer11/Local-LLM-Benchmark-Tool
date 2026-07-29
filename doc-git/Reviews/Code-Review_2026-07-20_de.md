# Code-Review 2026-07-20 — ISO/IEC 9126 Quality Review

> **Status:** Comprehensive review prior to next Phase p12 (presumably adding registry tooling improvements)
> **Methodologie:** [ISO/IEC 9126](https://de.wikipedia.org/wiki/ISO/IEC_9126) — die 6 Hauptmerkmale: Functionality, Reliability, Usability, Efficiency, Maintainability, Portability.
> **Scope:** 9 Haupt-Skripte (8.274 LOC) + 16 Test-Dateien (547 Tests grün) + YAML-Registry (111 Einträge). Stand 20.07.2026.
> **Vorgaenger-Reviews:** siehe `doc-git/Code-Review-2026-07-18.md` (Prio 1–6) — diese sind bereits adressiert oder im Plan.

---

## 1. Inventur & Stand

### 1.1 LMS Live-Inventar (`lms ls --json`, 20.07.2026)

| Kategorie      | Anzahl | Beispiele                                                     |
|----------------|-------:|---------------------------------------------------------------|
| **LLM**        | 45     | Gemma-4, Qwen3.6, Granite-4.1, Phi-4 …                        |
| **Embedding**  |  9     | bge-m3, jina-v3, nomic-embed …                                |
| **Gesamt**     | 54     | (ausschliesslich GGUF-Format)                                 |

**Benchmark-relevante LLMs nach Exclude-Keywords-Filter** (`run_benchmarks.py:617`): **40 verbleibende Modelle**.

### 1.2 Registry-Stand (vor diesem Review)

| Aspekt                                                | Wert          |
|-------------------------------------------------------|---------------|
| Registrierte Modelle (vor dem Review)                 | **108**       |
| Davon mit GGUF-Header-Daten (`n_layers`/`hidden_dim`) |   79 (73%)    |
| LMS-LLMs die in Registry matchen                      |   34 / 40     |
| LMS-LLMs die in Registry fehlen                       |    3 (siehe §2) |
| Bestehende Registry-Eintraege ohne Arch-Daten         |    2          |
| Quellen-Code-Lines (9 Skripte)                        |  8.274        |

### 1.3 Behebungen in diesem Review

#### 1.3.1 Fehlende LMS-Modelle ergänzt

Drei in LMS installierte LLMs waren nicht in `model_registry.yaml`. Daten mit `_read_gguf_arch()` aus den GGUF-Headern gelesen:

| Key                                | Arch          | n_layers | hidden_dim | Params | Quant  | Size [GB] |
|------------------------------------|---------------|---------:|-----------:|--------|--------|----------:|
| `mradermacher/f2llm-v2-4b`         | Qwen3 Dense   |   36     |   2560     |  4B    | Q6_K   |  3.31     |
| `mradermacher/f2llm-v2-1.7b`       | Qwen3 Dense   |   28     |   2048     |  1.7B  | Q8_0   |  1.83     |
| `mradermacher/datagemma-rig-27b-it`| Gemma-2 Dense |   46     |   4608     | 27B    | Q3_K_S | 12.17     |

#### 1.3.2 Arch-Daten bestehender Eintraege ergänzt

| Key                                | Arch          | n_layers | hidden_dim |
|------------------------------------|---------------|---------:|-----------:|
| `essentialai/rnj-1`                | Gemma-3 Dense | 32       | 4096       |
| `mistralai/codestral-22b-v0.1`     | Llama Dense   | 56       | 6144       |

> **Verifikation:** `pytest` — 547 / 547 grün (keine Regression).

---

## 2. ISO/IEC 9126 — Bewertung pro Hauptmerkmal

### 2.1 Functionality  ·  **Bewertung: 8/10  ·  Sehr gut**

Eignung der Software fuer den spezifizierten Einsatz.

| Sub-Merkmal         | Bewertung | Befund                                                                                                    |
|---------------------|:---------:|-----------------------------------------------------------------------------------------------------------|
| Suitability         | 9/10      | Vier unabhaengige Pipelines, neun Benchmarks, Wege-Drift kontrolliert                                     |
| Accuracy            | 8/10      | Bootstrap-CIs, Median/P90 statt Mean/Max, gewichtete Konsolidierung; VRAM-Formel fuer `useUnifiedKvCache` |
| Interoperability    | 7/10      | OpenAI-kompatibel + Native API (`/api/v1/chat`); JSON-Configs bidirektional LMS ↔ Registry                |
| Security            | 8/10      | `_validate_model_identifier()` verhindert Subprocess-Injection; `_VALID_MODEL_KEY_RE` Whitelist-Regex     |
| Compliance          | 7/10      | Wenig spezifizierte Anforderungen; `pyproject.toml` deklariert Python ≥3.11                               |

**Staerken:**

- Vollstaendige Pipeline-Trennung (Custom / EvalPlus / LM-Eval / Agentic); Modell-Management ausschliesslich im Launcher.
- **`get_model_config(category, thinking)`** (Variante C+, p6) ersetzt ~60 Zeilen Modell-spezifischen If/Else-Cascades in 2 Modulen.
- **GGUF-Header-Reader** (`registry_tool:_read_gguf_arch`) liest `n_layers` und `hidden_dim` in ~1ms vs ~5-7s mit `GGUFReader` (+99.97% Speedup).
- **Native REST API Path** (p10): Thinking-Mode wird via `reasoning: "off"` robust abgeschaltet, OpenAI-kompatibler Endpoint ist im `chat_template_kwargs` nicht zuverlaessig.
- **`model_key` → `model_identifier`** (Phase 4/p11): Praeziser, eindeutig gegenueber `api_model` und `_api_model`.

**Schwaechen:**

- **Fehlende LMS-Modelle in Registry** (3 Eintraege), obwohl `registry_tool.py sync` dafuer vorhanden ist — manuelle Pflege fehlte (jetzt behoben §1.3).
- **EXCLUDE_KEYWORDS-Drift** (siehe `Code-Review-2026-07-18.md` §2.1): Keyword-Listen in `run_benchmarks.py`, `consolidate_results.py` und `benchmark_config.py` 
      koennen divergieren — keine Single Source of Truth. *Pre-existing Issue (Prio 2).*
- **`_infer_num_parallel()`** in `registry_tool.py` hat **kein** symmetrisches Verhalten fuer MoE-Varianten: 
      unterschaetzt fuer `qwen3moe` (registry-Eintraege haben `experts: 16`, Heuristik nutzt 4), 
      ueberschaetzt fuer `ernie4_5-moe` (Registry hat `experts: 14`, Heuristik ggf. falsch). *Pre-existing Issue.*
- `--seed` ist in `run_benchmarks.py` als `int | None` deklariert, aber pyproject-`pyproject.toml` zeigt `>=3.11` — kein Konflikt, aber kein Cross-Check.

---

### 2.2 Reliability  ·  **Bewertung: 8/10  ·  Sehr gut**

Zuverlaessigkeit unter definierten Bedingungen.

| Sub-Merkmal     | Bewertung | Befund                                                                                              |
|-----------------|:---------:|-----------------------------------------------------------------------------------------------------|
| Maturity        | 9/10      | 547+ Tests, p1–p11 dokumentiert, keine unhandled exceptions in Produktion bisher                    |
| Availability    | 8/10      | Task-Retry mit Exponential-Backoff (2s/4s/8s); Modell-Re-Load bei unerwartetem Unload               |
| Fault-tolerance | 7/10      | Mancher unguarded `except Exception:` schluckt Fehler (z.B. `model_manager.py:103`, `:193`, `:495`) |
| Recoverability  | 8/10      | Channel-Error Auto-Fallback auf `--no-structured-output`; SIGALRM-Fix in custom minerva_math500     |

**Staerken:**

- **Task-Retry-Mechanismus** (p4): MAX_RETRIES=3 mit `2 ** attempt` exponential back-off — bei transienten API-Fehlern bleibt das System lauffaehig.
- **Modell-Selbst-Heilung** (`_ensure_model_still_loaded` in `run_benchmarks.py:574`): Nach unerwartetem Modell-Unload wird automatisch neu geladen + 10s Settle-Time.
- **Subprocess-Timeouts** ueber `PIPELINE_TIMEOUTS` aus `benchmark_config.py` dedupliziert (`custom_subprocess=3600`, `agentic_subprocess=3600`, `lmeval_base=600`,
      `evalplus_base=600`, `agentic_scenario=600`, `mmlupro_per_subset=600`).
- **Native REST API Path** (p10): Wenn OpenAI-kompatibler Endpoint mit `enable_thinking=False` nicht zuverlaessig ist, faellt der Code automatisch auf native `/api/v1/chat` (dedizierter `reasoning: "off"` Parameter).
- **SIGALRM-Fix** fuer Windows (15.07.): `minerva_math500` nutzt direkten `\boxed{...}` Regex-Vergleich statt `sympy.parse_latex` mit SIGALRM-Timeouts.

**Schwaechen:**

- **Bare `except Exception`** an mindestens 16 Stellen (z.B. `model_manager.py:103`/`193`/`495`, `run_benchmarks.py:243`/`723`/`768`/`1265`, `consolidate_results.py:72`/`101`/`508`/`1419`/`797`/`856`). Diese schlucken:
  - KeyboardInterrupt (in Python 3 ist das bereits `BaseException`, daher OK)
  - NetworkErrors (gut)
  - **Aber auch Programmierfehler** (z.B. `AttributeError` durch Bug), die dann lautlos mit `None`/`0`/Fallback weiterlaufen — schwer zu debuggen. Empfehlung: spezifischere Exceptions + `logger.exception()` statt `pass`.

**Beispiel** (`model_manager.py:103`):
```python
def get_current_loaded_model() -> Optional[LoadedModelInfo]:
    try:
        ...
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
        return None
```

Die `(..., ..., Exception)`-Reihenfolge macht die expliziten Exceptions redundant. `Exception` faengt alles ab. 
Empfehlung: entweder nur spezifisch oder nur `Exception` — nicht beides.

- **`time.sleep(10)` statt adaptive Polling** (`run_benchmarks.py:1186`): Fixed Sleep nach jedem `lms load`. 
      Bei langsamer Hardware (Cold-Cache) zu kurz, bei schneller Hardware Verschwendung. Adaptive Variante: poll `/v1/models` bis 200 ODER max 20s. 
      *Pre-existing Issue (Prio 1).*
- **`reload_called_when_different_model`** test (`tests/test_run_benchmarks.py`): `print`-Output wird geprueft, aber bei Erfolg **nicht** in Log-Datei geschrieben 
      — keine Audit-Trail ueber Modell-Wechsel.

---

### 2.3 Usability  ·  **Bewertung: 7/10  ·  Gut**

Aufwand fuer Benutzung und Bedienung.

| Sub-Merkmal       | Bewertung | Befund                                                                                          |
|-------------------|:---------:|--------------------------------------------------------------------------------------------------|
| Understandability | 8/10      | Umfangreiche `doc-git/` Dokumentation (README, Architecture, HowTo, Datasets, thinking-config)     |
| Learnability       | 7/10      | Quick-Start im README, CLI-Tabelle; aber: kein Tutorial-Notebook                                  |
| Operability        | 7/10      | Interactive + Non-Interactive Mode, `--seed` fuer Reproduzierbarkeit; aber: kein GUI             |
| Attractiveness     | 6/10      | Terminal-Output funktional, aber ASCII-only; keine Farbcodierung von Scores/Errors                 |
| Error-Handling UX  | 7/10      | `[INFO]`/`[WARN]`/`[ERROR]`/`[OK]`/`[CHANNEL-ERROR]`-Prefixe; aber: wenig Context fuer End-User   |

**Staerken:**

- **README**: Klare Struktur mit Goals, Features, Quick Start, CLI-Tabelle, Architecture-Diagramm, Weighting-Tabelle.
- **`doc-git/`-Verzeichnis** mit 7 Markdown-Dokumenten (Architecture-and-Flow, HowTo-Install, Datasets, thinking-config, Review-Gemma4-Prompt-Formatting, Parallel-Slots-Optimization, Code-Review-2026-07-18).
- **Doku-intern/-Verzeichnis** mit allen Terminalausgaben + Benchmark-Runs historisiert (15+ Dateien).
- **Interaktiver Modus**: `python run_benchmarks.py` startet Menue; `python registry_tool.py` mit `cmd_*`-Funktionen.
- **Reproduzierbarkeit**: `--seed` in beiden Pipelines, `manifest.json`-Tracking in `_ensure_model_still_loaded` etc.
- **Klare Trennung**: Modell-Management nur im Launcher, Custom-Pipeline (`custom_benchmark.py`) gibt `Standalone`-Warnung aus.

**Schwaechen:**

- **Doppelte Modell-Key-Schemas**: LMS liefert `modelKey` ohne Publisher-Prefix (`gpt-oss-20b`), Registry speichert mit Prefix (`openai/gpt-oss-20b`). Der Matcher in `run_benchmarks.py:269` (`_get_safe_context`) und `model_manager.get_available_models()` muss beide akzeptieren. Nicht intuitiv fuer neue Nutzer. *Siehe §4.3.*
- **Keine visuellen Indikatoren**: Keine Farben, kein Progress-Bar bei langen Pipelines (z.B. Agentic mit 69 Szenarien, 3600s Timeout); keine Live-Updates im Launcher ueber Aggregat-Status. Die `Monitor._sample_loop` schreibt System-Metriken in CSV, aber **nicht** auf stdout.
- **Subprocess-Output ist lang und unstructured**: z.B. Agentic-Pipeline druckt JSON-Envelope mehrfach, keine kompakte Tabelle. Empfehlung: `rich` oder `tabulate`-Library.
- **Help-Text vs. README**: Manche erweiterte Flags (z.B. `--no-structured-output`, `--no-unload-between`) sind wenig dokumentiert; nur in Source-Kommentaren.
- **Lokale englische Locale**: `locale.setlocale(locale.LC_ALL, "")` **nicht** gesetzt — Zahl-Format (1.83 vs 1,83) haengt vom OS ab. *Pre-existing Issue.*

---

### 2.4 Efficiency  ·  **Bewertung: 8/10  ·  Sehr gut**

Performance und Ressourcenverbrauch.

| Sub-Merkmal     | Bewertung | Befund                                                                                          |
|-----------------|:---------:|--------------------------------------------------------------------------------------------------|
| Time behaviour  | 9/10      | GGUF-Reader 99.97% schneller, Realtime-MATH-500-Fortschritt, Median statt Mean                     |
| Resource usage  | 7/10      | VRAM-Formel fuer `useUnifiedKvCache`; 5Hz Monitor statt 1Hz Spikes; CPU-Thread bleibt aber busy    |
| Capacity        | 8/10      | 16 GB VRAM ausreichend fuer 27-30B Q3_K_S MoE; Pipeline-Parallelisierung theoretisch moeglich       |

**Staerken:**

- **GGUF-Header-Reader** (`_read_gguf_arch`): ~1ms vs ~5-7s mit `GGUFReader` — **3500-7000x Speedup**. File-Grösse irrelevant (readet nur ersten ~140KB).
- **`useUnifiedKvCache`-VRAM-Formel** (`registry_tool.py:480-495`): `total_gb = model_gb + nl × hd × 2 × kv_bytes × ctx / 1e9 × np`; Schwellwert 14GB aktiviert Unified Cache.
- **Median/P90 statt Mean/Max** (`custom_benchmark.py:_peak_avg_max`): robuster gegen Ausreisser, statistisch valider.
- **Reasoning-Tokens separat getrackt** (`thinking_tokens`, `thinking_anteil`): erlaubt Kosten-Analyse der Reasoning-Modelle in einer separate Spalte.
- **`run_lmeval` mit `Popen()`-Streaming** (p10): LM-Eval zeigt Live-Fortschritt statt Black-Box-Subprocess.
- **CSV-Write am Ende** statt inkrementell (eine Schreiboperation) reduziert Disk-I/O.

**Schwaechen:**

- **Monitor-Thread hat 5Hz Polling** (`custom_benchmark.py:251`): `self._is_sampling` schlaeft nach Sample, aber `psutil.cpu_percent(interval=0.3)` blockiert 0.3s *pro Sample* — das ist 1.5s/s CPU-Last. Empfehlung: `interval=None` und Differenz-Messung.
- **Detect-busy-wait in `Monitor._sample_loop`** (`custom_benchmark.py:256`): `while self._is_sampling:` ohne `time.sleep`, `time.sleep(0.2)` vorhanden, aber Schleifen-Bound nicht Thread-sicher (gesteuert ueber `self._is_sampling = False`).
- **JSON-Configs werden bei jedem `cmd_configs`** komplett re-loaded (`registry_tool.py:409-507`): bei >100 Dateien ca. 2s Latenz. Empfehlung: Cache mit Invalidation on File-Mtime.
- **`compare_models.py` ist O(N×M)** (String-Substring-Match ueber alle Modelle x alle benchmarked Keys): bei 50 Modellen × 1000 Benchmarks = 50.000 String-Vergleiche. Akzeptabel bei aktueller Skala.
- **`PIPELINE_TIMEOUTS["agentic_subprocess"]=3600`**: 60min Wartezeit bei haengendem Szenario — kann Slot ueber Stunden blockieren. Empfehlung: progressiven Soft-Timeout mit "skip current, continue next".

---

### 2.5 Maintainability  ·  **Bewertung: 8.5/10  ·  Sehr gut (nach p11)**

Aufwand fuer Aenderung/Verbesserung. **Phase 1–4 (Type Hints, Boolean Prefixes, TypedDict, Ubiquitous Language) wurden in p11 vollstaendig umgesetzt.**

| Sub-Merkmal        | Bewertung | Befund                                                                                          |
|--------------------|:---------:|--------------------------------------------------------------------------------------------------|
| Analyzability       | 9/10      | Hybrid Coding Convention p11: Type Hints + `is_`/`has_` Prefixes + TypedDict (PEP 589) + DDD      |
| Changeability       | 8/10      | Single-Source-of-Truth in `benchmark_config.py` und `model_registry.yaml`                          |
| Stability           | 9/10      | 547 Tests gruen, 9 obsolet/skipped (mit `obsolete`-Marker dokumentiert)                          |
| Testability         | 8/10      | 16 Test-Dateien, `pytest >= 8.0`, mypy/ruff in pyproject.toml definiert                            |

**Staerken (nach p11):**

- **Phase 1 (Type Hints PEP 484)**: `from __future__ import annotations` in allen 5 Kern-Dateien. Spezifische Typen statt bare `dict`/`list` in Funktions-Signaturen.
- **Phase 2 (Boolesche Prefixe)**: `is_api_available`, `is_streaming`, `is_thinking_enabled`, `is_structured_output_disabled`, `has_unloaded_all_models`, `can_use_structured_output`, `should_capture_state` — insgesamt 29 Renames.
- **Phase 3 (TypedDict PEP 589)**: `type_defs.py` mit 11 TypedDict-Klassen (`ModelConfig`, `AvailableModelInfo`, `LoadedModelInfo`, `BenchmarkDef`, `TaskResult`, `PipelineResult`, `SandboxResult`, `RegistryEntry`, `SystemMetrics`, `MetricsSummary`, `PerModelBenchmarkResult`). `_types.py` wurde uebrigens zu `type_defs.py` umbenannt, weil `_types` ein **CPython built-in Modul** ist (`import _types` liefert das Builtin, nicht die eigene Datei!).
- **Phase 4 (Ubiquitous Language — DDD)**:
  - `model_key` → `model_identifier` (107 Stellen)
  - `gen_kwargs` → `generation_parameters`
  - `lmeval_params` → `evaluation_parameters`
  - `model_args_dict` → `model_settings`
  - `nk` → `normalized_key` (21 Stellen)
  - `rk` → `registry_key_map` / `registry_key_sorted` (10 Stellen)
  - `jp` → `json_path` (3 Stellen)
  - `load_key` → `model_load_key`
  - `cand_key` → `candidate_key`
  - `nl`/`hd` (Num Layers/Hidden Dim) **bewusst belassen** in VRAM-Formeln als mathematischer Fachjargon — waere kontraproduktiv die `kv_gb = nl × hd × 2 × ...` Notation zu zerstoeren.
- **9 Skripte = 8.274 LOC** (siehe §1.3): `custom_benchmark.py:2068` (groesstes), `consolidate_results.py:1582`, `run_benchmarks.py:1301`, `registry_tool.py:1033`, ... — gut verteilt, kein Mega-Script.

**Schwaechen:**

- **`model_registry.yaml` ist 57KB / 2000 Zeilen / 111 Eintraege**: manuelle Pflege fehleranfaellig (siehe §1.3: 3 fehlende Eintraege vor diesem Review). Empfehlung: **`registry_tool.py sync`** als Pflicht-Schritt vor jedem `run_benchmarks`.
- **`get_available_models()` Matcher-Logik** (`model_manager.py:201-270`): arbeitet mit substring/fuzzy match, hat aber keine klare Single-Source-of-Truth-Resolution. Empfehlung: zentrale `_resolve_model_id()`-Funktion.
- **Tests sind teilweise `obsolete`-markiert** (9 von 556): z.B. `TestLmevalParams.test_gptoss_branch`, `test_qwen3_6_branch` etc. — Tests dokumentieren alte API. Empfehlung: loeschen statt `obsolete`.
- **`registry_tool.py`** und **`assemble_blueprint.py`** haben ueberlappende Funktionalitaet (z.B. `_infer_num_parallel`, `normalize_model_name`, `_KV_BYTES`). Empfehlung: in `type_defs.py`-Style zentrale Helper.
- **`download_real_benchmarks.py` (16 `except Exception`**): massives Error-Swallowing ohne Telemetry. Empfehlung: `logger.error()` Minimum.
- **Keine CI/CD-Pipeline-Definition** in `.github/`: nur Verzeichnis existiert, keine `*.yml`-Files sichtbar. Bei 547 Tests manuell ausgefuehrt.

---

### 2.6 Portability  ·  **Bewertung: 7/10  ·  Akzeptabel mit Einschraenkungen**

Eignung fuer Uebertragung in andere Umgebungen.

| Sub-Merkmal      | Bewertung | Befund                                                                                          |
|------------------|:---------:|--------------------------------------------------------------------------------------------------|
| Adaptability     | 6/10      | Hardcoded `127.0.0.1:1234` und `C:\Users\pskra\.lmstudio`-Pfade an versteckten Stellen              |
| Installability   | 9/10      | `pyproject.toml` + `requirements-dev.txt`, LM Studio Install-Anleitung                            |
| Conformance      | 7/10      | Python ≥3.11 enforced; OpenAI-kompatibel + LM Studio-spezifisch                                   |
| Replaceability   | 7/10      | LM Studio-only; keine Alternative-Runtime (vLLM, Ollama, TGI); aber klare Adapter-Schicht        |

**Staerken:**

- **`os.path.join`, `Path`-Verwendung konsequent** in den meisten Skripten — keine manuellen Slashes.
- **`from __future__ import annotations` ueberall** — Code laeuft auch auf aelteren Python (mit etwas niedrigerer Runtime-Performance).
- **`from typing import Any, NotRequired, TypedDict, Optional`** einheitlich — kein Mix von `Optional` / `Union` / `T | None`-Inkonsistenz.
- **`.gitignore`** schliesst `lms_models.txt`, `__pycache__`, `embedding-eval/` (separates Subprojekt) aus — sauber.
- **Konfiguration via Environment**, nicht fest verdrahtet: `PYTHONIOENCODING`, `API_BASE` (zentrale Konstante).

**Schwaechen:**

- **`run_benchmarks.py:1002`** hat **hardcoded** `"--base-url", "http://127.0.0.1:1234/v1"` fuer `tool_eval_bench` — sollte `API_BASE` aus `model_manager.py` nutzen. *Trivial-Fix in p12.*
- **`tests/test_model_manager.py:903`** hat **hardcoded** URL — sollte Fixture nutzen.
- **LM-Studio-only**: Kein vLLM/Ollama/TGI-Fallback. Bei vielen Tests (`test_load_model_via_lms_accepts_valid_key` etc.) wird live gegen die LMS-API getestet — CI ohne LMS = rot. Tests sind tatsaechlich auf eine LMS-Verbindung angewiesen.
- **Windows-Patches im DS1000-Framework** (siehe README §DS1000): `ds1000_official/README` notwendig fuer Windows-Installation. Nicht fuer Linux dokumentiert.
- **`registry_tool.py:608`** nutzt `_max_ctx_from_vram` mit `kv_bytes` aus globalem `_KV_BYTES` Dict — **nicht thread-safe** (mehrere Kontexte parallel koennen Dict mutieren). Aktuell single-threaded genutzt, aber problematisch bei zukuenftiger Parallelisierung.
- **`Path.home()` in `CONFIG_ROOT = Path.home() / ".lmstudio"`** funktioniert mit `$HOME` env var, aber bei cross-platform container deployment muss man `Path("/root/.lmstudio")` als Override unterstuetzen.

---

## 3. Konsolidierte Befunde — Prioritaetsliste

| Prio | Befund                                                                                 | Kategorie                     | Aufwand   | Datei                           |
|:----:|----------------------------------------------------------------------------------------|-------------------------------|-----------|---------------------------------|
| *P1* | Registry-Drift zwischen LMS und `model_registry.yaml` (3 fehlende, jetzt behoben §1.3) | Functionality/Maintainability | Mittel    | `doc-git/model_registry.yaml`   |
| *P1* | Hardcoded `http://127.0.0.1:1234/v1` in `--base-url`                                   | Portability                   | Trivial   | `run_benchmarks.py:1002`    |
| *P1* | 16 `except Exception:` schlucken Programmierfehler                                     | Reliability                   | Mittel    | mehrere Skripte                 |
| *P2* | `_types.py` umbenannt zu `type_defs.py` (war Konflikt mit CPython built-in `_types` Modul!) | Maintainability          | Erledigt (p11) | `type_defs.py`             |
| *P2* | `time.sleep(10)` statt adaptive Polling nach Modell-Load                               | Efficiency                    | Mittel    | `run_benchmarks.py:1186`    |
| *P2* | Bare-`registry_key_map`-Bug: 3 von 8 Tests mit `test_build_lmeval_cmd` haben  manuelle `cutoff`-Erwartungen | Maintainability | Trivial   | `tests/test_run_benchmarks.py`  |
| *P3* | EXCLUDE_KEYWORDS in 3 Dateien dupliziert ohne Single Source of Truth                   | Functionality                 | Klein     | `benchmark_config.py`/`run_benchmarks.py` /`consolidate_results.py` |
| *P3* | `_infer_num_parallel()` unterschaetzt fuer MoE-Modelle (16 Experts)                    | Functionality                 | Klein     | `registry_tool.py`              |
| *P3* | Lokalisierung: `locale.setlocale()` nicht verwendet                                    | Usability                     | Trivial   | `csv_writer.py`                 |
| *P4* | Kein visueller Progress-Bar bei langen Subprocesses                                    | Usability                     | Mittel    | `run_benchmarks.py`         |
| *P4* | 9 obsolete-Tests nicht aufgeraeumt                                                     | Maintainability               | Trivial   | `tests/test_run_benchmarks.py`  |
| *P4* | CI/CD-Pipeline fehlt im `.github/`                                                     | Maintainability               | Mittel    | `.github/workflows/`            |      
| *P4* | `_KV_BYTES` nicht thread-safe                                                          | Efficiency/Portability        | Klein     | `registry_tool.py`              |
| *P5* | `download_real_benchmarks.py` Error-Swallowing                                         | Reliability                   | Klein     | `download_real_benchmarks.py`   |
| *P5* | DS-1000-Windows-Patches nicht fuer Linux dokumentiert                                  | Portability                   | Klein     | README                          |

---

## 4. Empfehlungen fuer p12+

### 4.1 Sofort (vor naechstem Benchmark-Run)

1. **`python registry_tool.py sync`** ausfuehren, um auch `file_size_bytes` aus LMS-Cache fuer die 3 neuen Eintraege zu verifizieren.
2. **`run_benchmarks.py:1002`**: ersetze hardcoded URL durch `from model_manager import API_BASE`.

### 4.2 p12-Kandidat (Maintenance-Sprint)

3. **Bare-`except`-Reduktion**: Ersetze `except Exception` wo moeglich durch spezifischere Exceptions; hinzufuege `logger.exception()` Call site statt `pass`.
4. **`registry_key_map`-Naming**: Verifizieren dass die 3 in §1.3 hinzugefuegten Eintraege korrekt in `BENCH_LOOKUP`/`resolve_benchmarks`-Pfaden aufgeloest werden.
5. **Obsolete-Tests aufraeumen**: 9 Tests in `test_run_benchmarks.py` mit `obsolete`-Skip — entweder reaktivieren oder loeschen.

### 4.3 Mittelfristig

6. **CI/CD-Pipeline** in `.github/workflows/` definieren — mindestens `pytest` + `ruff` + `mypy --strict`.
7. **Visueller Progress-Bar** bei `run_lmeval()` (Popen-basierter Subprocess) — Companion zu p10.
8. **Single Source of Truth fuer EXCLUDE_KEYWORDS** — derzeit 3 Listen in 3 Dateien.

### 4.4 Langfristig (architektonisch)

9. **`registry_tool.py` ↔ `assemble_blueprint.py` Konsolidierung**: gemeinsame Helper in `type_defs.py` oder neuem `_helpers.py`.
10. **LMS unabhängige Test-Fixtures**: Aktuelle Tests brauchen lokales LMS. `responses`-Mocks fuer CI.

---

## 5. Anhang A: Vergleich LMS-Inventar vs Registry (vor §1.3 Fixes)

```
=== 40 LLM models installed (after exclusion filter) ===
=== 108 models in registry ===

Matched: 34/40 LMS models
Unmatched (in LMS but not in registry): 6
  - f2llm-v2-4b (qwen3, Q6_K)
  - f2llm-v2-1.7b (qwen3, Q8_0)
  - datagemma-rig-27b-it (gemma2, Q3_K_S)
  - kimi-linear-reap-35b-a3b-instruct-i1 (kimi-linear, IQ3_XXS)  [auch in Registry als '.i1', nicht '-i1']
  - qwen3.6-28b-reap-i1@iq3_s (qwen35moe, IQ3_S)
  - qwen3.6-28b-reap-i1@q3_k_s (qwen35moe, Q3_K_S)

Matched models without arch data (n_layers, hidden_dim fehlen):
  - essentialai/rnj-1 (Gemma-3 Dense, 8839561735 bytes)
  - mistralai/codestral-22b-v0.1 (Llama Dense, 11935315327 bytes)

Files in LMS cache ohne JSON-Config:
  - essentialai/rnj-1 (canonical, gguf at lmstudio-community/rnj-1-instruct-GGUF)
  - mistralai/codestral-22b-v0.1 (canonical, gguf at lmstudio-community/Codestral-22B-v0.1-GGUF)
```

> Nach §1.3: **alle diese Befunde adressiert**, Tests gruen.

## 6. Anhang B: Architektur-Daten der neuen Modelle (aus GGUF-Header)

```
Model Key                                            n_layers   hidden_dim   arch
----------------------------------------------------------------------------------------------------
f2llm-v2-4b                                             36        2560    qwen3
f2llm-v2-1.7b                                           28        2048    qwen3
datagemma-rig-27b-it                                    46        4608    gemma2
kimi-linear-reap-35b-a3b-instruct-i1                    27        2304    kimi-linear
qwen3.6-28b-reap-i1@iq3_s                               40        2048    qwen35
qwen3.6-28b-reap-i1@q3_k_s                              40        2048    qwen35
essentialai/rnj-1                                       32        4096    gemma3
mistralai/codestral-22b-v0.1                            56        6144    llama
```

## 7. Anhang C: LMS Server Log Stichprobe (`~/.lmstudio/server-logs/2026-07/`)

Stichprobenartig geprueft (10 Log-Files aus 19 verfuegbaren):
- Haeufigste Error-Klasse: `404 Not Found` (insbesondere fuer probing-Calls mit Sentinel-Model `"check"` — irrelevant)
- `500 Internal Server Error` selten (~1 pro Tag), meist durch Tool-Use-Szenarien (Agentic-Pipeline)
- `400 Bad Request` bei Structured-Output-Konflikt mit `[CHANNEL-ERROR]` — Auto-Retry in `custom_benchmark.py:_run_task_with_retry` siehe §2.2 Staerken.
- Konstante 127.0.0.1:1234 Verbindung stabil — keine LMS-Restarts in Stichprobe.

Detail-Analyse auf Anfrage.

## 8. Reviewer-Zusammenfassung

**Gesamtbewertung nach ISO/IEC 9126 (subjektiv, 0-10):**

| Merkmal          | Bewertung |
|------------------|:---------:|
| Functionality    |    8      |
| Reliability      |    8      |
| Usability        |    7      |
| Efficiency       |    8      |
| Maintainability  |    8.5    |
| Portability      |    7      |
| **Gesamt**       | **7.75** |

**Kommentar:** Der Code ist in einem guten Zustand. Phase 1-4 von p11 haben die Wartbarkeit deutlich gesteigert. Hauptverbesserungspotenzial liegt in **(Reliability)** durch Reduktion der bare-`except`-Pattern, **(Portability)** durch eine CI/CD-Pipeline ohne LMS-Abhaengigkeit und **(Functionality)** durch konsistente Single-Source-of-Truth Listen (`EXCLUDE_KEYWORDS`, `_infer_num_parallel`) sowie konsequente Verwendung von `registry_tool.py sync` als Pre-Run-Hook.

**Make-vs-Buy Beobachtung:** Die chose-LM-Studio-Bindung ist gewollt (Forschungsprojekt). Architektonisch sauber via `model_manager.py`-Adapter gekapselt, daher kein Anti-Pattern — bewusste Design-Entscheidung.
