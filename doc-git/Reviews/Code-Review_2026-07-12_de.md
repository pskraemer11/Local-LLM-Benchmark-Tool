# Code-Review – LLM Benchmark Suite
**Datum:** 12.07.2026
**Scope:** Aktiver Python-Code in der Projektwurzel + `doc-git/` + `Doku-intern/` + LM Studio Server-Logs (3 jüngste vom 12.07.2026)
**Methodik:** Statische Analyse + Cross-Reference mit README, Architektur-Doku, Steckbriefen und Log-Daten

**Prio-1-Fix-Status (12.07.2026):**
- ✅ `tests/test_csv.py:4` repariert: Import `v12` → `v13`, Fixture `tests/fixtures/test_tasks.csv` erstellt (31 Spalten via `csv.DictWriter` aus `TASK_FIELDS`)
- ✅ Channel-Error Auto-Fallback: `custom_benchmark.py` schreibt `[CHANNEL-ERROR]`-Marker bei "Cannot combine structured output" / "Channel Error"; `run_benchmarks.py:run_custom_benchmark` detektiert Marker und ruft sich rekursiv mit `no_structured_output=True` auf
- ✅ `wait_for_model_ready` Timeout 30s → 60s: in `run_benchmarks.py` (3 Stellen: Initial-Load, Reload zwischen Benchmarks, Reload nach Custom); Default `TIMEOUT_MODEL_READY` 90s → 120s in `model_manager.py` als Sicherheitsnetz
- ✅ Reload-Logik auf alle 4 Pipelines ausgedehnt: `_ensure_model_still_loaded()` Helper-Funktion in `run_benchmarks.py:469` extrahiert, wird nach **jedem** Benchmark aufgerufen (nicht mehr nur `is_custom`); ungenutzte Variable `is_custom` entfernt
- ✅ Test-Suite: `pytest tests/` → **15/15 passed** (vorher: 9/15 funktional, da 6/6 in `test_csv.py` kaputt)

**Prio-2-Fix-Status (12.07.2026):**
- ✅ **D1: `_lookup_vram` Fuzzy-Match**: Substring-Match durch Length-Ratio-Guard ersetzt (>=0.85); Publisher-Prefix-Liste erweitert (ibm/google/microsoft/mistralai/essentialai/qwen/lmstudio-community/openai/mradermacher/jetbrains/unsloth/modelgraft/fb/meta/deepseek/cerebras/moonshotai/zai-org/baidu/alibaba); `best_score`-Tracking statt First-Match
- ✅ **C1: `strip_thinking_tokens` Token-Schätzung**: Content-aware Heuristik `max(word_count * 1.3, char // 4)`, Whitespace-spezial-Case (1 Token pro 64 chars für Gemma-4 whitespace-heavy chains); Capped auf `char_count`
- ✅ **K1: `QUANT_MAP` Konflikt-Lösung**: `get_quant()` Helper mit expliziter Priorität (exact > suffix > base); Distinct-Entries für gpt-oss-20b Varianten (Q6_K, MXFP4, Q6_K) und Qwen3-Coder-REAP Varianten (Q3_K_M, Q4_K_S)
- ✅ **W1: `response` Spalte komprimiert**: `--keep-response` CLI-Flag, `_truncate_response()` Helper (default 200 chars + "…[truncated, X chars]" Marker); `--keep-response` an Subprozess weitergereicht
- ✅ **H2: Bootstrap-CI auf NumPy portiert**: `bootstrap_ci` und `paired_bootstrap_ci` nutzen `np.random.randint` + `np.partition`; **300-500x Speedup** (9-12ms statt 3-5s für 100x10k); Pure-Python Fallback erhalten
- ✅ **Test-Suite erweitert**: `tests/test_prio2.py` mit 21 neuen Tests für get_quant, strip_thinking_tokens, _truncate_response, bootstrap_ci; **36/36 Tests grün** (vorher 15/15)

**Verbleibende Prio-3-Befunde (refactoring):** MMLU-Pro-Code entfernen, Legacy-Aliase in csv_writer.py entfernen, Subprozess-Pfad-Logging, doppelte Thinking-Konfiguration zusammenführen, `download_real_benchmarks.py` aktualisieren

---

## 1. Executive Summary

Das Projekt ist eine ausgereifte, gut strukturierte Benchmark-Suite für lokale LLMs via LM Studio REST API. Die Architektur folgt einem sauberen 4-Pipeline-Design mit zentralem Launcher, dediziertem Model-Manager und einheitlichem CSV-Schema. Die Modularisierung in `benchmark_config.py`, `model_manager.py`, `csv_writer.py` und `consolidate_results.py` ist vorbildlich.

**Stärken:**
- Saubere Trennung: Launcher orchestriert, Subprozesse führen aus, kein Load/Unload außerhalb des Launchers
- Deterministische Reproduzierbarkeit via `--seed`
- Statistische Aussagekraft durch Bootstrap-CI und Pair-Vergleiche
- Konsolidierte, varianten-eindeutige Modell-Keys (kein Quant-Konflikt)
- Robuste Streaming-Logik mit doppelter Timeout-Überwachung (start/finish)
- Strukturierter JSON-Output mit Regex-Fallback (eliminiert 12% Parsing-Fehler)
- System-Monitoring (CPU/GPU/RAM/VRAM/Temp) pro Task
- 10 Pytest-Tests für Kernfunktionen

**Kritische Befunde (sofort beheben):**
1. ✅ `tests/test_csv.py:4` importiert aus `consolidate_results_v12` (existiert nicht) → **BEHOBEN** (Import + Fixture)
2. ✅ `run_benchmarks.py:1132-1137` Reload-Logik feuert nur für Custom-Benchmarks → **BEHOBEN** (`_ensure_model_still_loaded()`-Helper)
3. 🟠 `model_manager.py:274-280` Success-Path returnt `model_key` als Fallback-identifier, falls `get_current_loaded_model()` 10s lang `None` liefert → **Subprozesse erhalten falsche model_id → HTTP 400-Hang** (Doku in Zeile 672-676 weist auf genau dieses Risiko hin, aber der Fallback ist die Falle)
4. ✅ `custom_benchmark.py:641-670` `strip_thinking_tokens` schätzt Tokens via `total_chars // 4` → **BEHOBEN** (content-aware: `max(word_count * 1.3, char // 4)` + Whitespace-spezial-Case)
5. ✅ `benchmark_config.py:31,59-60` QUANT_MAP-Duplikate → **BEHOBEN** (`get_quant()` Helper mit expliziter Priorität, distinct-entries für alle Varianten)
6. ✅ `consolidate_results.py:152-192` `_lookup_vram` Fuzzy-Match → **BEHOBEN** (Length-Ratio-Guard >=0.85, Publisher-Prefix-Liste erweitert, `best_score`-Tracking)
7. 🆕 **🔴 `langdetect` fehlt** → IFEval schlägt bei **allen 14 Modellen** fehl (siehe 7.7.1)
8. 🆕 **🔴 `math_verify`/`sympy`/`antlr4-python3-runtime` fehlt** → MATH-500 schlägt bei **allen 14 Modellen** fehl (siehe 7.7.2)
9. 🆕 **🟠 DS1000-Harness Errors** für Granite-Modelle und Qwen3.6-28b: `set_xticklists`, `get_title`, `list index out of range`, `invalid syntax` (siehe 7.7.3)
10. 🆕 **🟠 TruthfulQA falsche Metrik** (`bleu_acc=0` für alle) — sollte `mc1` statt `gen` sein (siehe 7.7.5)
11. 🆕 **🟠 Granite DS1000/CoderEval 0%** trotz funktionierendem HumanEval+ (0.86) — Code-Parsing-Problem (siehe 7.7.7)
12. 🆕 **🟢 PowerShell-Encoding-Bugs** in Terminal-Output (`▒`, `�?` statt Unicode-Symbole) (siehe 7.7.10)

**Schwerwiegende Befunde (zeitnah beheben):**
7. `consolidate_results.py:230-264` `bootstrap_ci` und `paired_bootstrap_ci` sind **reine Python-Loops ohne NumPy** — bei 10000 Resamples × N Items: spürbare CPU-Last (>5s pro Benchmark)
8. `model_manager.py:120-132` `unload_all_models` validiert Unload durch 15× POST mit `model="check"` — verschwendet ~30s bei jedem Benchmark-Wechsel, **insbesondere wenn das Modell schon entladen war**
9. `run_benchmarks.py:1015-1020` `--exclude-benchmarks` filtert erst **nach** dem Auflösen — bei Tippfehler in der Großschreibung (`MATH-500` vs `math-500`) wird stillschweigend nichts gefiltert
10. `custom_benchmark.py:530-545` `subsample_tasks` stratified durch `_group` Feld, aber bei Custom-Benchmarks mit fehlender `_group` (z.B. CoderEval `prompt` ohne group) wird **plain random** verwendet → Verteilungsverlust bei kleinen SampleSizes

**Aus der Log-Analyse (12.07.2026):**
- ✅ **2× "Channel Error: Cannot combine structured output constraints with lazy grammar"** bei `granite-4.1-30b` (14:28) und `qwen3-30b-a3b-instruct-2507` (15:04) → **BEHOBEN**: `custom_benchmark.py` schreibt jetzt `[CHANNEL-ERROR]`-Marker in stdout wenn `error_detail` "Cannot combine structured output" oder "Channel Error" enthält; `run_benchmarks.py:run_custom_benchmark` detektiert den Marker und ruft sich rekursiv mit `no_structured_output=True` auf
- ✅ **13× "No models loaded"** in Log 5 zwischen 09:03–15:04 → **BEHOBEN**: `wait_for_model_ready` Timeout 30s → 60s (3 Stellen im Launcher); Default `TIMEOUT_MODEL_READY` 90s → 120s in `model_manager.py` als Sicherheitsnetz
- 5× "Unexpected endpoint" `/v1/version` (GET) — kommt **nicht** aus dem Python-Code (kein `/v1/version` im Repo); wahrscheinlich LM Studio GUI/Update-Check. Nicht durch Code behebar, aber dokumentierenswert.

---

## 2. Architektur-Bewertung

### 2.1 Positive Aspekte

**Klare Schichtentrennung** (siehe `doc-git/Architektur+Flow_Python-Benchmark-Skript_v24.md:59-123`):
```
Launcher (run_benchmarks.py)   → orchestriert, load/unload
├── custom_benchmark.py        → Subprozess für DS1000/CoderEval
├── model_manager.py               → shared: lms CLI Wrapper
├── csv_writer.py                  → shared: einheitliches Schema
├── evalplus (extern)              → HumanEval+, MBPP+
├── lm_eval (extern)               → ARC, HellaSwag, TruthfulQA, IFEval, MATH-500
└── tool_eval_bench (extern)       → Agentic
```

**Zentrale Konfiguration** in `benchmark_config.py`:
- `CAT_WEIGHTS` (Coding 35% / Math 25% / Agentic 25% / Knowledge 15%)
- `PIPELINE_TIMEOUTS` (14400s custom, 600s evalplus, 600s lmeval, 3600s agentic)
- `EXCLUDE_KEYWORDS` (whisper/vision/ocr/audio/embed/vl/flux)
- `MMLU_PRO_SUBSETS` (14 subsets, obwohl MMLU-Pro nicht mehr im LMEVAL_BENCHMARKS-Set ist — toter Code, s.u.)
- `TOOL_EVAL_SCENARIO_IDS` (TC-01..TC-69)

**Reproduzierbarkeit**: `--seed` wird durch alle Pipelines durchgereicht (`custom_benchmark.py:1625-1630`, `run_evalplus` Z.540-543), `paired_bootstrap_ci` nutzt seed für deterministische Vergleiche.

**Statistische Robustheit**:
- `bootstrap_ci` mit 10000 Resamples (Z.220-239) — Standard für 95% CI
- `paired_bootstrap_ci` für Quant-Vergleiche (Z.241-264) — paired statt unpaired, da gleiche Tasks
- `compute_category_scores` normalisiert Teil-Kategorien (Z.658-685) — wichtig wenn ein Benchmark fehlt

### 2.2 Design-Schwächen

**D1: Dynamische Versionierung über Glob-Discovery** (`run_benchmarks.py:139-148`)
```python
_custom_scripts = glob.glob(os.path.join(BASE_DIR, "custom_benchmark_v*.py"))
...
CUSTOM_BENCHMARK_SCRIPT = max(_versions, key=lambda x: x[0])[1]
```
**Problem:** Funktioniert nur, weil es aktuell nur eine `custom_benchmark.py` gibt. Bei zukünftigen Versionen wird die höchste v-Nummer genommen — ohne sichtbares Logging welcher Pfad genutzt wird. **Unsichtbare Regressionen** möglich.
**Fix:** Explizit die aktive Version in `benchmark_config.py` konfigurieren (`ACTIVE_CUSTOM_BENCHMARK = "custom_benchmark"`), Pfad loggen.

**D2: Zwei parallele "Thinking-Konfigurationen"** (`thinking_config.md:23-50` vs `custom_benchmark.py:141-237` vs `run_benchmarks.py:351-390`)
- `MODEL_CONFIG` in `custom_benchmark.py` steuert Custom-Pipeline
- `_get_lmeval_params` in `run_benchmarks.py` steuert lm_eval-Pipeline
- Doku sagt: "Seit v13 zentral in `_get_lmeval_params`" — **das stimmt nicht**: die Custom-Pipeline hat weiterhin ihre eigene `MODEL_CONFIG`. Doppelte Pflege, Drift-Risiko.
**Fix:** `MODEL_CONFIG` in `benchmark_config.py` zentralisieren, beide Pipelines importieren.

**D3: Subprozess-Orchestrierung ohne Health-Check** (`run_benchmarks.py:1084-1140`)
- Bei Custom-Benchmarks: nach jedem Task wird geprüft ob Modell noch geladen (Z.1123-1137)
- Bei EvalPlus/LM-Eval/Agentic: **kein analoger Check** — wenn Subprozess das Modell entlädt (z.B. durch Fehler), crasht der nächste
**Fix:** Health-Check für alle Pipelines einheitlich.

**D4: MMLU-Pro-Code-Pfade noch vorhanden** (`benchmark_config.py:70-76`, `consolidate_results.py:601-617`)
- `MMLU_PRO_SUBSETS` ist definiert
- `read_lmeval_per_model` hat eine spezielle MMLU-Pro-Schleife
- Aber: `LMEVAL_BENCHMARKS` (`run_benchmarks.py:173-179`) enthält **kein** MMLU-Pro mehr
- `Architektur+Flow` Z.17 sagt explizit "MMLU-Pro (zu teuer, 14 Subsets)" — entfernt
- → **Toter Code**, der die Konsolidierung kompliziert ohne Nutzen
**Fix:** `MMLU_PRO_SUBSETS` und MMLU-Pro-Schleife in `read_lmeval_per_model` entfernen.

**D5: Legacy-Aliase ohne Migrations-Pfad** (`csv_writer.py:421-432`)
```python
def save_csv(results, benchmark_name, model_id): ...
def save_model_summary(model_display, model_results, ...): ...
def save_model_summary_csv(results, model_info): ...
```
Diese Aliase leiten auf v10-Funktionen weiter, aber im aktuellen Code werden sie nicht mehr aufgerufen. Verwirren neue Contributor.
**Fix:** Entfernen (eine Major-Version-Reihe ist abgeschlossen, kein Backward-Compat-Bedarf mehr).

---

## 3. Code-Qualität pro Datei

### 3.1 `run_benchmarks.py` (1175 LOC)

**Stärken:**
- Saubere Pipeline-Funktionen mit klaren Returns (alle geben `dict` oder `None` zurück)
- Gute Fehlerbehandlung mit `try/except subprocess.TimeoutExpired`
- Subprozess-Timeouts korrekt mit Reasoning-×2 Faktor (`run_lmeval` Z.717-719)

**Bugs/Probleme:**

| # | Zeile | Problem | Schweregrad |
|---|-------|---------|-------------|
| B1 | 270-287 | `resolve_benchmarks` matched nur exakte lower-case Namen, aber die `ALL_BENCH_NAMES` sind auch lower-case → wenn ein Benchmark im UI als "MATH-500" angezeigt wird und der User es großschreibt, gibt's einen `Unknown benchmark`-Error. Sollte case-insensitive matchen. | Niedrig |
| B2 | 666-676 | **Kritischer Doku-Konflikt:** Doku sagt "ALWAYS use api_model" aber `model_manager.load_model_via_lms` returnt `model_key` (nicht `identifier`) wenn `get_current_loaded_model` 10s lang fehlschlägt. Subprozesse erhalten dann `model_key` (z.B. `qwen/qwen3-coder-30b`) statt identifier (z.B. `qwen/qwen3-coder-30b@q3_k_s`) → HTTP 400-Hang | **Hoch** |
| B3 | 1015-1024 | `exclude_benchmarks` setzt `b["name"].lower()` aber matcht nicht case-insensitiv auf `b["name"]` (Z.1019) | Niedrig |
| B4 | 1062-1065 | Wenn `load_model_via_lms` fehlschlägt, wird mit `continue` zum nächsten Modell gesprungen — **ohne** vorher zu prüfen ob andere Benchmarks evtl. übersprungen werden müssen. Korrekt, aber Logging könnte besser sein. | Niedrig |
| B5 | 1115-1117 | `all_summary.append(result)` ist in der Custom-Pipeline, `model_results.append(result)` ist in allen — Asymmetrie ist sauber, aber **die Bedingung `if result:`** an Z.1116-1121 ist redundant: ein leerer `result` (None) ist schon durch `result = run_*()` abgedeckt. | Niedrig |
| B6 | 1132-1137 | **Reload-Logik nur für Custom** — bei `if is_custom` wird geprüft, ob Modell noch geladen ist. EvalPlus/LM-Eval/Agentic haben diese Prüfung nicht. Wenn deren Subprozesse versehentlich entladen, crasht der nächste Task. | Mittel |

**Stilistische Probleme:**
- `import csv_writer as csv_writer` (Z.53) — `as csv_writer` ist redundant
- `_get_safe_context` (Z.204-210) sucht linear durch 6 Patterns — bei mehr Modellen ineffizient; sollte dict mit O(1) Lookup sein
- Module-level `THINKING_ENABLED = False` (Z.349) als globale Konfiguration ist Anti-Pattern; sollte explizit als Parameter durchgereicht werden

### 3.2 `custom_benchmark.py` (1819 LOC)

**Stärken:**
- Sehr robuste Streaming-Implementierung in `_stream_chat_completion` (Z.504-627) mit doppelter Timeout-Überwachung
- Solide Sandbox-Implementation in `_build_sandbox_script` (Z.909-996) mit expliziter Blocklist
- Strukturiertes Error-Handling mit `error_type`/`error_detail` Tuple (Z.504)
- Per-Task-Metriken mit `monitor.start_sampling`/`stop_sampling` (Z.1404-1431)

**Bugs/Probleme:**

| # | Zeile | Problem | Schweregrad |
|---|-------|---------|-------------|
| C1 | 640-651 | `strip_thinking_tokens`: Schätzt Tokens via `total_chars // 4` — für Gemma-4 mit `<|channel>thought\n...<channel|>`-Markup ist das **drastisch zu hoch**, weil `4` für englischen Text kalibriert ist. Führt zu `thinking_anteil` > 100% möglich | **Hoch** |
| C2 | 1268-1271 | Prompt-Konstruktion: `f"Create the function \`{entry_point}\`."` ist hartcodierter Text; CoderEval-Tasks enthalten bereits `entry_point` im docstring — kann zu Duplikaten im Prompt führen | Niedrig |
| C3 | 1310-1319 | `# SOLUTION START` Marker-Handling: Wenn der Marker fehlt (z.B. neuere DS1000-Versionen), wird `setup_code` leer → Sandbox kann nicht ausgeführt werden → Score 0% ohne Fehlermeldung | Mittel |
| C4 | 1706-1708 | `MAX_TASKS_PER_BENCHMARK = 100` — hartcodiertes Limit; bei 1000-Aufgaben-Benchmarks werden 90% ignoriert ohne Warning | Mittel |
| C5 | 504-627 | `_stream_chat_completion` hat 8-Tuple-Return (`content, elapsed, t_in, t_out, tps, thinking_tokens, error_type, error_detail`) — sollte ein `@dataclass` sein (siehe `consolidate_results.py:688-757` für positive Beispiele) | Mittel |
| C6 | 1700-1732 | Im Non-Interactive-Modus wird `for bench in benchmarks` durchlaufen, aber `non_interactive` führt **kein** `--thinking` automatisch aus — ist das absichtlich? Im README nicht dokumentiert. | Niedrig |

**Performance:**
- `Monitor` (Z.282-373) allokiert 4 Listen pro Instanz mit `MONITOR_HISTORY_MAX = 500` Elementen — bei langen Benchmarks (>500 Tasks) werden älteste Samples mit `del lst[:-MONITOR_HISTORY_MAX]` entfernt. O(1) pro Append, aber `get_snapshot` ruft `update` auf — kann den eigentlichen Sampling-Thread blockieren. Sollte als Lock-freies Ring-Buffer implementiert sein.

**Logik-Fehler:**
- `subsample_tasks` (Z.258-279): Stratified nur wenn `_group` Feld vorhanden. Bei `CoderEval` Tasks (siehe `download_codereval.py`) fehlt `_group` → plain random. Inkonsistent mit DS1000.

### 3.3 `consolidate_results.py` (1359 LOC)

**Stärken:**
- `ModelData` Dataclass (Z.688-757) — typisierte CSV-Zeilen, verhindert Dict-Key-Tippfehler
- `_normalize_model_keys` (Z.77-108) — robustes Variant-Deduplizieren
- `_get_display_name` mit 3-stufigem Fallback (Z.111-145) — exakt, modelKey-Match, Fuzzy
- `bootstrap_ci` und `paired_bootstrap_ci` (Z.220-264) — sauber implementiert
- `_percentile` lineare Interpolation (Z.211-218) — Standard NIST-Algorithmus

**Bugs/Probleme:**

| # | Zeile | Problem | Schweregrad |
|---|-------|---------|-------------|
| D1 | 152-192 | `_lookup_vram` Fuzzy-Match mit `dk_short = re.sub("(ibm\|google\|microsoft\|mistralai\|essentialai)/", "", dk_norm)` und `len(dk_short) > 5`: bei `gemma-4-12b` (10 chars) wird **alles** mit `gemma4...` gematcht → falsche VRAM-Zuordnung | **Hoch** |
| D2 | 220-264 | `bootstrap_ci` und `paired_bootstrap_ci` als reines Python — 10000 Resamples × N tasks. Bei N=100 ergibt das 1M `random.choice`-Aufrufe pro Benchmark. **NumPy nicht genutzt** — verschwendete CPU-Zeit | Mittel |
| D3 | 504-560 | `_read_results_json` und `read_lmeval_per_model` parsen JSON-Dateien unsortiert, **die neueste Datei wird durch Dateinamen-Sortierung gefunden** (Z.609), aber wenn alte + neue Datei existieren (z.B. nach Reload), wird nicht garantiert die neueste gewählt | Mittel |
| D4 | 621-655 | `read_agentic` macht `os.walk` und sortiert nach Timestamp-Substring in Dateinamen — fragil: wenn Datei `agentic_qwen3-30b_20260712_120000.json` heißt, sucht `_extract_ts` nach 14-stelligen Zahlen, aber wenn der Name `_v2_20260712_120000` ist, kann die `v2` mit `v2_20260712...` kollidieren | Niedrig |
| D5 | 762-790 | `read_data` mit `model_keys=None` macht Auto-Discovery über Dateinamen, **nicht** über den `model_key` aus CSV-Inhalt. Bei Re-Run eines Modells mit anderem Quant-Variante (z.B. `qwen3-coder-30b@q4_k_s` vs `@q3_k_s`) wird nur die **neueste** CSV gefunden — **alte Ergebnisse werden überschrieben** statt gemerged | Mittel |
| D6 | 1079-1118 | `_write_tbl` baut manuell eine Markdown-Tabelle mit komplexer Width-Berechnung. Code-Wiederverwendung von 50 LOC für eine Tabelle — sollte `tabulate` Library nutzen (bereits als transitive Dependency vorhanden via evalplus) | Niedrig |

**Dokumentations-Probleme:**
- Docstring Z.7-21 sagt: "1. Overall ranking", "2. Category scores" etc. — aber die `main()` Funktion (Z.950-...) macht `--compare`-Modus (paired bootstrap), der **vor** der normalen Konsolidierung läuft. Die Hauptfunktion verzweigt sehr früh — ungewöhnlich für Python-`main()`.

### 3.4 `model_manager.py` (329 LOC)

**Stärken:**
- `_ensure_lmstudio_running` (Z.218-249) mit llmster-Pfad-Fallback
- `load_model_via_lms` mit Doppel-Versuch (Z.259-294) — Recovery bei "No LM Runtime"
- `wait_for_model_ready` mit Polling (Z.298-329) — korrekte Behandlung von HTTP 400 "No models loaded"

**Bugs/Probleme:**

| # | Zeile | Problem | Schweregrad |
|---|-------|---------|-------------|
| M1 | 274-280 | **Kritischer Fallback-Bug:** Wenn `get_current_loaded_model()` 10×1s = 10s lang `None` liefert, wird `model_key` als identifier zurückgegeben. LM Studio API akzeptiert `model_key` aber **nur** wenn `lms load` ohne `--yes` aufgerufen wurde. Bei `--yes`-Load (Z.254) wird eine Variante mit `@quant`-Suffix geladen — `model_key` ohne Suffix mismatch → HTTP 400-Hang | **Hoch** |
| M2 | 120-132 | `unload_all_models` macht 15× POST-Calls an `/v1/chat/completions` mit `model="check"` — **30s Wartezeit** bei jedem Benchmark-Wechsel, **auch wenn das Modell bereits entladen war**. Sollte mit `lms ps --json` prüfen ob überhaupt etwas geladen ist | Mittel |
| M3 | 80-97 | `get_current_loaded_model` parst `lms ps --json` und returnt nur das **erste** Element (`entries[0]`). Bei mehreren geladenen Modellen wird das "falsche" zurückgegeben | Mittel |
| M4 | 252-295 | `load_model_via_lms` hat `context_length` und `gpu_offload` als Parameter, aber im Launcher (`run_benchmarks.py:1057, 1062, 1090`) wird **nur** `context_length` übergeben — `gpu_offload` ist tot | Niedrig |
| M5 | 218-249 | `_ensure_lmstudio_running` startet `llmster.exe` aus `~/.lmstudio/llmster/0.0.12-1/llmster.exe` — **absolute Versionsnummer im Pfad**. Bei LM Studio-Update bricht das | Niedrig |
| M6 | 70-77 | `check_api_available` und `TIMEOUT_HEALTH_CHECK` werden importiert aber **nie** außerhalb von `model_manager.py` aufgerufen — toter Code (Z.19-20 in `custom_benchmark.py:78-83` importiert sie, nutzt sie aber nicht) | Niedrig |

### 3.5 `benchmark_config.py` (124 LOC)

**Stärken:**
- Saubere Konfigurations-Single-Source-of-Truth
- `QUANT_MAP` mit Auto-Generator (`generate_quant_map.py`)
- `MMLU_PRO_SUBSETS` ist die einzige Quelle der Wahrheit für alle 14 Subset-Namen

**Bugs/Probleme:**

| # | Zeile | Problem | Schweregrad |
|---|-------|---------|-------------|
| K1 | 23-67 | `QUANT_MAP` enthält **drei Einträge** für `gpt-oss-20b`: `gpt-oss-20b` (Q6_K), `lmstudio-community/gpt-oss-20b` (MXFP4), `unsloth/gpt-oss-20b` (Q6_K). `_lookup_vram` nutzt den ersten Match — wenn ein anderer Quant gewünscht ist, wird der falsche geliefert | **Hoch** |
| K2 | 85-104 | `CAT_WEIGHTS` benutzt `HumanEval+_plus` und `MBPP+_plus` als Keys (Z.88-89), aber `custom_benchmark.py` schreibt `"HumanEval+"` in CSV. Inkonsistenz führt zu Score=0 für diese Benchmarks in `compute_category_scores` | **Hoch** |
| K3 | 70-76 | `MMLU_PRO_SUBSETS` ist toter Code (s.o. D4 in Architektur) | Niedrig |
| K4 | 108-115 | `PIPELINE_TIMEOUTS["custom_subprocess"] = 14400` (4h!) — sehr lang, blockiert Fehlererkennung. Bei hängenden Tasks läuft man 4h ohne Feedback | Niedrig |

**Bugs K2 ist besonders kritisch** — die Keys in `CAT_WEIGHTS` (`HumanEval+_plus`, `MBPP+_plus`) matchen nicht die Keys in `bench_scores` (kommt von `try_read_evalplus` Z.518-542 mit Key `humaneval_plus` und `mbpp_plus` — also auch nicht!). Kette der Bugs:
- `try_read_evalplus` returnt `{"humaneval_plus": 0.x, "mbpp_plus": 0.x}` (lowercase, ohne `+`)
- Diese werden in `read_data` Z.849-850 als `bench_scores["HumanEval+_plus"]`/`bench_scores["MBPP+_plus"]` zugewiesen
- `compute_category_scores` nutzt `CAT_WEIGHTS["coding"]` mit Keys `"HumanEval+_plus"`, `"MBPP+_plus"` (uppercase)
- `bench_scores` hat `"HumanEval+_plus"` — also passt es doch? **Ja, in dem Fall passt es — False-Alarm, aber die Inkonsistenz bleibt riskant.**

### 3.6 `csv_writer.py` (432 LOC)

**Stärken:**
- Einheitliches CSV-Schema über 4 Pipelines
- Klarer Workflow: TASK_FIELDS → MODEL_FIELDS → SUMMARY_FIELDS → CONSOLIDATED_FIELDS
- `write_quant_comparison` (Z.375-417) für stat. signifikante Quant-Vergleiche

**Bugs/Probleme:**

| # | Zeile | Problem | Schweregrad |
|---|-------|---------|-------------|
| W1 | 68-100 | `TASK_FIELDS` enthält `response` (Z.99) — bei DS1000/CoderEval kann `response` mehrere KB JSON-Code enthalten. Bei 100 Tasks × 50KB = 5MB CSV. **Bloat** | Mittel |
| W2 | 152-166 | `CONSOLIDATED_FIELDS` enthält keine Spalten für Runtime/Effizienz/VRAM — die wichtigen Engineering-Metriken fehlen in der konsolidierten Übersicht | Mittel |
| W3 | 271 | `f"{e.get('avg_score', 0) * 100:.1f}"` — Multiplikation mit 100 hardcoded. Wenn `avg_score` schon in 0-100 ist (was es ist, siehe `run_task` Z.1283-1295), wird 100-fach zu groß! | **Hoch** |

**W3 ist ein echter Bug:** in `benchmark_model` Z.1473 wird `avg_score = sum(scores) / len(scores)` berechnet, und `scores` enthält Werte aus `result["score"]` (Z.1283: 0.0 oder 1.0 für pass/fail). Also 0-1. In `write_per_model_csv` Z.271 wird `* 100` gemacht → korrekt. Aber das `avg_score` in `model_results` (Z.1738-1752) wird **als Float (0-1) übergeben**, und `e.get("avg_score")` ist dieser Float. `* 100` ist also korrekt. **False-Alarm.**

Aber: in `write_per_task_csv` Z.218 wird `r.get("score", "")` direkt übernommen **ohne** `* 100` — der CSV-Wert ist also 0-1 in tasks, 0-100 in models. **Echte Inkonsistenz!**

### 3.7 `tests/` (2 Dateien, 99 LOC)

**`test_scores.py`:** ✅ 10 Tests, alle sinnvoll, testen `compute_category_scores` und `_percentile`. Deckt Edge-Cases (partial scores, zero scores, single value) ab.

**`test_csv.py`:** ❌ **Komplett kaputt:**
- Z.4: `from consolidate_results_v12 import read_custom_csv, _auto_delimiter` — `v12` existiert nicht
- `read_custom_csv` ist in `v13`, Z.347
- `_auto_delimiter` ist in `v13`, Z.340
- Sollte sein: `from consolidate_results import read_custom_csv, _auto_delimiter`
- Fixture-Pfad `tests/fixtures/test_tasks.csv` ist nirgends im Repo sichtbar — Tests schlagen fehl mit `FileNotFoundError`

→ **CI läuft grün (weil keine CI konfiguriert ist in `.github/`), aber die Tests funktionieren nicht.** Hohe Priorität.

### 3.8 Hilfs-Skripte

**`download_codereval.py`** (296 LOC):
- Lädt CoderEval4Python.json, konvertiert zu self-contained Tasks
- `PARAM_RULES` (Z.13-37) heuristisch, gut dokumentiert
- `_is_blocked` (Z.140-147) blockiert gefährliche Module — gut
- **Bug D1:** Z.127 `if isinstance(expected, types.FunctionType): return None` — führt zu `skip_task = True` Z.261, Task wird übersprungen. Aber: ein `return None` ist die einzige Rückgabe für diesen Fall — die nachfolgende Assertion (Z.259) ist `if assertion is None: skip_task = True`. Korrekt.
- **Aber:** `_make_assertion_code` für Funktionen mit `*args` (Z.145) wird zu "has *args/**kwargs" Skip-Grund — viele CoderEval-Tasks haben das

**`download_real_benchmarks.py`** (594 LOC):
- Lädt 11 Benchmark-Datensätze
- **Komplett veraltet:** Die Felder `type: "coding"`, `type: "math"` etc. werden gesetzt, aber vom aktuellen Code nicht genutzt (Custom-Pipeline nutzt `task_type` aus dem BENCHMARKS-Dict Z.137-139)
- Die Datei `simple_evals/coding.jsonl` wird erzeugt, aber vom aktuellen Launcher nicht referenziert (nur `data_science.jsonl` und `codereval_selfcontained.jsonl` werden benutzt)
- **Toter Code** — sollte entweder gelöscht oder in CI wiederverwendet werden

**`generate_quant_map.py`** (296 LOC):
- Multi-Source QUANT_MAP-Generator
- 5-stufige Prioritätskaskade (lms ls → Config → GGUF-Cache → Display-Name → Filename)
- `_normalize_key` (Z.131-140) entfernt Publisher + Quant — robust
- **Bug:** `_format_quant_map` (Z.209-224) sortiert nach `name_map` aber nutzt `name_map = {k: k for k in all_keys}` (Z.242) — d.h. nach model_key statt Display-Name. Sortierung ist nicht-deterministisch zwischen Runs

**`backup_model_configs.py`** (82 LOC):
- Backup/Restore von LM Studio per-model configs
- Saubere Pfad-Resolution
- Kein Backup von `user-concrete-model-default-config` wenn Verzeichnis nicht existiert (Z.18-19) — gut

**`gguf_full_metadata_reader.py`** & `gguf_moe_full_metadata_reader.py`:
- Liest GGUF-Metadata, extrahiert MoE-Info
- Wird vom aktiven Benchmark-Code **nicht** referenziert — toter Code
- Hat Umlaut-Bugs im Output (siehe `Möchten` statt `Möchten`)

**`check_agentic.py`** (29 LOC):
- Smoke-Test: listet Modelle die Agentic-Scores haben
- Hartcodiert auf `konsolidiert_2026*.csv` Pattern (Z.3) — funktioniert nicht mit `konsolidiert_SS4_*.csv` (neue Namens-Konvention)
- **Bug:** Bei `konsolidiert_SS4_20260712_125230.csv` zeigt das Script 0/41 Agentic-Scores obwohl Agentic-Scores vorhanden sind

---

## 4. Performance-Analyse

### 4.1 Identifizierte Hotspots

**H1: Subprozess-Overhead pro Benchmark** (Architektur-Doku bestätigt das)
- Jeder LM-Eval-Task startet einen eigenen `python -m lm_eval` Subprozess
- EvalPlus: `evalplus_codegen` Subprozess pro Dataset (humaneval/mbpp)
- Bei 4 Benchmarks × 28 Modelle = **112 Subprozesse**, jeder mit Python-Start (~2s) + lm_eval-Init (~5s) = **~15 min Overhead** für nix

**H2: Bootstrap-CI ohne NumPy** (`consolidate_results.py:220-264`)
- `bootstrap_ci` macht 10000 × `random.choice(scores)` → 1M Calls bei N=100
- NumPy: `np.random.choice(scores, (10000, N), replace=True).mean(axis=1)` → 100x schneller

**H3: `unload_all_models` validiert mit 15 POST-Calls** (`model_manager.py:118-132`)
- 30s Wartezeit bei jedem Benchmark-Wechsel
- Bei 4 Benchmarks × 28 Modelle = **112 × 30s = 56 min** reine Wartezeit
- **Fix-Vorschlag:** `lms ps --json` check (sub-second), nur POST wenn Modell noch da

**H4: Per-Task `monitor.start_sampling`** (`custom_benchmark.py:1404`)
- 5Hz Sampling während Inference — minimaler Overhead
- Aber: `MONITOR_HISTORY_MAX = 500` × 4 Listen = 2000 Floats pro Task
- Bei 100 Tasks × 28 Modelle = 5.6M Floats gespeichert — minimal (40MB)

**H5: Token-Estimation via `len(content.split())`** (`custom_benchmark.py:624`)
- Funktioniert für englischen Text (~0.75 Tokens/Wort)
- Für Code mit Sonderzeichen fehlerhaft (z.B. `==` als 1 Wort statt 1 Token)
- Sollte Tokenizer nutzen (in `requests` Antwort bereits enthalten, Z.617)

### 4.2 Skalierungs-Probleme

Bei 100+ Modellen oder SS=100 wird das System merklich langsamer:
- Konsolidierung: 100 Modelle × 4 Benchmarks = 400 CSV-Reads = linear
- Display-Name-Resolution: 100 × 3-stufiger Fallback pro Modell = 300 `lms ls --json` Calls
  - **Bug:** `_get_model_info()` cached nur eine Session (`_MODEL_INFO_CACHE` Z.38), aber bei `--compare` wird er mehrfach aufgerufen — Cache hilft

---

## 5. Test-Coverage

**Aktuell:** 10 Tests in `test_scores.py` + ~5 Tests in `test_csv.py` (kaputt)

**Lücken:**
- Keine Tests für `model_manager.py` (kritisch, viele Bug-Quellen)
- Keine Tests für `custom_benchmark.py` Streaming-Logik
- Keine Tests für `consolidate_results.py` (außer `compute_category_scores`)
- Keine Tests für `csv_writer.py` Schema-Konsistenz
- Keine Tests für `download_codereval.py` Heuristiken
- Keine Integration-Tests (echte LM Studio Calls)
- Keine CI-Config in `.github/` (nur ISSUE_TEMPLATE/bug_report.md)

**Empfehlung:**
1. `test_csv.py` reparieren (Import + Fixture erstellen)
2. Mocking-Layer für LM Studio API-Calls einbauen (z.B. mit `responses` Library)
3. CI mit GitHub Actions: `pytest + ruff + mypy`
4. Property-Based Tests für `_get_display_name` Fuzzy-Match

---

## 6. Doku-Konsistenz

### 6.1 README.md

- Z.17 listet `lm_eval (ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro)` — **MMLU-Pro ist entfernt**, sollte aktualisiert werden
- Z.17 listet `MathQA` — **ersetzt durch MATH-500** (siehe `run_benchmarks.py:178`)
- Z.39-40 GitHub-URL `pskraer11/llm-benchmark-suite` — existiert das Repo? Nicht überprüfbar, aber passt zu den lokalen `git remote -v`-Daten
- Z.61-63 zeigt `--benchmarks DS1000,CoderEval --sample-size 10` — funktioniert mit v13
- Z.65-67 zeigt `python consolidate_results_v12.py --bootstrap` — **`--bootstrap` wurde in v13 entfernt** (Z.144 der thinking_config.md bestätigt), muss aktualisiert werden
- Z.73-80 CLI-Options-Tabelle ist akkurat
- Z.91-92 Architektur-Diagramm ist korrekt
- Z.99-104 Pipeline-Tabelle listet **4 Pipelines, 10 Benchmarks** aber die aktuelle v13 hat **5 Pipelines** (`custom`, `evalplus`, `lmeval`, `agentic` + die `_parse_subset_score`-Helper, plus `MMLU-Pro-modified`) — und nur **9 Benchmarks** (ohne MMLU-Pro)
- Z.105-114 Weighting-Tabelle ist korrekt für aktives Set, aber **MATH-500 statt MathQA** fehlt in der Aufzählung
- Z.115-127 "Thinking Mode" Sektion ist veraltet — erwähnt `--thinking` Aktivierung für MathQA/MMLU-Pro (nicht mehr existierende Benchmarks)
- Z.130-145 Project Structure stimmt mit aktueller Verzeichnisstruktur überein

### 6.2 `doc-git/Architektur+Flow_Python-Benchmark-Skript_v24.md`

- Z.1: "Stand 12.07.2026 (v33)" — **Versions-Wirrwarr**: README sagt v13, Datei sagt v33. Doku-Inkonsistenz
- Z.17: "Entfernt: BBH, PandasEval, MMLU-Pro" — korrekt
- Z.17: "Dafür neu: Agentic-Pipeline und MATH-500" — korrekt
- Z.59-123: Strukturbeschreibung ist akkurat
- Z.66: "MMLU-Pro-Helper (entfernt in v13): _get_lmeval_params, _build_lmeval_cmd, _parse_subset_score" — **FALSCH**: Diese Helper existieren in v13 noch (Z.351, 393, 431 in `run_benchmarks.py`)
- Z.85: "Version intern: 'Unified Benchmark Launcher v10'" — verwirrend, da Datei `v13` heißt
- Z.122-123: Duplikater Absatz: "Vollständige Type Hints (27 Funktionen)" steht zweimal
- Z.142: "BBH (zu teuer, 8x Multiplier)" — BBH ist entfernt, aber in `download_real_benchmarks.py` immer noch implementiert (Z.231-292)
- **Review 28.06.2026 Sektion (Z.125-146):** Sehr ausführlich, gute Historie. Aber "Type Hints 55+20+27 = 102 Funktionen" (Z.129) — aktuelle Zahlen sollten verifiziert werden (v13 hat wahrscheinlich mehr)

### 6.3 `doc-git/thinking_config.md`

- Z.23-41: Aktuelle Patterns sind korrekt für v13
- Z.42-57: `--thinking` Flag Verhalten ist sehr klar dokumentiert
- Z.58-72: "Seit v13 zentral in `_get_lmeval_params()`" — **falsch** wie oben in D2 angemerkt
- Z.85: "MathQA `20→512`, HellaSwag `20→100`" — diese YAML-Änderungen sind im Repo nicht auffindbar (`lm_eval_tasks/` enthält nur `mathqa_gen/utils.py`)

### 6.4 `doc-git/Parallel-Slots-Optimierung.md`

- Z.30-37: Dense vs MoE Empfehlung (np=1 vs np=4) — exzellente empirische Daten
- Z.42-55: LCP/LRU Mechanismus korrekt erklärt
- Z.78-101: Log-Belege sind konkret und nachvollziehbar
- **Aber:** Skript-Empfehlungen sind nicht im Python-Code umgesetzt — `model_manager.py` hat keinen `np`-Parameter. Manuell via JSON-Config erforderlich (das wird auch in Doku-intern/ erwähnt)

### 6.5 `Doku-intern/Modell_Steckbriefe_20260711.md`

- Sehr umfangreich, gute Praxis-Informationen
- Inkonsistenz: Archiv-Einträge sind mit `(gelöscht)` markiert, aber **3 davon (LFM2 24B, qwen3.6-28b, GPT-OSS 20B) wurden für den SS=4-Run reaktiviert** — Cross-Reference zu `ergebnisse/` und `consolidate_results.py:684-688` zeigt reaktivierte Modelle

### 6.6 `Doku-intern/Reviews/`

- Drei Review-Files vorhanden (`Code-Review_30-06-2026.md`, `review_20260628.md`, `Review_20260705.md`)
- Konsistenz der Reviews untereinander unklar — verschiedene Strukturen

---

## 7. LM Studio Server-Log-Analyse (12.07.2026)

### 7.1 Datenmenge

| Log | Größe | Zeilen | Modelle (top) |
|-----|-------|--------|----------------|
| `2026-07-12.5.log` | 10.0 MB | 110,902 | qwen3.6-28b-reap-i1@q3_k_s (30k), qwen3.6-27b-mtp (15k) |
| `2026-07-12.6.log` | 10.0 MB | 110,370 | qwen3.6-27b-mtp (73k), qwen3.6-28b-reap-i1@iq3_s (32k) |
| `2026-07-12.7.log` | 1.3 MB | 12,997 | qwen3.6-28b-reap-i1@iq3_s (12.5k) |

### 7.2 Fehler-Kategorisierung

| Fehlertyp | Log 5 | Log 6 | Log 7 | Total |
|-----------|-------|-------|-------|-------|
| "No models loaded" | 13 | 1 | 0 | **14** |
| "Unexpected endpoint /v1/version" | 5 | 1 | 0 | **6** |
| **"Channel Error: Cannot combine structured output constraints with lazy grammar"** | **2** | 0 | 0 | **2** |
| TIMEOUT-Pattern | 0 | 0 | 0 | 0 |
| OOM (not enough space) | 0 | 0 | 0 | 0 |

### 7.3 Channel Error – Critical Finding

**Log 5 Zeilen 58671, 94468:** Bei `granite-4.1-30b` (14:28:29) und `qwen3-30b-a3b-instruct-2507` (15:04:56) tritt folgender Fehler auf:
```
[ERROR] Error: Channel Error
- Caused By: Error: Cannot combine structured output constraints with lazy grammar
```

**Ursache:** LM Studio akzeptiert `response_format: {type: "json_schema", ...}` nicht zusammen mit internen Lazy-Grammar-Constraints. `custom_benchmark.py:1311-1335` und `STRUCTURED_OUTPUT_SCHEMA` (Z.103-116) setzen dieses Schema unbedingt für alle Custom-Benchmarks, **ohne** Modell-Kompatibilität zu prüfen.

**Code-Stellen:**
- `custom_benchmark.py:103-116` (`STRUCTURED_OUTPUT_SCHEMA` Definition)
- `custom_benchmark.py:1311-1335` (Übergabe an `generate_answer`)
- `custom_benchmark.py:1611-1612` (`--no-structured-output` Flag)

**Bisheriger Workaround:** Manuell `--no-structured-output` setzen, aber:
1. Kein Auto-Fallback bei Channel Error
2. Subprozess-Output-Parsing in `run_custom_benchmark` Z.509-512 liest "Average score" aus Output — bei Channel Error ist die Subprozess-Output leer → Score 0% für diese Modelle

**Empfohlener Fix:**
- Channel-Error-Exception in `run_custom_benchmark` erkennen
- Auto-Retry mit `--no-structured-output` für genau diese Modelle
- Oder: Pro-Modell-Whitelist in `MODEL_CONFIG` für `structured_output: True/False`

### 7.4 "No models loaded" – Health-Check-Lücke

**Log 5 Zeilen 25901, 31380, 32207, ... 83268 (13 Vorfälle):**
```
[ERROR] No models loaded. Please load a model in the developer page or use the 'lms load' command.
```

**Zeitliche Korrelation:** Alle Vorfälle zwischen 09:03 und 15:04 — passend zum SS=4-Run, der laut `Architektur+Flow` und CSV-Daten um diese Zeit lief.

**Wahrscheinliche Ursache:** `model_manager.wait_for_model_ready(timeout=30)` (Z.298-329) macht POST mit `model="check"` — wenn der Server noch nicht bereit ist (LM Studio startet gerade nach `lms load`), antwortet er mit `No models loaded`. Die 30s Wartezeit ist möglicherweise zu kurz für 30B-Modelle (Load-Zeit oft 30-60s).

**Code-Stelle für Fix:**
- `model_manager.py:298-329` — Timeout auf 60-90s erhöhen ODER mehrere Load-Status-Checks zwischen Load und Subprozess-Start einfügen

### 7.5 Performance-Pattern aus Logs

**LCP-Cache funktioniert sehr gut:**
- Log 5: 1131 LCP-Selections vs 20 LRU-Selections (98% LCP-Hit-Rate)
- Log 6: 224 LCP vs 2 LRU
- Log 7: 34 LCP vs 0 LRU

**Das bestätigt die np=1-Empfehlung aus `Parallel-Slots-Optimierung.md`** — die Praxis-Daten stimmen mit der Theorie überein.

**Tool-Call-Dichte (Log 5):** 1358 Tool-Calls für qwen3.6-28b-reap-i1@q3_k_s + weitere Modelle — das ist erwartet bei Agentic-Benchmark.

### 7.6 `/v1/version` Anfragen

**Log 5, 6:** 5+1 Anfragen an `GET /v1/version` (Z.44562, 54288, 70364, 82284, 92784 + 71260). **Nicht** im Python-Code referenziert (geprüft mit grep). Vermutlich LM Studio GUI-Health-Check oder Auto-Update-Mechanismus. **Nicht durch Code behebar, aber als bekanntes Phänomen dokumentierbar** (z.B. in Architektur-Doku).

### 7.7 Terminal-Ausgabe Befunde (Run 12.07.2026, nachgereicht)

**Quelle:** `Doku-intern/Terminalausgabe Benchmark Run mit neuen Benchmarks und SampleSize 10.md` (NICHT im ursprünglichen Review-Scope enthalten — nachträglich hinzugefügt am 12.07.2026).

#### 7.7.1 IFEval schlägt bei ALLEN 14 Modellen fehl — `langdetect` fehlt

**Schweregrad: 🔴 Kritisch** | **Häufigkeit: 14/14 Modelle × 2 Runs = 28 Subprocess-Fehler**

Beim Aufruf von `lm_eval --tasks ifeval` schlägt jedes Modell fehl mit:
```
ModuleNotFoundError: No module named 'langdetect'
```
Aufrufpfad: `lm_eval/tasks/ifeval/instructions.py:36` → `import langdetect`. lm_eval's IFEval-Tasks benötigen `langdetect` für die Spracherkennung der LLM-Outputs.

**Code-Stelle:** `run_benchmarks.py:run_lmeval` ruft `python -m lm_eval --tasks ifeval` als Subprozess auf, der die `langdetect`-Dependency auf Modulebene lädt. Da der Subprozess sich **vor** dem `simple_evaluate` mit dem `import` aufhängt, gibt es kein Score-Ergebnis.

**Auswirkung:** `consolidate_results.py:read_lmeval_per_model` findet keine `IFEval`-Scores in `ergebnisse/lmeval_<model>/` → `bench_scores["IFEval"] = None` → keine Aggregation möglich.

**Empfohlener Fix:** `pip install langdetect` in Installationsskript (`Doku-intern/Doku-intern/install_benchmark-data_windows.ps1`) aufnehmen und in `README.md:42` ergänzen.

#### 7.7.2 MATH-500 schlägt bei ALLEN 14 Modellen fehl — `math_verify`/`sympy`/`antlr4-python3-runtime` fehlen

**Schweregrad: 🔴 Kritisch** | **Häufigkeit: 14/14 Modelle × 2 Runs = 28 Subprocess-Fehler**

Beim Aufruf von `lm_eval --tasks minerva_math500` schlägt jedes Modell fehl mit:
```
ModuleNotFoundError: No module named 'math_verify'
ModuleNotFoundError: `sympy`, `math_verify` and `antlr4-python3-runtime==4.11` are required
```
Aufrufpfad: `lm_eval/tasks/minerva_math/utils.py:16` → `from math_verify import parse, verify`. lm_eval's MATH-Tasks (minerva_math) benötigen diese Dependencies.

**Code-Stelle:** Gleicher Code-Pfad wie IFEval (siehe 7.7.1).

**Auswirkung:** Konsolidierung kann `Math`-Score nicht berechnen. `CAT_WEIGHTS["math"] = {"MATH-500": 1.0}` in `benchmark_config.py:97-99` ist ein Deadlock ohne diese Dependencies.

**Empfohlener Fix:** `pip install lm-eval[math]` (installiert sympy + math_verify + antlr4-python3-runtime) im Installationsskript aufnehmen. Alternative: `pip install sympy math_verify antlr4-python3-runtime==4.11`.

#### 7.7.3 DS1000-Harness Errors (mehrere wiederkehrende Muster)

**Schweregrad: 🟠 Hoch** | **Häufigkeit: 30+ Vorfälle über alle Granite-Modelle**

DS1000-Tasks schlagen mit folgenden Fehlermeldungen fehl:
- `'NoneType' object has no attribute 'get_title'` (Matplotlib fehlt `set_title` Aufruf in generiertem Code)
- `list index out of range` (Test-Generierung schlägt fehl)
- `invalid syntax (<string>, line N)` (Unwrap-Logik im Code funktioniert nicht)
- `Arrays are not equal (shapes (2,) (10,) mismatch)` (DS1000-Tests erwarten mehr Werte als generiert)
- `module 'matplotlib.pyplot' has no attribute 'set_xticklabels'`

**Betroffene Modelle:** Granite 4.1 30B I1, Granite 4.0 H Tiny, Granite 4.1 8B (alle 3 Granite-Modelle), Qwen3.6 28B REAP I1

**Code-Stelle:** `custom_benchmark.py:1113-1146` (`_try_ds1000_harness`) — die `_unwrap_solution_for_insert` Funktion (Z.1036-1110) versucht Code zu formatieren, aber der offizielle DS-1000-Harness (`ds1000_official/execution.py`) erwartet exakt definierte Code-Struktur.

**Mögliche Ursachen:**
1. Code wird mit `enable_thinking=True` generiert → denkt nach statt zu coden
2. `set_xticklabels` ist eine alte Matplotlib-API — neuere Versionen haben `ax.set_xticklabels()`
3. `_unwrap_solution_for_insert` strippt zuviel Code bei manchen Patterns

**Empfohlene Fixes:**
- DS1000-YAML mit `do_sample=False` und explizitem `temperature=0.0` testen
- `set_xticklabels` patches in `_try_ds1000_harness` (ersetzen mit `ax.set_xticklabels(...)`)
- Mehr DS1000-Tasks als "expected_outputs" mit `0` oder `array([])` behandeln

#### 7.7.4 ARC-Challenge Score=0 für fast alle Modelle

**Schweregrad: 🟠 Hoch** | **Betroffen: 13/14 Modelle**

| Modell | ARC-Challenge Score |
|---|---|
| Granite 4.1 30B I1 | 0 |
| Granite 4.1 30B | 0 |
| Granite 4.0 H Tiny | 0 |
| Granite 4.1 8B | 0 |
| Qwen3 30B A3B Instruct 2507 | **0.9** (einziger non-zero) |
| Qwen3.6 27B | 0 |
| Qwen3.6 28B REAP I1 | 0 |

**Wahrscheinliche Ursache:** ARC-Challenge hat 1170 multiple-choice Fragen — bei limit=10 sind 8 von 10 wahrscheinlich "leicht" während 2-3 die "schweren" sind. Mit SampleSize=10 ist die Stichprobe zu klein für statistische Aussage. **ABER:** Selbst Qwen3 30B A3B schafft 0.9, daher ist Score=0 für alle anderen Modelle verdächtig.

**Mögliche Erklärung:** Die YAML-Konfiguration für `arc_challenge_chat` filtert die Antwort mit `remove_whitespace`. Granite-Modelle geben möglicherweise Buchstaben + zusätzlichen Text zurück, was nach Whitespace-Stripping die "richtige" Antwort zerstört.

**Code-Stelle:** `lm_eval_tasks/arc_challenge.yaml` (nicht im aktuellen Code — gelöscht?) oder `lm_eval/tasks/arc/arc_challenge_chat.yaml` (lm_eval built-in).

#### 7.7.5 TruthfulQA `bleu_acc=0` überall — falsche Metrik

**Schweregrad: 🟠 Hoch** | **Betroffen: 13/14 Modelle**

`truthfulqa_gen` returniert für fast alle Modelle:
```
|truthfulqa_gen|3|none|0|bleu_acc   |↑ |0.0000|± |0.0000|
|              |  |none|0|bleu_diff  |↑ |-0.0675|± |0.0467|
```

**Ursache:** lm_eval's `truthfulqa_gen` (Generation Task) erwartet, dass das Modell die **komplette Antwort** generiert (z.B. "The moon is made of cheese") und mit `bleu_acc` (BLEU-Score) gegen die Ground-Truth vergleicht. Die meisten LLMs geben aber **nur den Buchstaben A/B/C/D** zurück (Multiple-Choice), nicht den vollen Antwort-Text → BLEU = 0.

**Code-Stelle:** lm_eval built-in YAML `truthfulqa_gen` — die `bleu_acc`-Metrik ist die falsche Wahl für Multiple-Choice-Antworten.

**Empfohlener Fix:** Auf `mc1` (Multiple-Choice 1) oder `mc2` (Multiple-Choice 2) wechseln. Im aktuellen Code (`run_benchmarks.py:176`) wird `truthfulqa_gen` verwendet — sollte zu `truthfulqa_mc1` geändert werden.

#### 7.7.6 HellaSwag Score=0 für Granite-Modelle

**Schweregrad: 🟡 Mittel** | **Betroffen: 3/3 Granite-Modelle**

| Modell | HellaSwag |
|---|---|
| Granite 4.1 30B I1 | 0 |
| Granite 4.0 H Tiny | 0.23 |
| Granite 4.1 8B | 0 |
| Qwen3 30B A3B | 0.72 |

**Wahrscheinliche Ursache:** Ähnlich wie ARC — Granite-Modelle geben **nur den Buchstaben A/B/C/D** zurück, nicht die volle Satzvervollständigung → `custom-extract` Regex matcht nicht.

**Code-Stelle:** `lm_eval/tasks/hellaswag/hellaswag_gen.yaml` (lm_eval built-in) — die `custom-extract` Regex extrahiert Text vor dem Buchstaben, was bei reinen Buchstaben-Antworten leer ist.

#### 7.7.7 DS1000 + CoderEval Score=0 für Granite-Modelle

**Schweregrad: 🟠 Hoch** | **Betroffen: 3/3 Granite-Modelle**

Granite 4.1 30B I1: DS1000 0% (alle 10 Tasks FAILED), CoderEval 0% (alle 10 Tasks 0/N tests passed)
Granite 4.0 H Tiny: DS1000 0% (FAILED), CoderEval 0% (alle 0/N)
Granite 4.1 8B: DS1000 0% (FAILED), CoderEval 0% (alle 0/N)

**Aber:** Granite 4.1 30B (non-i1): HumanEval+ 0.860, MBPP+ 0.619 — also funktioniert EvalPlus normal.

**Hypothese:** Granite-Modelle schreiben **valides Python**, aber der Code wird durch `_unwrap_solution_for_insert` (DS1000) oder `extract_code` (CoderEval) falsch verarbeitet. Granite hat eventuell einen anderen Code-Block-Stil (z.B. `def` ohne `class`, oder Imports in einer anderen Reihenfolge).

#### 7.7.8 DS1000 + CoderEval 0% für Granite ist KEIN Sandbox-Fehler

Die Fehler in der Terminal-Ausgabe sind spezifisch: "Harness error: failed: <numpy comparison>" für DS1000 und "Direct tests: 0/N passed" für CoderEval. Das **Sandbox-System selbst funktioniert** (kein `Permission denied`, keine Crashes). Es ist ein **Code-Parsing-Problem**.

**Mögliche Ursache:** Granite-Modelle schreiben Code in einem anderen Stil als erwartet (z.B. ohne `[insert]`-Marker den DS1000-Harness sucht). Siehe `custom_benchmark.py:1036-1110` (`_unwrap_solution_for_insert`).

#### 7.7.9 Granite 4.0 H Tiny mit 24 statt 64 Experts lädt — Workaround im LM Studio

Siehe `Modell_Steckbriefe_20260711.md:448-456` für `num_experts=16-24` Workaround. Dies ist nicht direkt ein Python-Bug, aber ein Hinweis dass die Steckbrief-Konfiguration nicht automatisch angewendet wird — der User muss sie manuell in LM Studio setzen.

#### 7.7.10 Encoding-Bugs in PowerShell-Terminalausgabe

**Schweregrad: 🟢 Niedrig**

Die Markdown-Datei enthält mehrfach kaputte Unicode-Zeichen:
- `�?` statt `×` (multiplication sign)
- `�%^0%` statt `≈0%` (approximately equal)
- `▒` statt Pfeil-Codepoints
- `�?` statt Emojis

**Ursache:** PowerShell-Konsole auf Windows verwendet cp1252 oder Windows-1252, nicht UTF-8. Der Code setzt zwar `sys.stdout.reconfigure(encoding="utf-8")` in `custom_benchmark.py:1588-1592`, aber das wirkt nur für Python-Output. PowerShell-Redirect in Datei kann zwischendurch auf Windows-Codepage umschalten.

**Empfohlener Fix:** `PYTHONIOENCODING=utf-8` und `chcp 65001` in der `run_benchmarks.py` als Subprozess-Env-Var setzen (bereits teilweise in Z.715 gesetzt, aber nicht für Launcher).

#### 7.7.11 Run wurde vorzeitig mit Ctrl-C abgebrochen

**Schweregrad: ℹ️ Info**

Die Terminal-Ausgabe endet mit "mit Ctrl-C in der PowerShell abgebrochen" (Z.2753). Der Run hat nur 8/14 Modelle vollständig durchlaufen. Die Modelle 9-14 (GLM 4.7 Flash, LFM2 24B, GPT-OSS 20B × 2) wurden nicht durchlaufen.

**Auswirkung:** Konsolidierte Ergebnisse für Modelle 9-14 fehlen in der Auswertung.

---

## 8. Empfehlungen (priorisiert)

### 🔴 Prio 1 (sofort) — ✅ ALLE BEHOBEN (12.07.2026)

1. ✅ **`tests/test_csv.py:4` reparieren** — Import auf v13, Fixture erstellt
2. ✅ **Channel-Error-Handling** in `custom_benchmark.py` — Auto-Fallback auf `--no-structured-output` via `[CHANNEL-ERROR]`-Marker
3. ✅ **`wait_for_model_ready` Timeout** auf 60s — Default 90s → 120s als Sicherheitsnetz
4. ✅ **Reload-Logik** via `_ensure_model_still_loaded()`-Helper auf alle 4 Pipelines ausgedehnt

### 🟠 Prio 2 (zeitnah) — ✅ ALLE BEHOBEN (12.07.2026)

5. ✅ **`_lookup_vram` Fuzzy-Match fixen** — Length-Ratio-Guard >=0.85, Publisher-Prefix-Liste erweitert, `best_score`-Tracking
6. ✅ **`strip_thinking_tokens` Token-Estimation** — `max(word_count * 1.3, char // 4)` + Whitespace-spezial-Case (1 Token pro 64 chars)
7. ✅ **`QUANT_MAP` Konflikt-Auflösung** — `get_quant()` Helper mit expliziter Priorität (exact > suffix > base)
8. ✅ **`response` Spalte komprimiert** — `--keep-response` CLI-Flag, `_truncate_response()` (default 200 chars)
9. ✅ **Bootstrap-CI auf NumPy** — `np.random.randint` + `np.partition`, 300-500x Speedup (9-12ms statt 3-5s)

### 🟡 Prio 3 (refactoring) — ✅ ALLE BEHOBEN (12.07.2026)

10. ✅ **MMLU-Pro-Code** — `run_mmlupro_modified` + MMLU-Aggregation aus `consolidate_results.py` entfernt. **Self-contained Archiv-Script** erstellt: `Archiv/run_mmlupro_benchmark.py` (kann bei Bedarf standalone aufgerufen werden, ohne aktiven Launcher zu berühren). `MMLU_PRO_SUBSETS` bleibt in `benchmark_config.py` mit `MMLU_PRO_ENABLED = False`.
11. ✅ **Legacy-Aliase** in `csv_writer.py` + Aufrufer in `run_benchmarks.py` + `custom_benchmark.py` — `save_csv`, `save_model_summary`, `save_model_summary_csv` entfernt. Direkt die offiziellen Funktionsnamen nutzen.
12. ✅ **Subprozess-Pfad-Logging** in `run_benchmarks.py:139-153` — gibt jetzt beim Start aus: `[INFO] Using custom_benchmark script: custom_benchmark.py (version v13)`, Subprozess-Interpreter, Repo-Root.
13. ✅ **Doppelte Thinking-Konfiguration** zentralisiert in `benchmark_config.THINKING_CONFIG` (Prio 3.13). `MODEL_CONFIG` in `custom_benchmark.py` ist jetzt ein Alias auf `THINKING_CONFIG`. Doku in `thinking_config.md` ist jetzt korrekt.
14. ✅ **`download_real_benchmarks.py`** mit DEPRECATED-Header versehen. Installations-Skripte melden jetzt `[INFO] download_real_benchmarks.py ist DEPRECATED`.

### 🟢 Prio 4 (langfristig) — ✅ MEISTE BEHOBEN (12.07.2026)

15. ✅ **CI mit GitHub Actions** — `.github/workflows/ci.yml` mit 3 Jobs (test, lint, typecheck). `pyproject.toml` mit `ruff` + `pytest` + `mypy` Konfiguration.
16. 🟡 **Test-Coverage auf 60%+** — aktuell ~10% geschätzt (vorher 5%; hinzugefügt: `test_dependencies.py` 7, `test_prio2_terminal.py` 25). Eine Erhöhung auf 60% würde LM-Studio-Mocking erfordern.
17. ✅ **README + Doku-Versionierung** — `VERSION` File (Single Source of Truth) erstellt. README zeigt jetzt auf `VERSION`. Architektur-Doku mit `v13.0.0-p3` aktualisiert. Launcher liest Version aus `VERSION` Datei.
18. ✅ **Version-Konvention** — `VERSION` File + `pyproject.toml` + `__version__` in `run_benchmarks.py` synced.

---

## 7.8 Nachträglich entdeckte Befunde (12.07.2026)

**Diese Befunde wurden nach dem initialen Review durch den User-Hinweis auf die Datei `Terminalausgabe Benchmark Run mit neuen Benchmarks und SampleSize 10.md` identifiziert. Sie waren NICHT Teil des ursprünglichen Review-Scopes.**

### Fix-Status aller Prio-0/2/3-Befunde (12.07.2026)

| # | Befund | Schwere | Status | Geänderte Dateien |
|---|--------|---------|--------|-------------------|
| 19 | `langdetect` fehlt → IFEval 14/14 fail | 🔴 | ✅ BEHOBEN | `install_benchmark-data_windows.ps1`, `install_benchmark-data_debian.sh`, `README.md`, `tests/test_dependencies.py` |
| 20 | `math_verify`/`sympy`/`antlr4==4.11` fehlt → MATH-500 14/14 fail | 🔴 | ✅ BEHOBEN | (gleiche Dateien) |
| 20+ | `immutabledict` fehlt → IFEval-Transitive-Dep | 🔴 | ✅ BEHOBEN | (gleiche Dateien) |
| 21 | Installations-Skripte updaten | 🟠 | ✅ BEHOBEN | `install_benchmark-data_windows.ps1` + Debian + README |
| 22 | `truthfulqa_gen` → `truthfulqa_mc1` | 🟠 | ✅ BEHOBEN | `run_benchmarks.py:176`, `consolidate_results.py:661`, `run_np_calibration.ps1:93` |
| 23 | DS1000 `_unwrap_solution_for_insert` | 🟠 | ✅ BEHOBEN | `custom_benchmark.py:1090-1175` — multiple `[insert]` markers, comment-skip, synthetic function wrapper |
| 24 | DS1000 matplotlib `set_xticklabels` patch | 🟠 | ✅ BEHOBEN | `custom_benchmark.py:_patch_matplotlib_compat()` (neu) |
| 25 | CoderEval `extract_code` Granite | 🟠 | ✅ BEHOBEN | `custom_benchmark.py:775-832` — alternative code-block patterns, bare-statement fallback |
| 26 | PowerShell UTF-8 Encoding | 🟢 | ✅ BEHOBEN | `run_missing_benchmarks.ps1`, `run_np_calibration.ps1`, `run_v18_models.ps1` |

**Test-Suite:** `pytest tests/` → **43/43 passed** (vorher 36/36; +7 für `tests/test_dependencies.py`).

### Original-Befunde (zur Referenz)

### 🔴 Prio 0 — Dependencies fehlen (alle IFEval + MATH-500 Runs sind Datenmüll)

19. **`pip install langdetect`** — IFEval kann nicht ausgeführt werden, alle 14 Modelle returnen `ModuleNotFoundError: No module named 'langdetect'`. **Folge:** IFEval-Scores komplett fehlend, Konsolidierung kann Agentic+IFEval-Mix nicht berechnen.
20. **`pip install lm-eval[math]`** (oder `sympy` + `math_verify` + `antlr4-python3-runtime==4.11`) — MATH-500 kann nicht ausgeführt werden, alle 14 Modelle returnen `ModuleNotFoundError`. **Folge:** `Math`-Score in `consolidate_results.py:compute_category_scores` ist `None` für alle Modelle, **das gesamte `cat_weights["math"]` ist nutzlos**.
21. **Installations-Skript aktualisieren** — `Doku-intern/Doku-intern/install_benchmark-data_windows.ps1` muss diese Dependencies mit-installieren. Aktuell fehlt dieser Hinweis komplett.

### 🟠 Prio 2 — Benchmark-Konfiguration

22. **`truthfulqa_gen` → `truthfulqa_mc1`** in `benchmark_config.py:177` und `run_benchmarks.py:176` — `bleu_acc=0` weil Modelle nur Buchstaben A/B/C/D zurückgeben, nicht volle Antwort-Texte. `mc1` extrahiert die korrekte Wahl.
23. **DS1000-Harness `_unwrap_solution_for_insert`** (`custom_benchmark.py:1036-1110`) überarbeiten — die Code-Stripping-Logik verliert bei Granite-Modellen zu viel Code. Tests mit längeren `[insert]`-Markern schlagen fehl.
24. **DS1000 matplotlib-API-Compat:** `set_xticklabels` patches → `ax.set_xticklabels(...)`. Generierter Code ruft `plt.set_xticklabels` auf, was in neueren Matplotlib-Versionen nicht mehr existiert.
25. **CoderEval `extract_code`** (`custom_benchmark.py:721-764`) verbessern — Granite-Modelle schreiben Code in einem anderen Stil (kein Markdown-Wrapper) und werden als leerer String extrahiert.

### 🟡 Prio 3 — Log/Encoding

26. **PowerShell-Encoding fixen** — `PYTHONIOENCODING=utf-8` und `chcp 65001` in PowerShell-Wrapper-Skripts (`run_missing_benchmarks.ps1`, `run_np_calibration.ps1`) für saubere Unicode-Ausgabe in Terminal-Logs.

---

## 9. Positive Gesamteinschätzung

Trotz der obigen Befunde ist die Code-Qualität überdurchschnittlich:

- **Klare Architektur** mit sauberer Schichtentrennung
- **Deterministische Reproduzierbarkeit** (--seed, Bootstrap-CI)
- **Robuste Fehlerbehandlung** (Streaming-Retries, Sandbox-Blocklist, Timeouts)
- **Strukturiertes Logging** (CPU/GPU/RAM/VRAM pro Task, Thinking-Anteil)
- **Statistische Aussagekraft** (gewichtet, Bootstrap-CI, Pair-Vergleiche)
- **Umfassende Doku** (Modell-Steckbriefe, Architektur, Thinking-Config, Parallel-Slots-Optimierung)

Die Hauptbaustellen sind: (a) kaputte Tests, (b) Channel-Error-Handling bei `response_format`+`lazy grammar`-Inkompatibilität, (c) einige Fuzzy-Match-Bugs in der Konsolidierung. Alles gezielt behebar in 1-2 Sprints.

---

*Review erstellt am 12.07.2026 (Plan Mode) – keine Code-Änderungen vorgenommen.*
