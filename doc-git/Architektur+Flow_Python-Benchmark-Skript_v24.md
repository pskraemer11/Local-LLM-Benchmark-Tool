# Architektur & Flow – Stand 15.07.2026 (v13.0.0-p5)

> **Versions-Konvention:** siehe [`../VERSION`](../VERSION) – Single Source of Truth für Projekt-Version. Der Dateiname `_v24.md` ist Legacy und wird in einer zukünftigen Major-Version auf `_v13.md` umgestellt.

## 1. Uberblick

Das Benchmark-System besteht aus **vier unabhangigen Evaluierungs-Pipelines**, gesteuert uber einen zentralen Launcher. 
**Modell-Management (Laden/Entladen) wird NUR vom Launcher in `main()` veranlasst.**

### Vier Evaluierungs-Pipelines (9 Benchmarks)

| Pipeline                  | Skript(e)                              | Benchmarks                                     | Auswertung                                 |
|---------------------------|----------------------------------------|------------------------------------------------|--------------------------------------------|
| **Eigenes Skript v10**    | `custom_benchmark_v13.py`              | DS1000, CoderEval                              | `exec_sandboxed()` + Namespace-Vergleich   |
| **lm-evaluation-harness** | `lm_eval` CLI                          | MATH-500, ARC-Challenge, HellaSwag, TruthfulQA | `generate_until` + Regex-Extraktion        |
| **evalplus**              | `evalplus.codegen`+`evalplus.evaluate` | HumanEval+, MBPP+                              | Differential-Testing mit plus_input        |
| **Agentic**               | `tool_eval_bench` CLI                  | Agentic (69 Szenarien)                         | tool-eval-bench Envelope (final_score)     |

**Entfernt:** BBH (zu teuer, 8x Multiplier), PandasEval (zu wenig Aufgaben, wenig Differenzierungspotential), MMLU-Pro (zu teuer, 14 Subsets).

Dafur neu: **Agentic-Pipeline** (tool-eval-bench) und **MATH-500** (ersetzt MathQA).

## Struktur 
```
LM Studio (localhost:1234)
├── REST API: POST /v1/chat/completions
├── Modell-Verwaltung: lms load / unload / ps (CLI)
├── lms ls --json  -> modelKey + selectedVariant + variants[] + quantization.name
│   → modelKey = base key (z.B. essentialai/rnj-1)
│   → variants[] = @-qualifizierte IDs (z.B. ["essentialai/rnj-1@q8_0"])
│   → lms load akzeptiert NUR modelKey (ohne @) – kein CLI-Flag für Varianten-Selektion
└── Kein logprobs, kein /v1/completions

model_manager.py (GEMEINSAM, unversioniert)
├── load_model_via_lms(model_key) -> (bool, exact_identifier)
│   ├── model_key = base modelKey (ohne @) – lms load akzeptiert keine @-Varianten
│   ├── Aufruf: `lms load {model_key} --yes` (kein --gpu max, kein -c)
│   │   → GPU-Nutzung wird automatisch uber die `user-concrete-model-default-config`-JSONs gesteuert
│   │   → Kontextlange wird automatisch aus der Pre-Config ubernommen
│   └── --identifier wird nicht gesetzt (nicht fur Varianten-Selektion)
├── unload_all_models()
├── wait_for_model_ready()     [ungenutzt]
├── get_current_loaded_model() -> dict mit identifier, model_key, display_name
├── check_api_available()      [ungenutzt]
├── API_BASE                   (zentral, nicht hardcoded im Launcher)
└── PIPELINE_TIMEOUTS          (zentral definiert)

csv_writer.py (CSV-OUTPUT, unversioniert)
├── write_accumulative_summary()  -> Einheitliches Schema (; Delimiter, utf-8)
├── write_konsolidiert_aktuell()
├── median/p90-Spalten in fn_csv
└── Einheitliche Spalten: pipeline;bench;model;score;cpu_med;cpu_p90;gpu_med;...

benchmark_config.py (ZENTRALE KONFIGURATION)
├── CAT_WEIGHTS / OVERALL_WEIGHTS
├── PIPELINE_DISCOVERY
├── TOOL_EVAL_SCENARIO_IDS
├── QUANT_MAP (auto-generiert via generate_quant_map.py)
└── EXCLUDE_KEYWORDS

run_benchmarks_v13.py (LAUNCHER - main(), v10)
├── NUR HIER wird load/unload aufgerufen
├── Steuert alle 4 Pipelines
├── Custom-Subprozess via dynamischem Glob (immer hoechste _vXX-Datei)
├── Erfasst exakte Modell-ID aus lms ps
├── all_summary.append() ausserhalb des is_custom-Blocks
├── API_BASE aus model_manager.API_BASE
├── MMLU-Pro-Helper (entfernt in v13): _get_lmeval_params, _build_lmeval_cmd, _parse_subset_score
├── Task-Retry: MAX_RETRIES=3, exponentielles Backoff
├── --seed fuer reproduzierbare Task-Auswahl (an Custom-Subprozess weitergegeben)
├── --no-structured-output fuer Fallback in Custom-Pipeline
├── Context Length: Wird aus den `user-concrete-model-default-config`-JSONs ubernommen
│   (kein Parameter mehr an `load_model_via_lms()`)
├── Gibt Speicher am Ende frei
├── Exkludiert: whisper, vision, ocr, audio, embed, vl
├── API-Bereitschaft: time.sleep(10) statt polling-Schleife
├── Varianten-Aufloesung (v31):
│   ├── model_info["key"] = variant-eindeutig (selectedVariant oder modelKey@quant)
│   ├── model_info["model_key"] = base modelKey (fuer lms load)
│   ├── model_info["quant"] = quantization.name aus JSON
│   ├── model_info["variants"] = vollstaendige variants[]-Liste aus lms ls --json
│   ├── load_key = model_info["model_key"] (base Key, ohne @)
│   ├── Nach Laden: Warnung wenn geladene Variante ≠ gewuenschtem Quant
│   └── lms load hat KEIN CLI-Flag fuer Varianten-Selektion -> Workaround via Warning
├── EvalPlus resume=False (v31): resume=True entfernt, da alte Samples akkumuliert wurden
│   → evalplus_codegen generiert jetzt exakt sample_size Tasks, keine Altlasten
└── Version intern: "Unified Benchmark Launcher v10"

custom_benchmark_v13.py (CUSTOM-BENCHMARKS, v10)
├── RUFT NIE load/unload auf
├── Nimmt Modell als bereit an
├── DS1000 + CoderEval (PandasEval entfernt)
├── Task-Retry mit MAX_RETRIES=3 + exponentiellem Backoff
├── System-Metriken: Per-Task-Peak-Werte (Monitor ~5Hz), gespeichert mit median/p90
├── Strukturierter Output: response_format mit JSON-Schema (Standard)
├── extract_code() mit JSON-Parsing-Shortcut + Regex-Fallback
├── --no-structured-output als Fallback fur kleine/inkompatible Modelle
├── --seed fuer reproduzierbare Task-Auswahl
├── Speichert tasks_*.csv + modell_*.csv
├── Keine Legacy-Pfade (altes Format, interaktiver Modus entfernt)
├── Vollstandige Type Hints (55 Funktionen)
└── Standalone-Modus warnt -> Nutzung von run_benchmarks_v13.py

consolidate_results_v13.py (KONSOLIDIERUNG, v10)
├── ModelData-Dataclass (statt roher Dicts)
├── median/p90-Spalten in CSV und MD
├── compute_category_scores() normalisiert nach verfugbaren Benchmarks
├── TOP 5 / BOTTOM 5 / Kategorie-Rankings im MD
├── width-Duplikat entfernt (toter width-Block geloscht)
├── Alle Benchmarks konsolidiert (auch wenn einzelne Pipelines fehlen)
├── Bootstrap-CIs immer berechnet (DS1000 + CoderEval)
├── --compare: Paired Bootstrap fuer2+ Modelle (alle Paarvergleiche)
├── --seed fuer reproduzierbares Bootstrap
├── --models: Modell-Filter
├── --since/--until: Zeitraum-Filter fur CSV-Ergebnis-Dateien (YYYYMMDD_HHMMSS oder YYYYMMDD)
├── --all-runs: Alle historischen Benchmark-Laufe einbeziehen (Default: nur letzter Lauf)
├── --no-installed: Installed-Filter deaktivieren (Default: nur aktuell via lms ls installierte Modelle)
├── --merge: Shortcut fur --all-runs + --no-installed, merged die letzten --runs N Laufe (Default: 2)
├── Varianten-bewusste Modell-Info (v31):
│   ├── _get_model_info(): Keys jetzt variant-eindeutig (selectedVariant oder modelKey@quant)
│   │   → Kein Ueberschreiben mehr bei mehreren Quants des gleichen Modells
│   ├── _get_display_name(): Sucht auch ueber gespeichertes modelKey-Feld
│   ├── _lookup_vram(): Sucht ueber modelKey-Feld vor Fuzzy-Match
│   ├── try_read_evalplus(): Fallback auf base-Key (ohne @) fuer alte Ergebnisverzeichnisse
│   ├── read_lmeval_per_model(): Gleicher Fallback
│   └── read_agentic(): Gleicher Fallback
├── Installed-Filter: Kreuzreferenz mit lms ls --json, nur aktuell installierte Modelle (Default)
├── Latest-Run-Filter: Nur CSVs vom neuesten Timestamp overall (Default; --all-runs deaktiviert)
├── Vollstandige Type Hints (27 Funktionen)
└── Vollstandige Type Hints (27 Funktionen)
```

## Review am 28.06.2026
Nach dem Review am 28.06. wurden folgende Architekturanderungen umgesetzt:
- **Versionierungs-Vereinheitlichung**: Alle 3 Hauptskripte laufen jetzt unter gemeinsamer Major-Version **v10** (vorher: Launcher v7, Custom v24, Konsolidierung v8).
- **Hilfsmodule ohne Version**: `model_manager.py`, `csv_writer.py` (vorher `_v2`).
- **Type Hints**: Alle Funktionen in den 3 Hauptskripten (55+20+27 = 102 Funktionen) vollstandig typisiert.
- **Zentrale Konfiguration**: `benchmark_config.py` fur Gewichte, Tool-Eval-Szenarien.
- **Task-Retry**: `MAX_RETRIES=3` mit exponentiellem Backoff bei API-Fehlern.
- **MMLU-Pro-Helper extrahiert**: `_get_lmeval_params()`, `_build_lmeval_cmd()`, `_parse_subset_score()` als testbare Einzelfunktionen.
- **ModelData-Dataclass**: In `consolidate_results_v13.py` – typisierte CSV-Zeilen statt roher Dicts.
- **System-Metriken**: Median + P90 statt Mean + Max (robuster gegen Ausreisser).
- **CSV-Schema**: `fn_csv` um CPU_med/CPU_p90/GPU_med/GPU_p90/RAM_med/RAM_p90/GPU_Temp_p90 erweitert.
- **API_BASE**: Nicht mehr hardcoded, sondern aus `model_manager.API_BASE` bezogen.
- **all_summary-Bug gefixt**: `all_summary.append()` war falschlich im `if is_custom:`-Block – alle 4 Pipelines landen jetzt im Summary.
- **Pytest-Tests**: 15 Tests fur compute_category_scores, read_custom_csv, Percentile, CSV-Parsing.
- **Granite 4.0 H Tiny**: Experts=64 verursacht `ggml_new_object: not enough space` bei 1M Context; erst mit Experts=16 lauffahig.
- **Thinking-Mode per CLI**: `--thinking`-Flag aktiviert `enable_thinking=True` fur MATH-500 bei **allen Reasoning-Modellen** (AceMath, DeepSeek, Gemma 4) – nicht nur Gemma 4. Gesteuert uber `REASONING_PATTERNS`-Set in `custom_benchmark_v13.py` und "Raisonierende" Modell-Erkennung in `run_benchmarks_v13.py`.
- **Strukturierter Output (v30)**: Custom-Pipeline nutzt `response_format` mit JSON-Schema (`{"code": "..."}`) uber LM Studio API. Garantiert valides JSON, eliminiert ~12% Parsing-Fehler (leere Antworten, Markdown-Extraktion). Fallback via `--no-structured-output`.
- **Paired Bootstrap Vergleich (v30)**: `consolidate_results_v13.py --compare "key1,key2,key3"` vergleicht alle Paare mit gepaartem Bootstrap-CI. `--seed` sorgt fur identische Task-Subsets.
- **--seed fur Reproduzierbarkeit (v30)**: `run_benchmarks_v13.py --seed 42` und `custom_benchmark_v13.py --seed 42` ermoeglichen reproduzierbare Task-Auswahl.
- **--bootstrap entfernt (v30)**: CIs werden immer berechnet, wenn Per-Item-Daten vorhanden sind. Keine Flag noetig.
- **Context Length (v32)**: Wird aus den `user-concrete-model-default-config`-JSONs ubernommen (kein CLI-Parameter mehr). Typisch 8192-16384 – ausreichend fur alle Benchmarks (DS1000~1.2K, MATH-500~1K, Agentic~9K), reduziert VRAM-Druck bei 128K-Modellen massiv.

---

## 2. Haupt-Flow (run_benchmarks_v13.py)

### 2.1 main()-Funktion – Zentrales Modell-Management

Alle Pipelines verwenden die exakte Modell-ID aus `model_info["_api_model"]` (z.B. `microsoft/phi-4@q6_k`). Keine `variant`-/`key`-Mismatches mehr:

```
main()
├── stdout.reconfigure(encoding='utf-8')
├── os.environ["PYTHONIOENCODING"] = "utf-8"     # Global fuer Subprozesse
├── Argumente parsen (--model, --benchmarks, --sample-size)
├── get_available_models()                        # lms ls --json -> dedupliziert per model_family
├── resolve_models()                              # exakter Match vor Substring
├── resolve_benchmarks()
│
├── for MODEL in models:
│   ├── Reasoning-/MoE-Erkennung (Timeout x2 / Anzeige)
│   ├── get_current_loaded_model()                # lms ps --json
│   ├── if gleiches Modell geladen:
│   │   └── api_model = loaded["identifier"]
│   │   └── (unload + reload)                     # bei anderem Modell
│   │       ├── unload_all_models()
│   │       ├── ok, api_model = load_model_via_lms(model_key)  # -> exakte ID (Config aus JSON)
│   │       └── time.sleep(10)                    # API-Initialisierung abwarten
│   │
│   ├── model_info["_api_model"] = api_model      # GLOBAL fuer alle Pipelines
│   │
│   ├── for BENCHMARK in benchmarks:
│   │   ├── if agentic:
│   │   │   └── run_agentic()                     # tool-eval-bench
│   │   ├── if evalplus (HumanEval+/MBPP+):
│   │   │   ├── evalplus.codegen --id-range [0,N) # exclusives Ende
│   │   │   └── evalplus.evaluate
│   │   ├── if lmeval (MATH-500, ARC, HellaSwag, TruthfulQA):
│   │   │   └── lm_eval --model local-chat-completions
│   │   └── if custom (DS1000/CoderEval):
│   │       └── custom_benchmark_v13.py --subprozess
│   │           (Skript via dynamischem Glob aufgeloest: CUSTOM_BENCHMARK_SCRIPT)
│   │
│   └── all_summary.append(result)                # alle 4 Pipelines (Bugfix 28.06.)
│   └── csv_writer.write_accumulative_summary()   # Zwischenzusammenfassung
│
├── unload_all_models()                            # Speicher freigeben
└── csv_writer.write_konsolidiert_aktuell()        # Gesamtuebersicht (bei >1 Modell)
```

### 2.2 Modell-Management-Architektur

**ALT (vor v20):** Drei unabhangige Ladequellen -> doppeltes Laden.

**NEU (v20+):**
- `model_manager.py` enthalt ALLE Modell-Funktionen
- `run_benchmarks_v13.py` importiert aus `model_manager` - einziger Aufrufer von load/unload
- `custom_benchmark_v13.py` importiert aus `model_manager`, ruft **nie** `load/unload` auf
- `_api_model` (exakte ID aus `lms ps`) wird konsistent in **allen** Pipelines verwendet
- `API_BASE` wird aus `model_manager.API_BASE` bezogen (nicht hardcoded im Launcher)
- **Context Length:** Wird aus den `user-concrete-model-default-config`-JSONs ubernommen (kein Parameter mehr an `load_model_via_lms()`). Typisch 8192–16384 – ausreichend fur alle Pipelines (DS1000~1.2K, MATH-500~1K, Agentic~9K) und reduzieren VRAM-Druck bei Modellen mit nativen 128K+ Context massiv.

### 2.3 Modell-Bereitschaft (vereinfacht in v9)

**ALT (vor v9):** `wait_for_model_ready()` pollte POST `/v1/chat/completions` mit `"model": "check"` (fruher: POST `inference`-Endpoint). Schlug oft fehl weil `"model": "check"` kein gultiger LM-Studio-Modellname ist.

**ALT (v9 initial):** `check_api_available()` pollte GET `/v1/models` alle 2s (max 90s). Schlug feil weil der REST-Server nach `lms load` zusatzliche Zeit fur die Modell-Initialisierung braucht.

**NEU (v9 fix):** Nach `load_model_via_lms()` wird das Modell via `lms ps --json` bestatigt. Dann einfaches `time.sleep(10)` - keine Polling-Schleife mehr:

```python
# run_benchmarks_v13.py:
ok, api_model = load_model_via_lms(model_key)  # lms load + lms ps polling
print("  [INFO] Warte 10s auf API-Initialisierung...")
time.sleep(10)
model_info["_api_model"] = api_model
```

Nach Reload (wenn Custom-Benchmark das Modell unerwartet entladen hat): ebenfalls `time.sleep(10)`.

### 2.4 Dynamische Subprozess-Aufloesung (NEU in v7/v24, beibehalten in v10)

**Problem:** Bei `Copy-Item custom_benchmark_v23.py custom_benchmark_v24.py` musste der Launcher manuell aktualisiert werden, sonst rief er die alte Version auf.

**Fix:** Der Launcher ermittelt die hochste vorhandene `custom_benchmark_v*.py` per Glob:

```python
_custom_scripts = glob.glob(os.path.join(BASE_DIR, "custom_benchmark_v*.py"))
_versions = [(int(re.search(r'_v(\d+)\.py$', s).group(1)), s) for s in _custom_scripts]
CUSTOM_BENCHMARK_SCRIPT = max(_versions, key=lambda x: x[0])[1]
```

Vorteil: Nach `Copy-Item` wird ohne manuellen Eingriff sofort die neue Version verwendet.
Nachteil: Beide Versionen (alt + neu) mussen wahrend des Laufs existieren, da erst beim Start aufgeloest wird.

### 2.5 id_range-Korrektur

**Bug:** EvalPlus verwendet `[low, high)` (exklusives Ende). `id_range = "[0,sample_size-1]"` erzeugte mit SampleSize=8 den Bereich `[0,7]` -> nur 7 Aufgaben.

**Fix:** `id_range = f"[0,{args.sample_size}]"` -> SampleSize=20 -> `[0,20]` = 20 Aufgaben.

### 2.6 Modell-Klassifizierung

```python
REASONING_KEYWORDS = ["reasoning", "think", "r1"]
MOE_PATTERN = re.compile(r"\d+b-a\d+b", re.IGNORECASE)  # z.B. "8b-a1b"

_is_reasoning_model()   # -> Timeout x2 (2x eval_timeout) + Thinking-Mode via --thinking
_is_moe_model()         # -> nur Anzeige "(erkannt)"
_is_qwen3_5_model()     # -> systemlose Prompt-Einbettung
_is_qwen3_6_model()     # -> enable_thinking=False, max_tokens=8192
_is_gptoss_model()      # -> temperature=1.0, max_tokens=4096
_is_gemma_model()       # -> Thinking-Mode via --thinking (separat von _is_reasoning_model)
```

**Zusatzlich in `custom_benchmark_v11.py`:**

```python
REASONING_PATTERNS = {"acemath", "deepseek", "gemma"}
```

Wird von `_get_model_config()` genutzt: Wenn `--thinking` aktiv ist UND der Modell-Key eines der REASONING_PATTERNS enthalt, wird `enable_thinking=True` gesetzt. `deepseek` hat standardmassig `enable_thinking=True`, `gemma` standardmassig `False` (umschaltbar via `--thinking`). Modelle mit explizitem `enable_thinking=False` (qwen3.6, qwen3.5) bleiben ausgeschlossen.

### 2.7 Task-Retry-Mechanismus (NEU in v10, nach Review)

```python
MAX_RETRIES = 3
for attempt in range(1, MAX_RETRIES + 1):
    try:
        result = benchmark_task(...)
        if result is not None:
            return result
    except Exception as e:
        if attempt < MAX_RETRIES:
            wait = 2 ** attempt  # exponentielles Backoff: 2s, 4s, 8s
            print(f"[RETRY] Versuch {attempt} fehlgeschlagen: {e}. Warte {wait}s...")
            time.sleep(wait)
        else:
            print(f"[FAIL] Alle {MAX_RETRIES} Versuche fehlgeschlagen.")
            return 0.0, f"Max retries exceeded: {e}"
```

### 2.8 Split: `--model_args` vs `--gen_kwargs` (Bugfix 11.07.)

**Problem (bis 10.07.):** `_get_lmeval_params()` legte alle Parameter (`max_tokens`, `temperature`, `top_p`, `min_p`, `until`, `extra_body`) in `--model_args`. Diese landeten im Konstruktor `LocalChatCompletion.__init__(**kwargs)` und wurden dort **stillschweigend ignoriert** (openai_completions.py:158 `**kwargs`). Der API-Payload verwendete stattdessen die `generation_kwargs` aus der Task-YAML (`max_gen_toks: 20` → nur 20 Tokens → 0% Score).

**Fix:** Aufteilung in zwei CLI-Parameter:

| Parameter | Empfänger | Enthält |
|-----------|-----------|---------|
| `--model_args` | `LocalChatCompletion.__init__()` | `base_url`, `model`, `num_concurrent`, `max_gen_toks` (Fallback), `eos_string` |
| `--gen_kwargs` | Evaluator merged in YAML `generation_kwargs` → API-Payload (via `**gen_kwargs` in `_create_payload()`) | `max_tokens`, `temperature`, `top_p`, `top_k`, `min_p`, `until`, `extra_body` |

**Wirkung:** `extra_body.chat_template_kwargs.enable_thinking` fließt jetzt erstmals in den LM-Studio-Request. `max_tokens` überschreibt YAMLs `max_gen_toks`. `temperature`/`top_p`/`min_p` werden korrekt gesetzt.

**Referenz:** `run_benchmarks_v13.py:709-754`, `openai_completions.py:189-206` (LocalChatCompletion._create_payload)

### 2.9 Fehlerbehandlung

| Fehler                  | Behandlung                              |
|-------------------------|-----------------------------------------|
| API-Timeout (120s)      | Score=0, Detail="Timeout/API-Fehler"    |
| SyntaxError im Code     | Score=0, Detail="Code-Fehler: ..."      |
| API-Fehler (z.B. 503)   | Retry bis zu 3x mit exponentiellem Backoff |
| Modell nicht ladbar     | Uberspringe Modell                      |
| Modell nach Custom-Bench entladen | Automatischer Reload + 10s Pause |
| UnicodeEncodeError      | PYTHONIOENCODING=utf-8 global gesetzt   |
| Granite Tiny Experts=64 | `ggml_new_object: not enough space` bei 1M Context; Workaround: Experts=16 setzen |

---

## 3. Aufgabenverteilung (v13 - 9 Benchmarks)

| Benchmark       | Custom (v13) | lm-eval | evalplus | Agentic |
|-----------------|:------------:|:-------:|:--------:|:-------:|
| DS1000          | **Ja**       | Nein    | Nein     | Nein    |
| CoderEval       | **Ja**       | Nein    | Nein     | Nein    |
| HumanEval+      | Nein         | Nein    | **Ja**   | Nein    |
| MBPP+           | Nein         | Nein    | **Ja**   | Nein    |
| MATH-500        | Nein         | **Ja**  | Nein     | Nein    |
| ARC-Challenge   | Nein         | **Ja**  | Nein     | Nein    |
| HellaSwag       | Nein         | **Ja**  | Nein     | Nein    |
| TruthfulQA      | Nein         | **Ja**  | Nein     | Nein    |
| Agentic         | Nein         | Nein    | Nein     | **Ja**  |

**Entfernt:** PandasEval (zu wenige/wenig aussagekraftige Aufgaben), BBH (zu teuer, 8x Multiplier), MMLU-Pro (zu teuer, 14 Subsets).

---

## 4. MATH-500 (ersetzt MathQA)

MATH-500 ist ein standardisierter Mathematik-Benchmark (500 Aufgaben aus dem MATH-Dataset). 
Er ersetzt MathQA (604 Multiple-Choice-Aufgaben), da MATH-500 eine bessere Abdeckung mathematischer 
Konzepte bietet und starker verbreitet ist.

**Pipeline:** `lm_eval --model local-chat-completions --tasks minerva_math500 --gen_kwargs ...` 
(Generation, keine Multiple-Choice). Extraktion der finalen Antwort via `\boxed{}`-Regex.

**Windows-SIGALRM-Bug (gefixt 15.07.):** Der originale `minerva_math500`-Task aus lm-eval verwendet 
`signal.SIGALRM` fur Timeouts in `is_equiv()` – existiert **nicht auf Windows**. Dadurch wurde JEDE 
Antwort als falsch gewertet (0.0% fur alle Modelle). **Fix:** Eigener Task in 
`lm_eval_tasks/minerva_math500/` mit SIGALRM-freiem `process_results()`: Extrahiert `\boxed{...}`-
Inhalt per Regex, normalisiert und vergleicht als String. Kein `math_verify`, kein `sympy.parse_latex` 
mit Signal-Timeout.

**MathQA (entfernt):** Früher genutzt (604 Multiple-Choice A-E). Ersetzt durch MATH-500 (offene Generierung).

---

## 5. Agentic-Pipeline

`run_agentic()` in `run_benchmarks_v13.py`:

```
tool_eval_bench CLI
├── --base-url http://127.0.0.1:1234/v1
├── --scenarios TC-XX ... (zufallig aus TOOL_EVAL_SCENARIO_IDS = TC-01..TC-69)
├── --json-file <agentic_<model>_<ts>.json>
├── --timeout 120 (pro Szenario)
├── --no-live (kein interaktives UI)
└── Ergebnis: final_score (0-100) aus JSON-Envelope, normalisiert auf 0-1
```

Timeout pro Szenario: `PIPELINE_TIMEOUTS["agentic_scenario"]` = 600s (10 Minuten)
Gesamtlaufzeit pro Modell: `PIPELINE_TIMEOUTS["agentic_subprocess"]` = 3600s (60 Minuten)

Die 600s pro Szenario verhindern das vorherige Problem, dass `tool_eval_bench` nach 120s den HTTP-Request abbrach, wahrend das Modell noch einen Tool-Call generierte. Bei sehr grossen Multi-Turn-Kontexten (>5000 Tokens) kann der Timeout bei Bedarf weiter erhoht werden.

### max_tokens-Reduktion in tool_eval_bench (2026-07-07)

**Problem (Ausloser):** Granite-4.1-30B (Q3_K_S) generiert 300-500 Tokens pro Tool-Call-Response (essayartige Erklarungen vor dem eigentlichen Tool-Call), bei ~5.2 tok/s. Mit 69 Szenarien und mehreren Runden pro Szenario reicht das 3600s-Gesamtlimit nicht.

**Fix:** `max_tokens` in `tool_eval_bench` von 4096 auf 512 gesenkt.

| Aspekt | Detail |
|--------|--------|
| Datei | `...\Python314\Lib\site-packages\tool_eval_bench\runner\orchestrator.py:379` |
| Wert | `max_tokens=4096` → `max_tokens=512` |
| Gültigkeit | **Global** – betrifft alle Modelle, die durch `tool_eval_bench` laufen |
| Effekt | Modell wird nach ~512 Tokens abgeschnitten, verhindert lange Erklarungen |
| Risiko | Bei Tool-Calls mit komplexen JSON/Code-Argumenten (>512 Tokens) könnten Aufrufe unvollständig sein. Die 69 TC-Szenarien nutzen aber nur einfache Calls (Name + 2-3 Argumente, weit unter 512 Tokens) |
| Wartung | Geht bei `pip install --upgrade tool_eval_bench` verloren, muss dann erneut angewendet werden |

**Bisherige Agentic-Timeout-Fälle:** Nur bei Granite-4.1-30B aufgetreten. Reasoning-Modelle (Qwen3 Coder Reap 25B, Gemma-4) durchliefen andere Pipelines (DS1000, CoderEval, lm-eval, evalplus) und waren nicht von diesem Timeout betroffen. Sollte ein weiteres Modell im Agentic timed out gehen, sind neben `max_tokens` auch die Timeout-Werte in `benchmark_config.py` (`agentic_subprocess`: 3600s, `agentic_scenario`: 600s) zu prüfen.

### --no-unload-between (NEU in v13)

Das `--no-unload-between`-Flag verhindert das Entladen/Nachladen zwischen Benchmarks desselben Modells. 
Standardmäßig wird nach jedem Benchmark das Modell entladen (um VRAM zu sparen). Mit `--no-unload-between` 
bleibt das Modell geladen – nützlich bei vielen kleinen Benchmarks, aber riskant bei Modellen knapp über 16 GB VRAM.

### registry_tool.py (NEU 14.07.)

**`registry_tool.py`** konsolidiert drei bisher separate Code-Stellen fur Registry- und JSON-Config-Wartung:

| Befehl | Herkunft | Funktion |
|--------|----------|----------|
| `compare` | Bisher embedded Python in `sync_model_configs.ps1` | Registry vs LMS vs JSON-Configs vergleichen |
| `add` | Bisher embedded Python in `sync_model_configs.ps1` | Neue LMS-Modelle in Registry aufnehmen (canonical Key = `publisher/model-name`) |
| `configs` | Bisher embedded Python in `sync_model_configs.ps1` | `load.fields` (offloadRatio, numParallelSessions) in JSON-Configs schreiben |
| `sync-ctx` | `sync_context_length.py` | `context_length` aus JSON-Configs in Registry uebernehmen |
| `fill-ctx` | `fmt_registry.py` | Fehlende `context_length: 16384` in der Registry erganzen (size-basierte Regel) |
| `fill-size` | **NEU 15.07.** | `file_size_bytes` aus LMS-Cache fur Registry-Eintrage ohne size erganzen |
| `migrate-keys` | **NEU 15.07.** | Eintrage ohne Publisher-Prafix auf `publisher/model-name` umstellen (119 Keys migriert) |
| `fmt` | `fmt_registry.py` | Leerzeilen normalisieren (keine innerhalb, eine zwischen Eintragen) |
| `sync` | Alle obigen | Full Maintenance: add → configs → sync-ctx → fill-ctx → fmt |

**Aufruf:**
```bash
python registry_tool.py sync          # Vollwartung
python registry_tool.py compare       # Nur Report
python registry_tool.py add <datei>   # Neue Modelle aus JSON-Datei
python registry_tool.py configs       # Nur load.fields schreiben
python registry_tool.py sync-ctx      # Nur context_length syncen
```

**`sync_model_configs.ps1`** wurde auf `registry_tool.py` umgestellt (kein embedded Python mehr). Die alten Skripte `sync_context_length.py` und `fmt_registry.py` sind Thin Wrapper, die an `registry_tool.py` delegieren.

### model_registry.yaml – Neue Felder (14.07.)

| Feld | Typ | Default | Beschreibung |
|------|-----|---------|-------------|
| `offload` | int (0-1) | 1 | GPU-Offload-Ratio (1 = voller GPU-Offload) |
| `num_parallel` | int | 1 (Dense) / 4 (MoE) | Max Concurrent Prediction Sessions |
| `context_length` | int | 16384 | Kontextlange aus JSON-Config (Default bei fehlendem Eintrag) |

**Leerzeilen-Formatierung:** Innerhalb eines Eintrags keine Leerzeilen, zwischen Eintragen genau eine. Wird automatisch von `registry_tool.py fmt` bzw. `save_registry()` in `registry_tool.py` sichergestellt.

### Reasoning-Parsing in LM Studio (2026-07-07)

**Problem (Ausloser):** Granite-4.1-30B generierte 300-500 Tokens pro Response, weil LM Studios `reasoning.parsing` mit `<think>`/`</think>`-Tags aktiviert war (Default bei vielen Modellen). Das Modell schreibt eine lange Gedankenkette vor jedem Tool-Call, bevor es die eigentliche Antwort produziert.

**Fix:** `reasoning.parsing.enabled` auf `false` gesetzt, globale Stop-Strings ergänzt, Context-Length an Pipeline angepasst.

| Aspekt | Detail |
|--------|--------|
| Datei | `...\.lmstudio\.internal\user-concrete-model-default-config\<publisher>\<model>\<model>.gguf.json` |
| Key | `llm.prediction.reasoning.parsing.enabled` |
| Alter Wert | `true` (Default) |
| Neuer Wert | `false` |
| Wirkung | Keine `<think>`-Blöcke mehr → ~50-70% weniger Tokens pro Generation |
| Stop-Strings | `["<|end_of_text|>", "<|endoftext|>"]` – stoppt Generation am EOS-Token |
| Context-Length | Von 49152 auf 16384 gesenkt (wie Pipeline-Vorgabe) |

**Betrifft ALLE Modelle in LM Studio:** Der `reasoning.parsing`-Default ist oft `true`. Bei Modellen ohne natives Reasoning (die keine `<think>`-Tags im Training haben) erzeugt dies unnötig lange Antworten. Es wird empfohlen, `reasoning.parsing.enabled` für alle Modelle auf `false` zu setzen, die in der Benchmark-Pipeline verwendet werden.

**LM Studio GUI-Pfad:** Chat Panel → Rechts oben "..." → "Model Settings" → "Reasoning Parsing" → Enabled aus.

---

## 6. System-Metriken

Werte aus **Per-Task-Peak-Werten des Monitor-Threads** (~5Hz Sampling wahrend aktiver Inferenz):

```python
def _peak_avg_max(key, min_val=0):
    vals = [r.get(key) for r in results if r.get(key) and r[key] > min_val]
    return sum(vals)/len(vals), max(vals)

_cpu_avg, _cpu_max = _peak_avg_max("cpu_during")
_gpu_avg, _gpu_max = _peak_avg_max("gpu_during")
_ram_avg_pct = avg(ram_during) / total_ram * 100
_vram_avg, _vram_max = _peak_avg_max("vram_during")
```

| Wert | Quelle | Einheit |
|------|--------|---------|
| CPU  | `psutil.cpu_percent(interval=0.3)` | % (ganze Zahl) |
| RAM  | `psutil.virtual_memory()` | % (ganze Zahl) |
| GPU  | `nvidia_smi` via subprocess | % (ganze Zahl) |
| VRAM | `lms ps --json` `gpuMemUsage` | GB (1 Dezimalstelle) |
| GPU-Temp | `nvidia_smi` | °C (Integer) |

**Speicherung in CSV (v10, nach Review):** CPU_avg, CPU_med, CPU_p90, GPU_avg, GPU_med, GPU_p90, RAM_avg, RAM_med, RAM_p90, VRAM_GB, GPU_Temp_max, GPU_Temp_p90.

Median und P90 ersetzen Mean/Max als robustere Metriken gegen Ausreisser.

---

## 7. DS1000-Evaluierung

`evaluate_code()` in `custom_benchmark_v13.py` durchlauft 4 Evaluierungs-Modi:

1. **DS1000-Harness** - falls `test_execution` im `code_context` vorhanden
2. **Namespace-Vergleich** - falls `reference_code` + `setup_code` vorhanden
3. **Reference als Tests** - falls `reference_code` ohne Tests
4. **Direkte Tests** - falls `tests`-Array vorhanden

**Wichtige Fixes:**
- `extract_code()`: JSON-Parsing-Shortcut fur strukturierten Output, dann Regex-Fallback mit `_is_bare_statement`-Fallback, Line-by-Line-Heuristik mit Break
- `_repair_indentation()`: iterative Heuristik fur fehlende Einruckungen + `pass`-Einfugung
- `_unwrap_solution_for_insert()`: entfernt `def`-Header bei `[insert]` in Funktions-Body
- Regex: `except(?: |:)` statt `except ` (bare `except:` nicht erkannt)
- **Strukturierter Output (v30):** `response_format` mit JSON-Schema garantiert valides JSON. `extract_code()` parst zunachst JSON, dann Regex. Eliminiert ~12% Parsing-Fehler (leere Antworten, Markdown-Extraktion).

**Harness-Fail:** Der DS1000-Harness fuhrt den generierten Code tatsachlich in einer Python-Sandbox aus. Ein "Harness-Fehler" bedeutet, dass der Code mit einem Laufzeitfehler (SyntaxError, NameError etc.) gecrasht ist. Kleine Modelle (Granite Tiny, Nerdsking) haben oft Syntax-Probleme bei Insertion-Aufgaben.

**Task-Retry (v10):** Bei API-Fehlern (z.B. LM Studio 503, Channel Error) wird die Aufgabe bis zu 3x wiederholt mit exponentiellem Backoff (2s, 4s, 8s).

---

## 8. exec-Sandbox

```
exec_sandboxed(code, timeout=30)
├── template = _build_sandbox_script(code, tests)
├── subprocess.run([sys.executable, "-c", template], timeout=30)
├── if returncode == 0 -> ok
└── else -> error aus stderr
```

**Blockierte Builtins:** eval, exec, open, input, compile, globals, locals, vars
**Blockierte Module:** os, subprocess, shutil, socket, http, urllib, ctypes, multiprocessing, threading

---

## 9. lm-eval Integration

| Task | Beschreibung |
|------|-------------|
| math500_gen | MATH-500 (Generation) |
| arc_challenge_chat | ARC-Challenge (Multiple Choice) |
| hellaswag_gen | HellaSwag (Multiple Choice) |
| truthfulqa_gen | TruthfulQA (Generation) |

**Modell-ID:** `model = model_info.get("_api_model") or model_key` - exakte ID aus `lms ps`.

**Parameter pro Modellklasse (via `--gen_kwargs`) (v13):**

| Klasse | temperature | top_p | max_tokens | enable_thinking | Besonderheit |
|--------|-------------|-------|------------|-----------------|--------------|
| Default | 0.0 | 1.0 | 1024 | None | greedy |
| Reasoning | 0.1 | 0.9 | - | per `--thinking` | min_p=0.02, Timeout x2 |
| Gemma 4 | 0.0 | 1.0 | 4096 | per `--thinking` | Thinking aktivierbar fur MATH-500 |
| Qwen3.6 | 0.1 | 0.9 | 8192 | False (erzwungen) | Thinking-Tokens blockieren Token-Budget |
| GPT-OSS | 1.0 | 1.0 | 4096 | None | temperature=1.0, top_k=0, until=`<|return|>`/`<|call|>` |
| Qwen3.5 | 0.2 | 0.9 | - | False (erzwungen) | top_k=20, no_system_msg |

**Wichtig (v13):** `--thinking` hat NUR Wirkung bei:
- **Gemma 4** (fur MATH-500) – aktiviert `<|channel>thought` Tags
- **Reasoning-Modelle** (erkannt via Name: reasoning/think/r1) – erhoht Timeout ×2
- **Alle anderen Modelle** (Qwen3.6, GPT-OSS, Qwen3.5) – `--thinking` wird ignoriert, da `enable_thinking=False` erzwungen wird

---

## 10. evalplus Integration

**Gepatche Datei: `openai_request.py`**

| Anderung              | Vorher       | Nachher     | Grund                                  |
|-----------------------|--------------|-------------|----------------------------------------|
| `max_tokens` default  | 512          | **4096**    | Reasoning-Modelle brauchen mehr Tokens |
| API-Parameter         | `max_completion_tokens` | **`max_tokens`** | LM Studio versteht `max_tokens` |

**id_range:** `evalplus.codegen --id-range [0,sample_size]` (exklusives Ende).

---

## 11. CSV-Output (csv_writer.py)

Einheitliches Schema fur ALLE Pipelines:

```
pipeline;bench;model;score;thinking;cpu_avg;cpu_med;cpu_p90;gpu_avg;gpu_med;gpu_p90;ram_avg;ram_med;ram_p90;vram_gb;gpu_temp_max;gpu_temp_p90
custom;DS1000;Phi-4;0.45;0;35;33;40;42;40;46;32;30;35;12.3;67;65
evalplus;HumanEval+;Phi-4;0.82;0;28;26;32;38;36;42;30;28;33;11.8;62;60
lmeval;MATH-500;Phi-4;0.67;1;31;29;36;40;38;44;31;29;34;12.0;64;62
agentic;Agentic;Phi-4;0.55;0;33;31;38;39;37;43;30;28;32;11.9;63;61
```

**Delimiter:** `;` (Semikolon, Komma-kompatibel fur deutsche Excel)
**Encoding:** utf-8
**Zwischenzusammenfassung:** `csv_writer.write_accumulative_summary()` nach jedem Modell
**Konsolidierung:** `csv_writer.write_konsolidiert_aktuell()` am Ende (nur bei >1 Modell)

### Dateinamen-Schema:

| Datei | Muster | Beispiel |
|-------|--------|----------|
| Per-Task-Rohdaten | `tasks_{ts}_{bench}_{model}.csv` | `tasks_20260628_093326_DS1000_Granite 4.0 H Tiny.csv` |
| Modell-Zusammenfassung | `model_{ts}_{model}.csv` | `model_20260628_093326_Granite 4.0 H Tiny.csv` |
| Konsolidiert (CSV) | `konsolidiert_{ts}.csv` | `konsolidiert_20260628_094051.csv` |
| Konsolidiert (MD) | `konsolidiert_{ts}.md` | `konsolidiert_20260628_094051.md` |
| **Konsolidiert aktuell** | `konsolidiert_aktuell.csv` | Immer die neueste Gesamtuebersicht (wird von `write_konsolidiert_aktuell()` ueberschrieben) |

**CSV-Dateinamen-Regel (v10):** Der vollstaendige `model_key` (inkl. Quant-Variante) wird als Dateiname verwendet, max. 50 Zeichen. Bei Namenskollisionen wird ein Suffix `_1`, `_2` etc. angehaengt.

---

## 12. Konsolidierung (consolidate_results_v13.py)

```
consolidate_results_v13.py
├── find_latest_csv(pattern)
├── read_evalplus(model_key)
├── read_lmeval_per_model(model_key)
├── ModelData-Dataclass (typisierte Zeilen statt roher Dicts)
├── compute_category_scores(bench_scores)
│   ├── Coding  (35%): HumanEval+, MBPP+, DS1000, CoderEval
│   ├── Math    (25%): MATH-500
│   ├── Agentic (25%): Agentic
│   └── Knowledge (15%): ARC, HellaSwag, TruthfulQA
├── Overall = Coding + Math + Agentic + Knowledge (normalisiert auf 100%)
├── System-Metriken: median/p90 statt mean/max
├── _threshold_filtered() fur TOP Coding (>=60%)
├── _b5_named() fur BOTTOM 5
├── _fmt_pct() mit {:.0f}% (ganze Zahlen)
├── fn_csv mit median/p90-Spalten (CPU_med, CPU_p90, GPU_med, GPU_p90, ...)
├── thinking-Spalte (0/1) in allen Pipeline-returns, CSVs und Konsolidierung
├── bootstrap_ci(scores, n_resamples=10000) – Bootstrap-95%-KI fuer DS1000/CoderEval aus Per-Item-Daten (immer aktiv)
│   ├── ds1000_ci_lo / ds1000_ci_hi / codereval_ci_lo / codereval_ci_hi in CSV
│   └── Format im MD: "XX% [lo–hi]"
├── paired_bootstrap_ci() – Gepaarter Bootstrap-Vergleich fuer2+ Modelle
│   ├── compare_two_quants() berechnet Differenz, CI, p-value
│   └── Alle Paarvergleiche via itertools.combinations
├── read_paired_scores() – Matcht Tasks nach task_index (gleiche Items)
├── write_quant_comparison() in csv_writer.py – CSV + MD Output
├── --compare "key1,key2,key3" – Automatische Paarvergleiche
├── --seed – Reproduzierbares Bootstrap
├── --models – Modell-Filter
├── --compare-benchmark DS1000|CoderEval|all
├── width-Duplizierung entfernt (nur noch ein widths-Block)
└── generate CSV + MD (alphabetisch sortiert)
```

### Gewichtung (v10)

| Kategorie | Anteil | Benchmarks |
|-----------|--------|------------|
| Coding    | 35%    | HumanEval+ (25%), MBPP+ (25%), DS1000 (25%), CoderEval (25%) |
| Math      | 25%    | MATH-500 (100%) |
| Agentic   | 25%    | Agentic (100%) |
| Knowledge | 15%    | ARC (33.3%), HellaSwag (33.3%), TruthfulQA (33.3%) |
| **Overall** | **100%** | Summe aller vier Kategorien |

### ModelData-Dataclass (NEU in v10, nach Review)

```python
@dataclass
class ModelData:
    model_name: str
    scores: dict[str, float]
    system_metrics: dict[str, float]
    laufzeit_h: float
    eff: float
    toks: float
    vram: float
    quant: str
    cpu_med: float
    cpu_p90: float
    gpu_med: float
    gpu_p90: float
    ram_med: float
    ram_p90: float
    gpu_temp_p90: float
    gpu_temp_max: float
    cpu_avg: float
    gpu_avg: float
    cpu_max: float
    gpu_max: float

    def to_csv_dict(self) -> dict[str, str]:
        ...
```

---

## 13. Benchmark-Quellen

| Dataset           | Quelle github                | Aufgaben               | Referenz            |
|-------------------|-------------------------------|------------------------|---------------------|
| **DS1000**        | `xlangai/DS-1000` (HF)        | 5 Libraries (N Tasks)  | Lai et al. 2023     |
| **CoderEval**     | Manuell kuratiert (self_contained+slib_runnable) | ~138 Tasks | CoderEval 2023 |
| **HumanEval+**    | evalplus                      | 164 Funktionen         | Liu et al. 2023     |
| **MBPP+**         | evalplus                      | 378 Algorithmen        | Liu et al. 2023     |
| **MATH-500**      | openai/gsm8k (HF)             | 500 Aufgaben           | Hendrycks et al. 2021 |
| **ARC-Challenge** | lm-eval built-in              | 259 Aufgaben           | Clark et al. 2018   |
| **HellaSwag**     | lm-eval built-in              | 10042 Aufgaben         | Zellers et al. 2019 |
| **TruthfulQA**    | lm-eval built-in              | 817 Aufgaben           | Lin et al. 2021     |
| **Agentic**       | tool-eval-bench (HF: `aisafety-ai/tool_eval_bench`) | 69 Szenarien | -- |

---

## 14. Dateistruktur (Projekt)

```
Benchmarks/
├── benchmark_config.py              # Zentrale Konfiguration (Gewichte, Subsets, Szenarien)
├── model_manager.py                 # Modell-Management (unversioniert)
├── csv_writer.py                    # CSV-Schema (unversioniert) + write_quant_comparison()
├── custom_benchmark_v13.py          # Aktuelle Custom-Pipeline (DS1000 + CoderEval, strukturierter Output)
├── run_benchmarks_v13.py            # Aktueller Launcher (v13), dynam. Script-Aufloesung, --seed
├── consolidate_results_v13.py       # Aktuelle Konsolidierung (--compare, --models, immer-CI)
├── registry_tool.py                 # Registry + JSON-Config-Wartung (konsolidiert)
├── sync_context_length.py           # Thin Wrapper → registry_tool.py sync-ctx
├── fmt_registry.py                  # Thin Wrapper → registry_tool.py fill-ctx / fmt
├── generate_quant_map.py            # QUANT_MAP-Generator (auto-generiert)
├── check_agentic.py                 # Agentic-Diagnose
├── download_real_benchmarks.py      # Datensatz-Download
├── download_codereval.py            # CoderEval-Download
├── tests/
│   ├── __init__.py
│   ├── test_scores.py               # 10 Tests: compute_category_scores, Percentile
│   ├── test_csv.py                  # 5 Tests: read_custom_csv, auto_delimiter
│   └── fixtures/
│       └── test_tasks.csv           # Testdaten
│
├── simple_evals/                    # JSONL-Datensaetze (DS1000, CoderEval)
├── lm_eval_tasks/                   # Custom YAML-Tasks
│   ├── hellaswag_gen.yaml           # HellaSwag mit Chat-Prompt + Regex-Extraktion
│   ├── mathqa_gen/                  # MathQA (Multi-Choice) – Custom YAML + utils.py
│   └── minerva_math500/             # MATH-500 – SIGALRM-freie Windows-Version (15.07.)
├── Doku+Install/                    # Dokumentation
├── ergebnisse/                      # Ergebnisse + Konsolidierung
├── ds1000_official/                 # DS-1000-Framework (Windows-Patches)
├── Archiv/alte_py_skripte/          # Archivierte Skripte (alte Wrapper, One-offs)
└── doc-git/                         # Dokumentation
```

**Migrationspfad beim Kopieren einer neuen Version:**
Es genugt `Copy-Item custom_benchmark_v13.py custom_benchmark_v14.py`. Der Launcher erkennt dynamisch die hochste Version. Kein manuelles Update des Launchers notig.

---

## 15. Wichtige Konstanten

### Aus model_manager.py

| Konstante                   | Wert   | Zweck                             |
|-----------------------------|--------|-----------------------------------|
| `API_BASE`                  | `http://127.0.0.1:1234/v1` | LM Studio API      |
| `TIMEOUT_HTTP`              | 120 s  | HTTP-Request Timeout              |
| `TIMEOUT_CLI`               | 30 s   | CLI-Subprozess-Timeout            |
| `TIMEOUT_LOAD_MODEL`        | 180 s  | Modell-Lade-Timeout               |

### PIPELINE_TIMEOUTS (in model_manager.py)

| Key                     | Default | Verwendung                                                    |
|-------------------------|---------|---------------------------------------------------------------|
| `custom_subprocess`     | 3600    | Subprozess-Timeout DS1000/CoderEval (run_custom_benchmark)    |
| `evalplus_base`         | 600     | Basis-Timeot codegen+evaluate (×2 bei Reasoning)              |
| `lmeval_base`           | 600     | Basis-Timeot lm_eval (×2 bei Reasoning)                       |
| `agentic_subprocess`    | 3600    | Gesamtlaufzeit-Timeout tool_eval_bench                        |
| `agentic_scenario`      | 600     | Timeout pro Szenario (--timeout an tool_eval_bench)           |

Alle Pipelines importieren ihre Timeouts zentral aus `PIPELINE_TIMEOUTS`.
Aenderungen muessen NUR in `model_manager.py` erfolgen – kein Suchen nach Hardcodeds mehr noetig.

### Aus benchmark_config.py (NEU in v10, nach Review)

| Konstante                 | Wert                       | Zweck                          |
|---------------------------|----------------------------|--------------------------------|
| `CAT_WEIGHTS`             | `{"Coding": 0.35, "Math": 0.25, "Agentic": 0.25, "Knowledge": 0.15}` | Kategorie-Gewichtung |
| `OVERALL_WEIGHTS`         | `{"Coding": {"HumanEval+": 0.25, "MBPP+": 0.25, "DS1000": 0.25, "CoderEval": 0.25}, ...}` | Benchmark-Gewichtung pro Kategorie |
| `TOOL_EVAL_SCENARIO_IDS`  | TC-01..TC-69               | Agentic-Szenarien              |
| `EXCLUDE_KEYWORDS`        | whisper, vision, ocr, transcription, translat, audit, audio, embed, vl | Ausgeschlossene Modalitaeten |
| `REASONING_KEYWORDS`      | ["reasoning", "think", "r1"] | Reasoning-Erkennung          |
| `QUANT_MAP`               | Dict model_key -> Quant-Bezeichnung (statisch, ~45 Eintraege) | Quant-Zuordnung fuer CSV und Anzeige. Quelle-Prioritaet: QUANT_MAP > `lms ls --json` > Config-Dateien > GGUF-Cache. Auto-generierbar via `generate_quant_map.py` |
| `PIPELINE_DISCOVERY`      | Glob-Pattern + Version-Regex | Dynamische Script-Erkennung  |
| `CUSTOM_BENCHMARK_SCRIPT` | dynamisch via `glob()`     | Hochste `custom_benchmark_v*.py` |

**Entfernt in v29:** `DISPLAY_NAMES` + `WHITELIST` – ersetzt durch dynamische Auto-Discovery:
- **Modell-Auswahl** (`consolidate_results_v13.py`): Iteriert automatisch uber alle Modell-Keys aus den Ergebnis-CSVs. Optionaler Filter via `--models key1,key2`.
- **Anzeigenamen**: Werden live aus `lms ls --json` (Feld `displayName`) abgefragt, Fallback = lesbare Key-Transformation.
- **QUANT_MAP-Generator** (`generate_quant_map.py`): Holt alle Keys dynamisch aus `lms ls --json` + Ergebnis-CSVs, kein statischer Import mehr aus `benchmark_config.py`.
- Hintergrund: Whitelist war redundant (Auswahl auch interaktiv/CLI moeglich), DISPLAY_NAMES durch dynamische Quellen ersetzbar.

---

## 16. Type Hints (NEU in v10, nach Review)

Alle 3 Hauptskripte haben vollstandige Type Hints:

| Skript | Funktionen | Importe |
|--------|-----------|---------|
| `custom_benchmark_v13.py` | 55 Funktionen | `from collections.abc import Generator` |
| `run_benchmarks_v13.py` | 20 Funktionen | `from collections.abc import Iterator` |
| `consolidate_results_v13.py` | 27 Funktionen | `from dataclasses import dataclass`, `from collections.abc import Callable` |

**Beispiele:**

```python
# custom_benchmark_v13.py
def evaluate_generated_code(
    generated_code: str,
    entry_point: str,
    tests_field: Any,
    reference_code: str = "",
    setup_code: str = ""
) -> tuple[float, str]:
    ...

# run_benchmarks_v13.py
def run_benchmarks(
    models: list[str],
    benchmarks: list[str],
    sample_size: int
) -> list[dict[str, Any]]:
    ...

# consolidate_results_v13.py
@dataclass
class ModelData:
    model_name: str
    scores: dict[str, float]
    ...
    def to_csv_dict(self) -> dict[str, str]:
        ...
```

---

## 17. Tests (NEU in v10, nach Review)

15 pytest-Tests in `tests/`:

| Datei | Tests | Getestete Funktionen |
|-------|-------|----------------------|
| `test_scores.py` | 10 | `compute_category_scores()`, `_percentile()`, `_threshold_filtered()`, `_b5_named()` |
| `test_csv.py` | 5 | `read_custom_csv()`, `auto_delimiter_erkennung()`, CSV-Parsing mit Fixtures |

**Ausfuhrung:**
```
pytest tests/ -v
```

**Test-Framework:** pytest ohne zusatzliche Plugins. Fixtures in `tests/fixtures/test_tasks.csv`.

---

## 18. Bekannte Einschrankungen

1. **Varianten-Selektion via CLI:** `lms load` hat KEIN Flag, um eine bestimmte Quantisierung zu laden. `--yes` laedt immer die erste/bevorzugte Variante. Bei 2+ Quants des gleichen Modells wird eine Warnung ausgegeben, die Variante muss via LM Studio GUI oder Deinstallation der unerwuenschten Variante gewaehlt werden.
1. **DS1000-Score konservativ:** ~50% der Tasks nicht standalone ausfuhrbar (Harness-Fail).
2. **evalplus ohne Docker:** Gleiches Sicherheitsrisiko wie eigene Sandbox.
3. **Kein logprobs:** LM Studio bietet keinen Zugriff auf Token-Wahrscheinlichkeiten.
4. **Thinking-Token-Extraktion:** `<think>...</think>` wird gestripped.
5. **lm-eval Regex:** `mmlu_pro_*` extrahiert nur Buchstaben `[A-E]`. Seit 11.07.: `mathqa_gen` + `hellaswag_gen` unterstutzen auch Kleinbuchstaben `[a-e]`, `[a-d]`.
6. **Windows cp1252-Encoding:** `PYTHONIOENCODING=utf-8` global gesetzt.
7. **`lms unload --all` unzuverlassig:** Node-Prozesse bleiben manchmal aktiv.
8. **MMLU-Pro modifiziert (entfernt in v13):** Wurde durch MATH-500 ersetzt. MMLU-Pro war zu teuer (14 Subsets) und lieferte wenig Differenzierung.
9. **API-Bereitschaft:** `time.sleep(10)` ist ein Hack; bei sehr grossen Modellen (>30B) kann die Initialisierung langer dauern.
10. **GLM 4.7 Flash:** Nicht lauffahig auf 16 GB VRAM (GPU Thrashing).
11. **Gemma 4 19B:** Benotigt deaktivierte KV-Quant zum Laden.
12. **Granite 4.0 H Tiny:** Experts=64 verursacht `ggml_new_object: not enough space` bei 1M Context. Workaround: Experts=16 setzen. Der `num_experts`-Parameter ist nur uber LM Studio Python SDK/REST API setzbar, nicht im GUI.
13. **numExperts (MoE-Modelle):** In `model_registry.yaml` unterscheiden: `experts:` = LMS-Einstellung (reduziert wegen VRAM), `notes:` enthalt den Architekturwert (aus Steckbriefen). Die `user-concrete-model-default-config`-JSONs speichern den LMS-Wert als `llm.load.numExperts`.
14. **Dynamische Script-Auflosung:** Der Launcher lost den Custom-Benchmark-Pfad nur beim Start auf. Wird die Datei wahrend des Laufs ersetzt, lauft die alte Version bis zum Ende.
20. **Windows SIGALRM (minerva_math500):** Der originale lm-eval-Task `minerva_math500` verwendet `signal.SIGALRM` fur Timeouts bei `is_equiv()`. Auf Windows wird dadurch jede Antwort als falsch gewertet (0.0%). Workaround: Eigener Override in `lm_eval_tasks/minerva_math500/` mit SIGALRM-freiem `process_results()`.
15. **Agentic-Szenario-Timeout:** `PIPELINE_TIMEOUTS["agentic_scenario"]` (600s) verhindert Timeout-Abbrueche bei langen Kontexten (vorher: 120s Hardcoded -> Abbruch bei Tool-Call-Generierung).
16. **model.yaml-Konflikt:** Ein virtuelles Modell via `hub/models/<publisher>/<model>/model.yaml` kollidiert mit einer bereits geladenen physischen Instanz derselben GGUF-Datei → llama.cpp stuerzt mit HTTP 500 ab. Workaround: model.yaml nur fuer Modelle ohne physische Instanz (z.B. mradermacher/qwen3-coder-reap).
17. **MATH-500 statt MathQA:** MathQA wurde durch MATH-500 ersetzt (bessere Abdeckung, standardisierter). MMLU-Pro entfernt (zu teuer, 14 Subsets).
18. **`--no-unload-between`:** Standardmäßig aus. Nützlich bei vielen kleinen Benchmarks, spart Ladezeit.
19. **`--exclude-benchmarks`:** Erlaubt Ausschluss einzelner Benchmarks (z.B. `--exclude-benchmarks agentic,custom`).
20. **Consolidate Bugfixes (15.07.):** `find_latest_csvs` paart DS1000/CoderEval jetzt per `model_key` statt rohem Timestamp; Directory-Scan in `read_data` wird bei `--since` ubersprungen; `--merge` ohne `--runs` setzt `all_runs=True` statt `merge_runs=2`; IFEval-Metriken (`prompt_level_strict_acc,none` etc.) zur METRICS-Liste erganzt.

---

## 19. Wichtige Benchmark-Ergebnisse (Stand 30.06.2026)

### Granite 4.0 H Tiny (SampleSize=10, Experts=16, Q8_0, 7.4 GB VRAM)

| Benchmark | Score |
|-----------|-------|
| DS1000 | 10% (1/10, 9x Harness-Fail) |
| CoderEval | 55% |
| HumanEval+ | 100% |
| MBPP+ | 50% |
| ARC-Challenge | 40% |
| HellaSwag | 70% |
| TruthfulQA | 30% |
| MMLU-Pro | 64.3% |
| MathQA | 40% |
| Agentic | 85% |
| **Coding** | **53.8%** |
| **Knowledge** | **51.1%** |
| **Math** | **40.0%** |
| **Overall** | **57.7%** |
| **Effizienz** | **60.5 %p/h (TOP 1!)** |
| tok/s | 12.7 (TOP 2) |
| Laufzeit | 0.6h (36 min) |

### Nerdsking Python Coder 7B (SampleSize=10, Q8_0, 8.1 GB VRAM)

| Benchmark | Score |
|-----------|-------|
| DS1000 | 20% |
| CoderEval | 60% |
| HumanEval+ | 100% |
| MBPP+ | 57.1% |
| ARC-Challenge | 10% |
| HellaSwag | 70% |
| TruthfulQA | 50% |
| MMLU-Pro | 38.5% |
| MathQA | 20% |
| Agentic | 20% |
| **Coding** | **59.3%** |
| **Knowledge** | **42.2%** |
| **Math** | **20.0%** |
| **Overall** | **37.3%** |
| **Effizienz** | **28.9 %p/h (TOP 2)** |
| tok/s | 19.9 (TOP 1) |
| Laufzeit | 0.8h (48 min) |

### Qwen3 Coder REAP 25B (SampleSize=5, IQ4_XS, 16K Context – begrenzt wegen VRAM)

| Benchmark | Score |
|-----------|-------|
| CoderEval | 60% |
| HumanEval+ | 95% |
| MBPP+ | 71% |
| HellaSwag | 80% |
| Agentic | 80% |
| **Effizienz** | **17.1 %p/h** |
| tok/s | 3.3 |
| Laufzeit | 2.5h |

### Qwen3.6 27B (SampleSize=5, Q3_K_S, 262K Context)

**Hinweis:** `enable_thinking=False` (API-Parameter) noetig, da Thinking-Tokens das Token-Budget (2048) verbrauchen und zu 0% Custom-Benchmarks fuehren. LM Studio GUI-Option "Parsing von Begründungsabschnitten" ist inkompatibel.

| Benchmark | Score |
|-----------|-------|
| MMLU-Pro | 80% |
| Agentic | 90% |
| Custom-Benchmarks | 0% (wenn enable_thinking nicht deaktiviert) |

---

## 20. Versions-Changelog

| Datum  | Datei                                         | Anderung                                                                        |
|--------|-----------------------------------------------|---------------------------------------------------------------------------------|
| 12.07. | `Architektur+Flow_v25.md`                     | v33: v12→v13, MATH-500 ersetzt MathQA, MMLU-Pro entfernt, --no-unload-between, --exclude-benchmarks, Dokumentation aktualisiert |
| 12.07. | `run_benchmarks_v13.py`                       | v13 aus v12: MATH-500 statt MathQA, MMLU-Pro entfernt, `--no-unload-between`, `--exclude-benchmarks` |
| 12.07. | `custom_benchmark_v13.py`                     | v13 aus v12: MODEL_CONFIG aktualisiert (--thinking nur fur Gemma MATH-500/Reasoning) |
| 12.07. | `consolidate_results_v13.py`                  | v13 aus v12: MATH-500 statt MathQA, MMLU-Pro entfernt aus Gewichtung |
| 08.07. | `Architektur+Flow_v24.md`                     | v32: --gpu max/-c entfernt, Pre-Config-JSONs, numExperts-Klarstellung |
| 07.07. | `Architektur+Flow_v24.md`                     | v31: Varianten-eindeutige Keys, resume=False, load_key/lms load Fix, Warnung bei Varianten-Mismatch |
| 07.07. | `run_benchmarks_v12.py`                       | model_info["key"] variant-eindeutig, load_key getrennt, Warnung bei Varianten-Mismatch |
| 07.07. | `custom_benchmark_v12.py`                     | get_available_models() variant-eindeutige Keys + variants[] |
| 07.07. | `model_manager.py`                            | load_model_via_lms() mit --gpu max (CPU-Offloading-Fix) |
| 08.07. | `model_manager.py`                            | --gpu max und -c entfernt; Kontextlange/GPU-Steuerung uber Pre-Config-JSONs |
| 07.07. | `consolidate_results_v12.py`                  | _get_model_info() variant-eindeutig; Fallback auf base-Key fuer alte Ergebnisse |
| 07.07. | `csv_writer.py`                               | model_key in Dateinamen jetzt variant-eindeutig |
| 05.07. | `Architektur+Flow_v24.md`                     | v30: Strukturierter Output, Paired Bootstrap, --seed, --compare, --bootstrap entfernt |
| 05.07. | `custom_benchmark_v12.py`                     | Strukturierter Output: response_format mit JSON-Schema, extract_code() JSON-Shortcut |
| 05.07. | `run_benchmarks_v12.py`                       | --seed, --no-structured-output an Subprocess weitergegeben |
| 05.07. | `consolidate_results_v12.py`                  | --compare mit2+ Modellen, --seed, --models, immer-CI (kein --bootstrap) |
| 05.07. | `csv_writer.py`                               | write_quant_comparison() fuer CSV + MD Output |
| 05.07. | `Architektur+Flow_v24.md`                     | v29: DISPLAY_NAMES/WHITELIST entfernt, Auto-Discovery, Bugfixes |
| 05.07. | `benchmark_config.py`                         | ENTFERNT: DISPLAY_NAMES + WHITELIST; NEU: EXCLUDE_KEYWORDS zentralisiert |
| 05.07. | `consolidate_results_v12.py`                  | Auto-Discovery aus Ergebnis-CSVs; `--models` CLI-Arg; Bugfixes |
| 05.07. | `generate_quant_map.py`                       | Keys dynamisch via `lms ls --json` + Result-CSVs |
| 05.07. | `run_benchmarks_v12.py`                       | v12 aus v11: Stale Refs gefixt, Config-Imports zentralisiert |
| 05.07. | `custom_benchmark_v12.py`                     | v12 aus v11: Stale Refs gefixt, EXCLUDE_KEYWORDS aus Config |
| 05.07. | `model_manager.py`                            | German/English-Mix bereinigt |
| 04.07. | `Architektur+Flow_v24.md`                     | Thinking-Mode fur alle Reasoning-Modelle, REASONING_PATTERNS, enable_thinking-Tabelle |
| 15.07. | `Architektur+Flow_v24.md`                     | p5: MATH-500 SIGALRM-Fix (lm_eval_tasks/minerva_math500/), registry_tool.py fill-size/migrate-keys, Orphan mradermacher/qwen3-30b-a3b-python-coder, consolidate Bugfixes (DS1000/CoderEval pairing, --merge default, IFEval-Metriken) |
| 14.07. | `Architektur+Flow_v24.md`                     | p4: registry_tool.py, new CLI args in consolidate, offload/num_parallel in Registry, Blank-Line-Formatting |
| 14.07. | `registry_tool.py`                            | **NEU:** Konsolidiert sync_model_configs.ps1-embedded-Python + sync_context_length.py + fmt_registry.py |
| 14.07. | `sync_model_configs.ps1`                      | Rewrite: ruft registry_tool.py statt embedded Python; neuer Schritt 4 (configs) |
| 14.07. | `fmt_registry.py`                             | Rewrite: Thin Wrapper → registry_tool.py; Modul-Funktionen dorthin verlagert |
| 14.07. | `sync_context_length.py`                      | Rewrite: Thin Wrapper → registry_tool.py sync-ctx |
| 14.07. | `assemble_blueprint.py`                       | Ruft `format_blank_lines()` nach `classify_registry()` (automatische Leerzeilen-Normalisierung) |
| 14.07. | `model_registry.yaml`                         | 46 Eintrage mit `context_length: 16384` befullt; offload+num_parallel in allen Eintragen; Leerzeilen formatiert; duplicate-key `deepseek-coder-33b-instruct-i1` bereinigt |
| 14.07. | `consolidate_results_v13.py`                  | Neue CLI: --merge, --since, --until, --all-runs, --no-installed; Default: installed-only + latest-run |
| 04.07. | `custom_benchmark_v12.py`                     | REASONING_PATTERNS-Set, `--thinking` aktiviert Thinking fur AceMath+DeepSeek+Gemma |
| 04.07. | `run_benchmarks_v12.py`                       | `_get_lmeval_params()` Thinking fur Reasoning+Gemma bei MathQA/MMLU-Pro |
| 30.06. | `Architektur+Flow_v24.md`                     | Update: QUANT_MAP, qwen3.6-Klasse, konsolidiert_aktuell.csv, Qwen3/Qwen3.6-Ergebnisse |
| 28.06. | `run_benchmarks_v10.py`                       | Launcher v10 (vorher v7): Type Hints, all_summary-Bugfix, API_BASE aus model_manager, Task-Retry, MMLU-Pro-Helper |
| 28.06. | `custom_benchmark_v10.py`                     | Custom v10 (vorher v24): Type Hints, Task-Retry, kein PandasEval, kein interaktiver Modus |
| 28.06. | `consolidate_results_v10.py`                  | Konsolidierung v10 (vorher v8): Type Hints, ModelData-Dataclass, median/p90-Spalten, width-Duplizierung entfernt |
| 11.07. | `run_benchmarks_v12.py`                       | **Bugfix: lm_eval-Parameter via `--gen_kwargs` statt `--model_args`**; `eos_string` nur fur GPT-OSS; HellaSwag `min_limit=100` |
| 11.07. | `lm_eval_tasks/mathqa_gen/mathqa_gen.yaml`   | `max_gen_toks: 20→512`; Regex `[ABCDE]→[A-Ea-e]`; Pfade relativ |
| 11.07. | `lm_eval_tasks/hellaswag_gen.yaml`            | `max_gen_toks: 20→100`; Regex `[ABCD]→[A-Da-d]`; `>-→\|` (Newlines) |
| 11.07. | `lm_eval_tasks/mathqa_gen/utils.py`           | `process_docs()` Regex robuster bei Komma-Werten |
| 28.06. | `model_manager.py`                            | Versionierung entfernt (vorher _v2); API_BASE zentral; PIPELINE_TIMEOUTS beibehalten |
| 28.06. | `csv_writer.py`                               | Versionierung entfernt (vorher _v2); fn_csv um median/p90 erweitert             |
| 28.06. | `benchmark_config.py`                         | NEU: Zentrale Konfiguration fur CAT_WEIGHTS, OVERALL_WEIGHTS, MMLU_PRO_SUBSETS, TOOL_EVAL_SCENARIO_IDS, DISPLAY_NAMES |
| 05.07. | `benchmark_config.py`                         | ENTFERNT: DISPLAY_NAMES + WHITELIST – durch dynamische Auto-Discovery ersetzt |
| 05.07. | `consolidate_results_v12.py`                  | WHITELIST-Loop -> Auto-Discovery aus Ergebnis-CSVs; `_lookup_vram(model_key)` statt DISPLAY_NAMES-Reverse-Lookup; neues `--models` CLI-Arg; `_get_display_name()` aus `lms ls --json` |
| 05.07. | `generate_quant_map.py`                       | Kein Import aus benchmark_config mehr; Keys dynamisch via `lms ls --json` + Result-CSVs |
| 28.06. | `tests/test_scores.py`                        | NEU: 10 Tests fur compute_category_scores, _percentile, _threshold_filtered     |
| 28.06. | `tests/test_csv.py`                           | NEU: 5 Tests fur read_custom_csv, auto_delimiter                                |
| 28.06. | `tests/fixtures/test_tasks.csv`               | NEU: Testdaten fur CSV-Parsing                                                  |
| 28.06. | `run_all_dense.py` / `rerun_*.py`             | Wrapper auf run_benchmarks_v12.py aktualisiert                                  |
| 28.06. | `review_20260628.md`                          | NEU in Doku+Install: Code-Review mit 9 Kritikpunkten und Empfehlungen           |
| 28.06. | `Doku+Install/Alte_Skripte/`                  | 17 historische Skripte verschrottet (v18-v22, v6-v7, v1-v6)                     |
| 27.06. | `model_manager.py / csv_writer.py`            | Versioniert als _v2; PIPELINE_TIMEOUTS-Dict                                     |
| 27.06. | `Architektur+Flow_v22.md`                     | v24-Architektur: v7/v24/v8/v2, dynamische Script-Auflosung                      |
| 27.06. | `model_manager_v2.py / csv_writer_v2.py`      | Kopien von unversionierten Dateien                                              |
| 26.06. | `model_manager.py`                            | `wait_for_model_ready`/`check_api_available` nicht mehr vom Launcher genutzt    |
| 26.06. | `benchmark_lmstudio_v22.py`                   | v21->v22: Systemmetrik-Fix: per-Task-Peak-Werte statt MetricsCollector (10s)   |
| 25.06. | `consolidate_results_v6.py`                   | Ganze Prozentzahlen, TOP-Coding Schwellwert, Systemmetriken als %                |
| 23.06. | `benchmark_lmstudio_v21.py`                   | MetricsCollector, CPU/GPU/RAM-Sampling (buggy)                                   |
| 19.06. | `model_manager.py`                            | **NEU:** Gemeinsames Modul fur Modell-Management                                 |
| 19.06. | `run_benchmarks_v3.py`                        | Import aus model_manager, _api_model-Mechanismus, id_range-Fix                   |
| 17.06. | `run_benchmarks_v1.py`                        | Erster Unified Launcher                                                          |
| 14.06. | `benchmark_lmstudio_v12.py`                   | Erste stabile Version mit 10 Benchmarks                                          |

---

*Erstellt: 28.06.2026 | Aktualisiert: 15.07.2026*
*Basiert auf: v13.0.0-p5 – MATH-500 SIGALRM-Fix, registry_tool.py fill-size/migrate-keys, consolidate Bugfixes*
*Bugfix 11.07.: lm_eval `--gen_kwargs` statt `--model_args` fur Generation-Parameter; HellaSwag/MathQA YAML-Fixes*
*Bugfix 15.07.: MATH-500=0.0% durch Windows-SIGALRM-Inkompatibilitat – eigener Task in lm_eval_tasks/minerva_math500/*
