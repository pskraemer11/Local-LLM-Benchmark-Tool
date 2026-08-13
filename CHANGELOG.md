# CHANGELOG

Zentrales Änderungslog für das Local-LLM-Benchmark-Tool. Neueste Einträge zuerst.

Hinweise:
- Stand: 06.08.2026 — umgezogen aus §20 der `doc-git/Architecture, Flow & ChangeLog_en.md` (dort nur noch Verweis).
- Commit-Hashes beziehen sich auf `main`.

## Registry-Sampling (SSOT) – Plan & Migration (13.08.2026)

| Date | File | Change |
|------|------|--------|
| 13.08. | `doc-git/model_registry.yaml` | **Sampling-Felder (Variante A):** 17 Modelle mit `sampling:`-Block (coding/knowledge/agentic/math + thinking-Unterblock), befüllt mit den recherchierten temperature/top_p aus `MODEL_CATEGORY_SAMPLING` (vorher Platzhalter 0.6/0.95). `intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround` Block entfernt (keine recherchierte Zeile → Fallback korrekt). Kategorien ohne recherchierten Wert (z.B. ernie coding) nicht im Block → Fallback greift |
| 13.08. | `src/benchmark_config.py` | **Reader-Umbau (Lesepfade):** `+_registry_sampling_block()` (match_registry_key gegen Registry-Keys), `+_sampling_cell()` (Zelle + Quelle), `get_model_config` liest Registry-first. Precedence: Registry-`sampling:` → `MODEL_CATEGORY_SAMPLING` → Kategorie-/Thinking-Defaults. Neue `_source`-Variante "registry-sampling" |
| 13.08. | `src/benchmark_config.py` | **Entscheidung:** Reader übernimmt NUR temperature/top_p aus der Registry; top_k/min_p/enable_thinking weiterhin aus LMS-JSON (GUI/`--thinking`). `MODEL_CATEGORY_SAMPLING` bleibt als Fallback (30 Modelle ohne Block) |
| 13.08. | `tests/test_benchmark_config.py` | **7 neue Registry-Sampling-Tests** (recherchierte Werte, partielle Blöcke, Fallback Registry→Tabelle→Default); 2 Tests auf `_source="registry-sampling"` umgestellt |
| 13.08. | `doc-git/Planung/registry_sampling.md` + `registry_sampling_log.md` | **Migrationsplan + Log:** Schritte 1–6 abgeschlossen, Schritt 7 (Doku/HowTo) offen |
| 13.08. | gesamt | **Verifikation:** 148 relevante Tests grün, volle Suite 790 passed / 3 pre-existing TabbyAPI-Fehler; End-to-End 0 MISMATCH vs. Recherche; `validate` ohne neue Drifts |

## QUANT_MAP-Entfernung + Framework-Unabhängigkeit (11.08.2026, abends)

| Date | File | Change |
|------|------|--------|
| 11.08. | `src/benchmark_config.py` | **QUANT_MAP entfernt** (redundant). `get_quant()` extrahiert @quant direkt aus dem Key (`publisher/model@quant`). `extract_quant_from_key()` + `guess_quant_from_filename()` als Helper. UKV-Threshold 14.0→12.0 |
| 11.08. | `src/benchmark_config.py` | `is_support_file`: Filtert `*imatrix*` Dateien (Begleitdateien, < 200 MB) |
| 11.08. | `src/registry_tool.py` | **fill-quant**: Neuer Command — liest @quant aus GGUF-Dateiname (Source of Truth), ergänzt Registry-Keys ohne Quant. Hilfsfunktion `_gguf_quant_from_header()` mit bekannten Quant-Patterns |
| 11.08. | `src/registry_tool.py` | **fill-size**: Dateisystem als Primärquelle (nicht LMS), LMS als Fallback. Hilfsfunktion `_find_gguf_for_key()` |
| 11.08. | `src/registry_tool.py` | **fix_np**: Dateisystem-basiert (kein LMS erforderlich). `_identity_triple_from_key()` für kanonische (publisher, model, quant) Extraktion. Base-Entry-Cleanup wenn @quant-Variante existiert |
| 11.08. | `src/model_identity.py` | **model_identity_triple()**: Extrahiert (publisher, model, quant) — kanonische Identität. `UKV_FORCE_TRUE_MODELS` (gemma-4, kimi-linear, gpt-oss) |
| 11.08. | `src/field_owner.py` | np/UKV/offload/context_length → `source="registry"` (SSOT seit 11.08.), nicht mehr "config" |
| 11.08. | `src/consolidate_results.py` | QUANT_MAP-Referenzen entfernt, `extract_quant_from_key` stattdessen |
| 11.08. | `tests/` | Alle Tests angepasst: QUANT_MAP-Imports entfernt, neue Test-Logik für Key-basierte Quant-Extraktion. 783 Tests grün |

## Registry als SSOT + Benchmark-Infrastruktur (11.08.2026)

| Date | File | Change |
|------|------|--------|
| 11.08. | `src/benchmark_config.py` | **UKV-Threshold 12.0** (war 14.0): `USE_UNIFIED_KV_CACHE_THRESHOLD_GB = 12.0`. Spezialfälle `UKV_DISABLE_MODELS = {gemma-4, kimi-linear, gpt-oss}` (keine KV-Quantisierung vertragen → immer UKV=False). `should_use_unified_kv_cache()` Helper mit Spezialfall-Logik |
| 11.08. | `doc-git/model_registry.yaml` | **Registry als SSOT**: Alle Modelle `num_parallel=4` (explizit via API). UKV aus Formel (>=12GB) + Spezialfälle. `glmv-4.6v-flash` completeness (reasoning, capabilities, blueprint, max_context_length=131072). `context_length=98304` (Benchmark-Wert, nicht GGUF-Native-Max) |
| 11.08. | `src/registry_tool.py` | **Drift-Check entfernt**: `config_np_ukv_drift` aus `_DRIFT_CHECKS` und `cmd_validate` entfernt (Configs irrelevant, Registry ist SSOT). `cmd_pipeline` ignoriert np/ukv-Drifts. Unused vars entfernt |
| 11.08. | `src/model_manager.py` | **echo_load_config**: Load-Payload enthält `echo_load_config: True`, Log zeigt `np=<wert>` (z.B. `Loaded in 5.4s (np=4)`) — verifizierbarer Beweis für korrektes np |
| 11.08. | `src/assemble_blueprint.py` | **99 LMS-Configs**: `numParallelSessions=4` + `useUnifiedKvCache` in `load.fields` (nicht `operation.fields`) korrigiert — `read_lms_configs` liest aus `data["load"]["fields"]` |
| 11.08. | `pre_review_checks.ps1` | **GGUF-Check Fix**: 5-Tupel-Unpack (`nl, hd, _is_reasoning, ctx, _exp`) für geänderte `_read_gguf_arch` Signatur |
| 11.08. | `tests/test_registry_tool.py` | **Test-Updates**: `test_drift_checks_constant` ohne `config_np_ukv_drift`, `test_open_drift_exits_1` nutzt `config_context_drift` statt `config_np_ukv_drift` |
| 11.08. | `doc-git/Developer-Docs/LM-Studio-API-References.md` | **Neue Doku**: LM Studio REST API (Load + Chat Completions), TypeScript SDK (`LLMLoadModelConfig`, `LLMPredictionConfigInput`). Kritischer Fund: `numParallelSessions` + `useUnifiedKvCache` sind **nicht in der API** — nur via JSON-Config setzbar |
| 11.08. | `scripts/run-pass2-after-pass1.ps1` | **Auto-Sequencing**: Wartet auf Pass 1, startet Pass 2 automatisch |
| 11.08. | `run-qwen-rerun-both-passes.bat` | **Verbessert**: Per-Pass-Logging mit Zeitstempel |
| 11.08. | `~/.agents/skills/compaction/SKILL.md` | **Neuer Skill**: Auto-Compaction bei ~80% Kontext (Token-Einsparung). Format + Workflow in `doc-git/Developer-Docs/Compaction-Workflow.md` |
| 11.08. | `~/.agents/skills/*/SKILL.md` | **Gekürzt**: Alle Skills < 1.3KB (waren bis 9.3KB) — weniger Token-Verbrauch pro Prompt |
| 11.08. | `compaction/SKILL.md` + `Compaction-Workflow.md` | **Trigger geändert**: Nicht mehr Token-Länge (1M ctx irrelevant), stattdessen Event-basiert: commit/push, Architekturentscheidungen, Bug-Fixes, ~20-30 Messages, mind. 2x/Tag |

## Registry-Wartung (10.08.2026)

| Date | File | Change |
|------|------|--------|
| 10.08. | `src/registry_tool.py` | **validate-Performance-Fix:** `_gguf_drift_errors` (und `cmd_sync_from_gguf`) lasen jede GGUF **zweimal** — parallel via `_read_gguf_arch`, danach sequenziell via `_gguf_has_experts` (gguf-Bibliothek, öffnet jede Datei komplett) → `validate` hing 240s+. `_read_gguf_arch` liefert jetzt `expert_count` als 5. Rückgabewert (mitgelesen aus dem GGUF-Header), MoE-Erkennung erfolgt direkt im parallelen ThreadPool → `validate` in **6s** (38× schneller), 0 Registry-Drifts. `_gguf_has_experts` bleibt nur für `_classify_arch` (Z. 841). +3 Tests angepasst auf 5-Tupel |
| 10.08. | `doc-git/model_registry.yaml` | `crucible-labs/gemma4-26b-a4b-reap-25`: `context_length` 24576 → 65536 (Config-Feld-Owner ist Quelle) — 1. `validate`-Drift nach dem Fix |
| 10.08. | `src/registry_tool.py` + `tests/test_registry_tool.py` | **`quarantine-missing`-Kommando:** entfernt Registry-Einträge nicht-installierter Modelle reversibel (Configs nach `_quarantine_missing_<ts>` verschieben, Einträge als YAML-Backup unter `doc-git/Review-Artifacts/`, nichts hart gelöscht). Strenge @-Quant-Erkennung (x@iq4_nl nur installiert, wenn LMS exakt diese Variante führt; `normalize_variants` strippt @-Suffixe → Basis-Varianten maskieren keine fehlenden Quants). Sicherheitsnetz `_gguf_for_key_exists`: GGUF physisch vorhanden → nur melden (Index-Problem wie GLM-4.6V), kein Auto-Entfernen. Config-Verschiebung nur, wenn kein anderer verbleibender Registry-Key sie beansprucht (`_config_claimed_by_other`, verhindert Mitnahme z.B. `google/gemma-4-26b-a4b-it-qat` → unsloth-Config). Eingebunden in `pipeline full` als Schritt [2b]; `--dry-run`-Flag; Exit-Code 2 wenn nur gemeldet. **Lauf 10.08.:** 9 Modelle quarantänt (u.a. `mradermacher/nemotron-cascade-14b-thinking`, `mistralai/codestral-22b-v0.1`, `intel/mirothinker-v1.5-30b-q2ks-mixed-autoround`, 8× fehlende GGUF-Dateien verifiziert), 9 nur gemeldet (physisch vorhanden, z.B. `unsloth/ernie-4.5-21b-a3b-pt@iq4_nl`); `pipeline full` danach: `missing: 0`, 56 assembled, Validation 74/74. +6 Tests (TestCmdQuarantineMissing), ruff 0 |

## Review-Gate & Cleanup (06.08.2026)

| Date | File | Change |
|------|------|--------|
| 06.08. | gesamt | **Baseline-Cleanup (Commit `7e49cb8`):** Tool-Configs (ruff/mypy/pytest/pylint) in sichtbarem Root-`pyproject.toml` konsolidiert, versteckte `.ruff.toml`/`.pyproject.toml` entfernt; ruff 531→0 Fehler; B023-Thread-Bug in `custom_benchmark.py` gefixt (Default-Argument-Frozen in Thread-Closures, ~Z. 589-599); TYPE_CHECKING-Blöcke, B905 `strict=True`, ANN-, RUF003-, PERF402-Fixes; Re-Export `_USE_UNIFIED_KV_CACHE_THRESHOLD_GB` + `# noqa: F401` wiederhergestellt; mypy: 195 Legacy-Fehler (informativ, nicht blockierend) |
| 06.08. | `src/registry_tool.py` | **validate --verbose/--repro (Commit `0427387`):** `--verbose` zeigt alle Einzelprobleme; `--repro` schreibt `doc-git/Review-Artifacts/repro_issues.md` (Registry vs. LM-Studio-Hub `model.yaml`: arch/max_context_length/context_length/reasoning) — 1 echte Abweichung (`qwen/qwen3.5-9b` reasoning `instruct` vs. Hub `true`, siehe Planung Punkt 18), 57 ohne Hub-yaml (Hub-Hinweise); `validate` liefert jetzt Exit-Code 1 bei Registry-Problemen (Gate-Kriterium) |
| 06.08. | `pre_review_checks.ps1` | **v2-Rewrite:** [1] validate --repro → `repro_issues.md` (blockierend), [2] ruff → `lint_issues.md` (blockierend), [3] mypy (nur informativ), [4] pytest (blockierend), [5] GGUF-Header-Check → `gguf_issues.md` (Source-of-Truth, 40 Einträge/0 Abweichungen, ersetzt toten `_check_gguf_ctx.py`-Aufruf); `-NoTranscript`-Modus |
| 06.08. | `scripts/` | **pre-push-Hook (Commit `830b6769`):** `core.hooksPath` → `scripts/hooks` (Install/Uninstall via `scripts/install-hooks.ps1`); `scripts/pre-push.ps1` liest Push-Refs von stdin und führt das komplette Gate aus — jeder `git push` ist review-blockiert bis grün |
| 06.08. | `.github/workflows/review.yml` | **CI-Fix (Commit `4bf5a74`):** `runs-on: windows-2025` (statt ungültigem "Windows 11"), `actions/setup-python@v5` (3.14), echte Deps je Job (ruamel.yaml/psutil/gguf/requests/pynvml/pytest-mock/responses) statt `pip install -e .` (kein `[project]`-Abschnitt); mypy-Job `continue-on-error: true`; validate-Job nutzt neuen Exit-Code |
| 06.08. | `doc-git/Planung.md` | Punkt 18: qwen3.5-9b Reasoning-Einstufung klären (alle Qwen 3.5/3.6 sind Dual-Mode mit Thinking-Toggle laut Model Card; Registry intern inkonsistent: nur `qwen/qwen3.5-9b` `instruct`, alle anderen Qwen3.5/3.6-Einträge `thinking`) |
| 06.08. | `doc-git/model_registry.yaml` + `src/assemble_blueprint.py` | **Punkt 18 abgeschlossen:** `qwen/qwen3.5-9b` → `reasoning: thinking` (konsistent mit @q6_k-Variante + Hub `reasoning: true`; wirkt in `custom_benchmark._model_supports_reasoning`, run_benchmarks hatte `_is_qwen3_6_model()` bereits) + `max_context_length: 262144` nachgetragen (Hub-Wert, fehlte obwohl `fill-arch` es auffüllen sollte); Kommentar `assemble_blueprint.py:248-249` korrigiert („Default Non-Thinking" → „Default Thinking, enableThinking defaultValue: true laut Hub/Qwen-Model-Card"); enable_thinking-Handling geprüft: Thinking-Lauf erzwingt `enable_thinking: True` (REASONING_PATTERNS enthält qwen3.5/3.6), kein Code-Change nötig. `validate --repro`: **0 Abweichungen** (repro_issues.md wieder sauber), ruff 0, 741 Tests grün |

## Historie (umgezogen aus §20, Architecture-File)

| Date   | File                                         | Change                                                                           |
|--------|-----------------------------------------------|----------------------------------------------------------------------------------|
| 03.08. | `src/benchmark_config.py` + `src/model_manager.py` + `src/registry_tool.py` | **F1 MTP-Drafter-Filter (Review 03.08.):** `is_support_file()` zentralisiert in `benchmark_config.py`; `get_available_models()` filtert MTP-Drafter (`mtp-*`, `MTP/`-Ordner, `-assistant`-Architektur) und `mmproj*` – die Dauerwarnung beim Laufstart ist beseitigt, legitime MTP-Modelle (z.B. `qwen3.6-27b-mtp`) bleiben sichtbar |
| 03.08. | `src/tools/inject_chat_templates.py` | **F2 Granite-Templates:** Chat-Templates für 5 Granite-Modelle injiziert (12 Config-JSONs); `registry_tool.py validate` = 0 Probleme |
| 03.08. | `src/custom_benchmark.py` + `src/consolidate_results.py` | **F3 Doku/main()-Zerlegung:** alle NO-DOC-Funktionen dokumentiert; `main()` in benannte Teilfunktionen zerlegt (custom: `_parse_args`, `_verify_environment`, `_resolve_benchmarks`, `_resolve_models`, `_run_model_loop`, `_print_summary`; consolidate: `_parse_args`, `_read_all_data`, `_write_csv`, `_write_markdown`) |
| 03.08. | `src/run_benchmarks.py`, `src/custom_benchmark.py`, `src/consolidate_results.py`, `src/registry_tool.py` | **F4 CWD-unabhängige Einstiegspunkte:** sys.path-Bootstrap vor allen src-Imports – `python -m src.*` funktioniert aus jedem Verzeichnis |
| 03.08. | `src/custom_benchmark.py` + `doc-git/model_registry.yaml` | **F5 Codestral-Structured-Output-Schutz:** `_can_use_structured_output()` schließt `codestral` aus (Grammar-Channel-Errors, Server-Log 03.08.); Registry-Notiz für Grammar-400er; +7 Tests `TestCanUseStructuredOutput` |
| 03.08. | `tests/` | **+9 Tests (Review 03.08., F1/F5):** `test_model_manager.py` 76→78 (MTP-Drafter/mmproj-Filter), `test_prio2.py` 35→42 (`TestCanUseStructuredOutput`). Suite: **713 passing, 0 failing** |
| 03.08. | `doc-git/Reviews/` | **Review 2026-08-03:** Code-Review F1–F5 umgesetzt (siehe `Code-Review_2026-08-03_de.md`); 8 veraltete `_de.md`-Reviews entfernt |
| 02.08. | `src/custom_benchmark.py` (+`csv_writer.py`, `type_defs.py`) | **P1 Struktur-Gate (v13.0.10):** `classify_output()` → `output_status` (`empty`/`json_ok`/`json_missing_code`/`json_invalid`/`fenced`/`bare`) + `entry_point_found` (Regex-Triage) + `extracted_code`. Neue CSV-Spalten in `TASK_FIELDS`, `--keep-response` für Volltext. Reine Telemetrie, keine Score-Änderung |
| 02.08. | `src/benchmark_config.py` + `src/run_benchmarks.py` | **P4 Agentic-Safety (v13.0.10):** `AGENTIC_SAFETY_SCENARIO_IDS` (13 Category-K TC-31..36/41..43/57..60), `run_agentic(mode, seed)` + `--agentic-mode {random,safety}`, deterministisch via `random.Random(seed)` |
| 02.08. | `src/run_benchmarks.py` + `src/tools/parallel_ab.py` (+Tests) | **P3 YAML-Run-Spec (v13.0.10):** `--run-spec/--config run.yaml`, SUPPRESS-Probe-Parser (CLI>YAML>Defaults), `build_prompts(seed)` + `--seed`. Beispiel: `run.example.yaml` |
| 02.08. | `src/benchmark_config.py`, `src/assemble_blueprint.py`, `src/tools/patch_reasoning_effort.py` | **gpt-oss Reason-Logik zentralisiert:** `GPTOSS_REASONING_EFFORT="medium"` / `GPTOSS_REASONING_BUDGET=4096` – steuern Engine-Config UND `gptoss_reasoning`-Blueprint synchron |
| 02.08. | `src/benchmark_config.py` | **Bonsai-Temperature-Overrides:** `bonsai-27b` temp=0.7/top_p=0.95/top_k=20, `bonsai-8b` temp=0.6 (Herstellermk.; ohne Override liefen sie greedy `temp=0.0` → schlechte DS1000-Scores) |
| 02.08. | `doc-git/model_registry.yaml` | **Registry-Sync:** +53 Modelle (via `registry_tool.py sync`: 53 assembled, 191 validated) – u.a. Bonsai-8B/27B@Q1_0, Qwen3.5, GLM-4.7-Flash-ReAP |
| 02.08. | `sync_model_configs.ps1` | **Pfad-Fix (src/-Migration):** referenzierte `registry_tool.py`/`assemble_blueprint.py` aus dem Projekt-Root (veraltet). Jetzt via `$SRC = <root>\src` – `-AutoAdd`/`-FullSync` funktionieren wieder (Fehlernachweis: `Test-Path` Root `False`, `src/` `True`) |
| 02.08. | `doc-git/HowTo-Install-and-Configure-New-LLM_en.md` | **Neue Phase E (Modell entfernen):** `registry_tool.py rm <key> [--delete-files] [--yes]` – entfernt Registry-Eintrag, optional JSON-Configs (+ `.bak-*`) und GGUF-Dateien (immer `--delete-files` für "alles löschen"). CLI-Aufruf `-AutoAdd`/intern `src/`-Hinweis ergänzt |
| 02.08. | gesamt                         | **DS1000-Re-Run mit Struktur-Gate (4 Modelle, seed=2026):** Ternary-Bonsai 0.10, gpt-oss 0.20, Bonsai 27B@Q1_0 0.30, Bonsai 8B 0.60. Details: Sektion 7 der Auswertungsdatei |
| 01.08. | `src/run_benchmarks.py`                     | **IFEval peg-native-Fix (GGUF-EOS-Fallback):** `_get_model_eos_string()` liest EOS aus GGUF-Header (cached) → `eos_string` nur für Tasks ohne YAML `until` (z.B. IFEval). Behebt HTTP 500 „peg-native format" (llama#20260). stderr-Kurzfassung |
| 01.08. | `src/custom_benchmark.py`                     | **BUGFIX Stop-String:** `STOP_TOKENS_CODING` `"\n```"` → `"\n```\n"` (Z. 192). `\n```` matchte die Codeblock-Öffnung von DeepSeek-R1-Distill → 0% DS1000/CoderEval ("No code generated"). Verifiziert: DS1000 35%, CoderEval 67% (seed 42, SS20) statt 0%. Details §15 + thinking-config_en.md |
| 01.08. | `src/consolidate_results.py`                  | **SampleSize-Angabe + Tabellen-Formatierung:** MD-Header zeigt `SampleSize=5,20 (DS1000), …` statt `mixed` (`_describe_sample_sizes`, `_collect_pipeline_sample_sizes`, `_extract_csv_sizes`). Tabellen content-driven: längster Modellname bestimmt Breite, `|` fluchten vertikal, Dezimalpunkte ausgerichtet (`_render_complete_table`, `_align_decimal_cells`, `_write_tbl`) |
| 01.08. | `src/run_benchmarks.py`                       | **Single-Instance-Lock:** `.benchmark.lock` (PID+Startzeit) verhindert parallele Launcher (31.07.: 3 Läufe → RAM-Exhaustion). Stale Locks werden überschrieben |
| 31.07. | `src/benchmark_config.py`                     | **Registry-getriebenes enable_thinking:** `_registry_reasoning()`; `get_model_config()` setzt `enable_thinking=True`, wenn Registry `reasoning: thinking` und kein Override existiert (DeepSeek denkt standardmäßig). Details §2.6 |
| 31.07. | `src/custom_benchmark.py`                     | **Streaming-Thinking-Fixes:** `_extract_reasoning_delta()` (unterstützt `reasoning_content` + `reasoning`/gpt-oss); Start-/Stall-Timeout zählt Thinking-Streams; `_non_streaming_fallback` liest `reasoning_content`; `_uses_qwen_template()` deckt Qwen-basierte Distills (deepseek-r1-distill-qwen-14b) |
| 31.07. | `src/registry_tool.py`                        | **NEW `rm`-Befehl:** Registry-Eintrag löschen (optional `--delete-files` + Configs). **Pfad-Auflösung:** `_resolve_model_path_multi()` (exakt → Substring → Word-Match ≥2 Wörter); `_normalize_variants()`/`_quant_variant()` |
| 31.07. | `src/assemble_blueprint.py`                   | **gpt-oss → thinking** in `_ARCH_REASONING_MAP` (Harmony-Template, Review 27.07.). **Qwen3-Familie name-basiert:** `-instruct` → instruct, `-thinking` → thinking |
| 31.07. | `src/csv_writer.py`                           | `_fmt_float()` – None-sichere Zahlenformatierung |
| 31.07. | `doc-git/model_registry.yaml`                 | Bereinigt: nicht-installierte Varianten entfernt (u.a. Intel/gpt-oss-20b-q4ks-autoround, opea-gemma3-autoround, noctrex/lfm2, jetbrains/mellum2-thinking); `rnj-1` arch → `dense` |
| 31.07. | `src/tools/parallel_ab.py` (+Tests)           | **NEW A/B-Slots-Test:** vergleicht `num_parallel` (1/2/4) je Modell. Ergebnis 31.07./01.08.: `num_parallel: 4` bestätigt (Rang 1, 4 von 5 Modellen) – siehe `ergebnisse/parallel_ab_20260801_004539.md` |
| 31.07. | `src/tools/patch_reasoning_effort.py` (+Tests) | **NEW** Hilfstool für reasoning_effort-Patches |
| 30.07. | gesamt (v13.0.7)                              | **Coding-Textbausteine erweitert** (blueprint_definitions.yaml, assemble_blueprint), **Template-Injection**, **Name-Normalisierung** (registry_tool.py), Registry-Updates |
| 30.07. | gesamt (v13.0.6)                              | **src/-Migration abgeschlossen:** alle Scripts nach `src/` (custom_benchmark_v13.py, run_benchmarks_v13.py, consolidate_results_v13.py entfernt), CLI-Menü, quants-Normalisierung, `.pylintrc`, `run_lint.ps1`, README/Doku-Update |
| 29.07. | `utils/terminal.py`                           | **NEW:** ANSI-Farben + Progress-Bar Utility (`ok`, `warn`, `error`, `info`, `progress_bar`) – löst §2.3 "Keine visuellen Indikatoren" |
| 29.07. | `src/type_defs.py`                                | **NEW `GenerationConfig`-Dataclass:** `generate_answer()` von 16 Einzelparametern auf `cfg: GenerationConfig` umgestellt (P3-Befund aus Review 28.07.) |
| 29.07. | `src/custom_benchmark.py`                         | **Refactored `run_task()`:** 4 Helfer extrahiert (`_call_and_evaluate`, `_make_codereval_prompt`, `_make_datascience_prompt`, `_extract_setup_code`) – löst P3 "run_task()-Duplikation" |
| 29.07. | `src/run_benchmarks.py`                           | **`run_agentic()` umgestellt:** `subprocess.run` → `Popen` + Thread mit Live-Output-Fortschritt. Dynamischer Timeout: `limit * agentic_scenario + 600` statt fixer 3600s (P2 "PIPELINE_TIMEOUTS") |
| 29.07. | `src/consolidate_results.py`                      | **`main()` gesplittet:** 407→292 Zeilen. 3 Inline-Helfer auf Modulebene + `_run_comparison_mode()` extrahiert (P3 "main() >200 Zeilen") |
| 29.07. | `src/assemble_blueprint.py`                       | **Typ-Hints auf 100%:** 6 Funktionen ergänzt (`format_publishers`, `format_capabilities`, `classify_registry`, `create_blueprint_definitions`, `assemble_prompts`, `validate_prompts`) – löst P3 "Typ-Hint-Lücken" |
| 29.07. | alle 9 Skripte                                | **Terminal-Farben integriert:** ANSI `ok`/`warn`/`error`/`info` ersetzen `[OK]`/`[WARN]`/`[ERROR]`/`[INFO]`-Prefixe |
| 29.07. | `doc-git/thinking-config.md`                  | **Überarbeitet:** `chat_template_kwargs` nur für Qwen3/Qwen3.5 (Quelle: lmstudio-bug-tracker#1573). `reasoning_effort: low` für gpt-oss. MATH max_tokens 8192→4096 |
| 29.07. | `doc-git/Architecture-and-Flow.md`             | **§5 Agentic aktualisiert:** CLI-Diagramm auf v2.0.7, `max_tokens`-Patch-Doku durch v2.0.7-Änderungen ersetzt (`--no-think`, `--backend-kwargs`) |
| 29.07. | `doc-git/Jinja-Chat-Templates/`               | **4 neue Templates + 2 Configs:** `google_gemma-4-12B-it-qat-q4_0` (Jinja + Config), `google_gemma-4-26B-A4B-it` (Jinja + Config), `phi-4_template_unsloth.jinja`, `gpt-oss-20b-template_unsloth.jinja` |
| 29.07. | Benchmark-Lauf                                | **3 Modelle × 4 Pipelines × SampleSize 5** erfolgreich durchgelaufen (~34 Min). Server-Log-Analyse: 2 Channel Errors (structured output + lazy grammar, recovered). |
| 29.07. | `doc-git/Reviews/Code-Review_2026-07-28.md`   | **ISO/IEC 9126 Review** – siehe separates Dokument für ausführliche Bewertung |
| 29.07. | LM Studio Server Log                          | **Analysiert:** `~/.lmstudio/server-logs/2026-07/2026-07-29.1.log` – 2 Channel Errors, 3 Minor (GET /v1/version), alle recovered |
| 24.07. | `src/run_benchmarks.py`                       | **Pre-Run Registry-Prüfungen (7 Checks):** capabilities, blueprint, truncation, systemPrompt, reasoning, registry-exists, template-file – schlagen vor dem Modell-Laden fehl. Siehe §2.1a |
| 24.07. | `src/run_benchmarks.py`                       | **Startup-Validierung:** Fehlende capabilities/blueprint → ERROR+skip, fehlendes truncation → WARN+default, leerer systemPrompt → WARN |
| 24.07. | `src/benchmark_config.py`                         | **`_word_boundary_match()`:** `"de"` matcht nicht mehr `"deepseek"`. Boundary-aware Substring-Matching verhindert Fehlmatches. Override-Sortierung nach Länge (spezifischste Keys zuerst) |
| 24.07. | `src/registry_tool.py`                            | **NEW `validate`-Befehl:** 7 Checks (template_missing_file, template_missing_config, override_overlap, missing_reasoning/capabilities/blueprint, registry_no_config, orphan_override, reasoning_arch_mismatch) |
| 24.07. | `src/registry_tool.py`                            | **`cmd_sync()` erweitert:** Ruft jetzt `classify_registry()` → `assemble_prompts()` → `validate_prompts()` am Ende auf. Ein Befehl für alles |
| 24.07. | `src/registry_tool.py`                            | **`_detect_reasoning_from_template()` mit Regex:** `<\s*/?\s*(think|thinking|thought)\s*>` statt Substring. Vermeidet False Positives |
| 24.07. | `src/registry_tool.py`                            | **Interaktive Prompt-Abfrage in `cmd_add`:** Bei fehlender GGUF-Datei wird `[i]nstruct/[t]hinking/[n]one` abgefragt |
| 24.07. | `src/registry_tool.py`                            | **Bugfix `_format_blank_lines()`:** `pathlib.Path.write_text()` → `open()` (OSError [Errno 22] unter Python 3.14/Windows) |
| 24.07. | `src/assemble_blueprint.py`                       | **`_ARCH_REASONING_MAP`:** Statische Arch→Reasoning-Zuordnung (qwen3→thinking, gpt-oss→instruct, …). Priority 2 in `classify_reasoning()` |
| 24.07. | `src/assemble_blueprint.py`                       | **`classify_reasoning()` Priority-Chain:** existing_reasoning > arch map > blacklist > whitelist > instruct. Neue Parameter: `arch`, `existing_reasoning` |
| 24.07. | `src/assemble_blueprint.py`                       | **`REASONING_KEYWORDS` bereinigt:** `gpt-oss` entfernt, `phi-4`→`phi-4-reasoning`, `ministral` entfernt |
| 24.07. | `src/assemble_blueprint.py`                       | **Bugfix Import:** `from fmt_registry import format_blank_lines` → `from registry_tool import _format_blank_lines` (fmt_registry existiert nicht mehr im Root) |
| 24.07. | `src/custom_benchmark.py`                     | **Native API `_retry_native()`:** Retry-Kette bei API-Fehlern: `stop` → `reasoning="off"`. `top_k > 0`-Guard gegen LM-Studio-API-400 |
| 24.07. | `doc-git/HowTo-Install-and-Configure-New-LLM.md` | **Workflow vereinfacht:** `python src/registry_tool.py sync` als einziger Befehl. Alle 3 assemble_blueprint-Schritte entfallen (automatisch in sync) |
| 24.07. | `doc-git/Architektur+Flow_v24.md`             | **Komplett aktualisiert:** Hybrid-Klassifikation §2.6, Pre-Run-Checks §2.1a, Registry-Tool §Registry, Fields-Tabelle, Changelog |
| 21.07. | `src/run_benchmarks.py`                       | **Bugfix lm_eval 0.4.12 CLI:** `--generation_parameters` → `--gen_kwargs` (argument renamed in new lm-eval-harness) |
| 21.07. | `src/run_benchmarks.py`                       | **Reasoning detection via Registry:** `_is_reasoning_model()` now reads `model_registry.yaml:reasoning` field instead of keyword matching. `_load_registry_for_context()` no longer filters by `context_length`. Model identifier strips `@quant` suffix before registry lookup |
| 21.07. | `src/custom_benchmark.py`                     | **Same @quant fix** in `_model_supports_reasoning()` as run_benchmarks.py |
| 21.07. | `src/registry_tool.py`                            | **NEW: `fill-reasoning` command** – reads GGUF `tokenizer.chat_template`, sets `reasoning: thinking|instruct` in registry. Part of `sync` pipeline. `_read_gguf_arch()` now returns `(n_layers, hidden_dim, is_reasoning)` |
| 21.07. | `Architektur+Flow_v24.md`                     | Reasoning detection §2.6, registry_tool fill-reasoning, model_registry.yaml reasoning field, GGUF header reader updated |
| 20.07. | `src/custom_benchmark.py`                     | **Native REST API** (`_generate_answer_native()`): when `enable_thinking=False`, routes to `/api/v1/chat` with `reasoning="off"` — garantiert Thinking-Aus. Fallback nachdem `chat_template_kwargs` vom OpenAI-Endpoint ignoriert wird |
| 20.07. | `src/run_benchmarks.py`                       | **Real-time MATH-500 progress:** `run_lmeval()` switched from `subprocess.run()` to `subprocess.Popen()` — lm_eval stdout wird zeilenweise live ausgegeben (0/30, 5/30, ..., 30/30) statt erst am Ende |
| 20.07. | `src/run_benchmarks.py`                       | **Double coverage reasoning:** `_get_lmeval_params()` sends `reasoning="off"` alongside `chat_template_kwargs.enable_thinking`; `"reasoning"` added to both `gen_kwargs_keys` sets |
| 19.07. | `src/benchmark_config.py`                         | **BLACKLIST** (19 items) replaces `EXCLUDE_KEYWORDS`; `EXCLUDE_KEYWORDS = BLACKLIST` alias. Embedding models, <16K context, OCR/vision/audio, rag/german |
| 19.07. | `model_registry.yaml`                         | 26 blacklisted entries (404 lines) deleted: embedding, OCR, vision, audio, translation, <16K context |
| 19.07. | `src/registry_tool.py`                            | Blacklist skips in `cmd_add`, `cmd_configs`, `cmd_sync_from_configs` |
| 19.07. | `src/assemble_blueprint.py`                       | Blacklist skip in `assemble_prompts()`; imports `BLACKLIST` from `benchmark_config` |
| 19.07. | `src/model_manager.py`                            | `--context-length` flag **removed** from `load_model_via_lms()`. Root cause: `lms load --context-length N` permanently overwrote JSON configs. Context now exclusively from pre-config JSONs |
| 19.07. | `src/run_benchmarks.py`                     | All `context_length=` call sites removed; context-mismatch reload logic simplified away (no longer controllable via CLI) |
| 19.07. | `src/run_benchmarks.py`                     | **Bugfix Thinking lm_eval:** `extra_body` → `chat_template_kwargs` top-level in gen_kwargs. lm_eval nutzt `requests.post()` direkt (nicht OpenAI SDK) – `extra_body` wird als unbekannter HTTP-Key ignoriert. Betrifft MATH-500, ARC, HellaSwag, TruthfulQA |
| 19.07. | `src/custom_benchmark.py`                     | `_use_structured_output(model_key)` helper disables `response_format: json_schema` for reasoning (r1-distill, deepseek, think) and Mamba models; CoderEval regex fallback added; registry blueprint fixes (deepseek-r1-distill → reasoning_coding) |
| 19.07. | `src/custom_benchmark.py`                     | **Bugfix Thinking:** `extra_body` nesting entfernt in `generate_answer()`. `chat_template_kwargs` now at TOP level of HTTP body. Root cause: `extra_body` ist ein OpenAI-SDK-Konzept (wird entpackt), kein gültiger HTTP-JSON-Key — LM Studio ignorierte ihn still. Qwen3.6-27B (thinking=ON per GGUF) lief daher immer im Thinking-Modus (6000+ Tokens/Task) |
| 19.07. | `src/benchmark_config.py`                         | Qwen3.6-Catch-All: `qwen3.6` → `enable_thinking=False` (ersetzt spezifische `qwen3.6-27b`/`qwen3.6-28b-reap`). GGUF-Default ist thinking=ON für alle Qwen3.6-Modelle |
| 19.07. | `src/registry_tool.py`                            | Registry `context_length` fixed for 13 overestimated models (from GGUF headers); missing arch/reasoning/capabilities filled for 11 entries; JSON configs synced (165 updated) |
| 17.07. | `Architektur+Flow_v24.md`                     | p7: fill-arch + sync-from-configs, VRAM formula for useUnifiedKvCache, GGUF header reader (1ms), sync pipeline extended |
| 17.07. | `src/registry_tool.py`                            | NEW: fill-arch (GGUF header reader), sync-from-configs (overwrite from JSON). add reads n_layers/hidden_dim from GGUF. fill-arch in sync pipeline. HF fallback removed. |
| 12.07. | `Architektur+Flow_v25.md`                     | v33: v12→v13, MATH-500 replaces MathQA, MMLU-Pro removed, --no-unload-between, --exclude-benchmarks, documentation updated |
| 12.07. | `src/run_benchmarks.py`                       | v13 from v12: MATH-500 instead of MathQA, MMLU-Pro removed, `--no-unload-between`, `--exclude-benchmarks` |
| 12.07. | `src/custom_benchmark.py`                     | v13 from v12: MODEL_CONFIG updated (--thinking only for Gemma MATH-500/Reasoning) |
| 12.07. | `src/consolidate_results.py`                  | v13 from v12: MATH-500 instead of MathQA, MMLU-Pro removed from weighting |
| 08.07. | `Architektur+Flow_v24.md`                     | v32: --gpu max/-c removed, Pre-Config JSONs, numExperts clarification |
| 07.07. | `Architektur+Flow_v24.md`                     | v31: Variant-unique keys, resume=False, load_key/lms load fix, warning for variant mismatch |
| 07.07. | `run_benchmarks_v12.py`                       | model_info["key"] variant-unique, load_key separated, warning for variant mismatch |
| 07.07. | `custom_benchmark_v12.py`                     | get_available_models() variant-unique keys + variants[] |
| 07.07. | `src/model_manager.py`                            | load_model_via_lms() with --gpu max (CPU offloading fix) |
| 08.07. | `src/model_manager.py`                            | --gpu max and -c removed; context length/GPU control via Pre-Config JSONs |
| 07.07. | `consolidate_results_v12.py`                  | _get_model_info() variant-unique; fallback to base key for old results |
| 07.07. | `src/csv_writer.py`                               | model_key in filenames now variant-unique |
| 05.07. | `Architektur+Flow_v24.md`                     | v30: Structured output, Paired Bootstrap, --seed, --compare, --bootstrap removed |
| 05.07. | `custom_benchmark_v12.py`                     | Structured output: response_format with JSON schema, extract_code() JSON shortcut |
| 05.07. | `run_benchmarks_v12.py`                       | --seed, --no-structured-output passed to subprocess |
| 05.07. | `consolidate_results_v12.py`                  | --compare with 2+ models, --seed, --models, always-CI (no --bootstrap) |
| 05.07. | `src/csv_writer.py`                               | write_quant_comparison() for CSV + MD output |
| 05.07. | `Architektur+Flow_v24.md`                     | v29: DISPLAY_NAMES/WHITELIST removed, Auto-Discovery, bugfixes |
| 05.07. | `src/benchmark_config.py`                         | REMOVED: DISPLAY_NAMES + WHITELIST; NEW: EXCLUDE_KEYWORDS centralized |
| 05.07. | `consolidate_results_v12.py`                  | Auto-discovery from result CSVs; `--models` CLI arg; bugfixes |
| 05.07. | `generate_quant_map.py`                       | Keys dynamically via `lms ls --json` + result CSVs |
| 05.07. | `run_benchmarks_v12.py`                       | v12 from v11: Stale refs fixed, config imports centralized |
| 05.07. | `custom_benchmark_v12.py`                     | v12 from v11: Stale refs fixed, EXCLUDE_KEYWORDS from config |
| 05.07. | `src/model_manager.py`                            | German/English mix cleaned up |
| 04.07. | `Architektur+Flow_v24.md`                     | Thinking mode for all reasoning models, REASONING_PATTERNS, enable_thinking table |
| 18.07. | `Doku-intern/Code-Review-2026-07-18.md`         | **NEW:** Complete Code-Review report covering 6 blocks (architecture/drift/code-quality/performance/test-coverage/security) + 2 critical bug fixes |
| 18.07. | `src/model_manager.py`                            | **Bug 1 Fix:** `unload_all_models()` Race-Condition – polling via `lms ps --json` (canonical LMS state) instead of HTTP-ping with `model:"check"` (which was racy because LMS answered bogus model with HTTP 400, misinterpreted as "model gone") |
| 18.07. | `src/model_manager.py`                            | **Bug 2 Fix:** `_ensure_lmstudio_running()` 3-stage fallback: 1) `lms server start`, 2) `iterdir()` over `.lmstudio/llmster/*/` sorted by version desc, 3) error. Replaces hardcoded `0.0.12-1/llmster.exe` path that broke on LMS updates |
| 18.07. | `src/model_manager.py`                            | **NEW:** `_validate_model_key()` – whitelist regex `[A-Za-z0-9._/\-@:+=#]{1,256}` for defensive input validation (subprocess calls already use list-form, but bad input should fail with clear message) |
| 18.07. | `src/model_manager.py`                            | **NEW:** `safe_json_loads()` helper – uses `object_pairs_hook=OrderedDict` for deterministic parsing of LMS responses |
| 18.07. | `src/model_manager.py`                            | **NEW:** `HEALTH_CHECK_SENTINEL_MODEL = "check"` constant (replaces magic string) |
| 18.07. | `src/benchmark_config.py`                         | **NEW central constants:** `USABLE_VRAM_GB = 15.3`, `USE_UNIFIED_KV_CACHE_THRESHOLD_GB = 14.0`, `LEGACY_MODEL_GB_THRESHOLD_GB = 9.0`, `KV_QUANT_REFERENCE_BYTES = 1.5`. Was scattered across `src/registry_tool.py` and `cmd_configs` |
| 18.07. | `src/benchmark_config.py`                         | **ENHANCED:** `get_quant()` now has 4-step look-up priority: QUANT_MAP exact → suffix → base → **registry fallback (first entry of `quants: [...]` from model_registry.yaml)**. New models with `quants: [...]` in registry are auto-discovered without manual QUANT_MAP updates |
| 18.07. | `src/benchmark_config.py`                         | **REMOVED:** `MMLU_PRO_ENABLED` constant (imported but never read) |
| 18.07. | `src/registry_tool.py`                            | **REFACTORED:** Dynamic `importlib.machinery.SourceFileLoader` → direct `from assemble_blueprint import …` (via `sys.path.insert(0, str(BASE_DIR))`). Enables IDE resolution, `__pycache__` reuse |
| 18.07. | `src/registry_tool.py`                            | **REFACTORED:** `_normalize_ctx()` removed (was duplicate of `assemble_blueprint.normalize_model_name`). All call sites now use the canonical function |
| 18.07. | `src/registry_tool.py`                            | **ENHANCED:** `cmd_configs` now also writes `llm.load.contextLength` (VRAM-aware via `_max_ctx_from_vram()`) and `llm.load.useUnifiedKvCache` (via central thresholds) |
| 18.07. | `src/registry_tool.py`                            | **REFACTORED:** `_infer_num_parallel()` now handles MTP models (`mtp` in key → `np=2` to match Max Draft Tokens) |
| 18.07. | `src/run_benchmarks.py`                       | **REFACTORED:** Redundant `EXCLUDE_KEYWORDS` filtering removed from `resolve_models()` and `select_models_interactive()` – already applied by `get_available_models()`. `EVALPLUS_SENTINEL_MODEL = "local-model"` constant added |
| 18.07. | `src/run_benchmarks.py`                       | **DOCUMENTED:** `THINKING_ENABLED` global is single-threaded-safe in current launcher (sequential model iteration), but needs `threading.Lock` if parallel benchmarking is added |
| 18.07. | `src/assemble_blueprint.py`                       | **NEW:** `read_lms_configs()` 5s TTL cache (was re-walking 158+ JSON files on every call; `cmd_sync()` invokes 4+ times) |
| 18.07. | `src/custom_benchmark.py`                     | **ENHANCED:** `Monitor._sample_loop` sampling interval 200ms → 500ms (60% fewer NVML syscalls) |
| 18.07. | `src/custom_benchmark.py`                     | **REFACTORED:** 4x repeated `try: x.append(float(...)) except (ValueError, TypeError, AttributeError): pass` blocks → single `_safe_float()` helper |
| 18.07. | `src/custom_benchmark.py`                     | **Bug 6.4 Fix:** `_unwrap_solution_for_insert` now correctly synthesizes `def expected_func(*args, **kwargs): <body>` when Granite emits bare statements without `def` (was only documented in docstring, never implemented) |
| 18.07. | `src/consolidate_results.py`                  | **CLEANUP:** `MMLU_PRO_ENABLED` import removed |
| 18.07. | `tests/test_model_manager.py`                 | **+13 NEW tests** for `_validate_model_key()` (shell-meta, path-traversal, control-chars, length cap, integration with `load_model_via_lms`) |
| 18.07. | `tests/test_model_manager.py`                 | **+10 NEW tests** for Bug-1 Fix (`unload_all_models` with `lms ps --json` polling) |
| 18.07. | `tests/test_model_manager.py`                 | **+5 NEW tests** for `TestEnsureLmStudioRunning` (3-stage boot: lms server start / llmster fallback) |
| 18.07. | `tests/test_registry_tool.py`                 | **NEW FILE:** 35 tests for VRAM formula, KV-bytes table, match cascade, `_infer_num_parallel` rules, end-to-end cmd_configs |
| 18.07. | `tests/test_assemble_blueprint.py`            | **NEW FILE:** 43 tests for `normalize_model_name`, `classify_capabilities`, `extract_params`, format helpers, `read_lms_configs` cache |
| 18.07. | `tests/test_run_benchmarks.py`                | **FIXED:** `SAFE_CONTEXT` → `SAFE_CONTEXT_FALLBACK` import (was `ImportError` blocking test collection). 9 obsolete `_get_lmeval_params` if-else-cascade tests marked `pytest.mark.skip` with explanation (replaced by Variante C+ in v13) |
| 18.07. | `tests/test_prio2_terminal.py`               | **FIXED:** `test_no_def_in_solution_creates_synthetic` – corrected test expectation (verifies body in synthetic def, not literal `pass`) |
| 18.07. | `tests/` (all files)                          | **+136 NEW tests** total: 412 → 548 passing, 0 failing (1 pre-existing failure in `test_prio2_terminal` resolved by Bug 6.4 fix) |
| 15.07. | `Architektur+Flow_v24.md`                     | p5: MATH-500 SIGALRM fix, registry_tool.py fill-size/migrate-keys, consolidate bugfixes |
| 15.07. | `src/benchmark_config.py`                         | **Variant C+**: NEW `BENCHMARK_CATEGORY_DEFAULTS`, `MODEL_TEMP_OVERRIDES`, `get_model_config()`. `THINKING_CONFIG` as backward-compat alias. `REASONING_PATTERNS` moved from custom_benchmark to here. |
| 15.07. | `src/custom_benchmark.py`                     | `_get_model_config()` delegates to `benchmark_config.get_model_config()` with benchmark_category. `BENCHMARK_CATEGORY_MAP` and `get_benchmark_category()` new. `REASONING_PATTERNS` removed (to benchmark_config.py). |
| 15.07. | `src/run_benchmarks.py`                       | `_get_lmeval_params()` completely replaced: category-based lookup instead of if-else cascade. 5 obsolete helpers removed (`_is_magistral_model`, `_is_phi4_model`, `_is_ministral_model`, `_is_nemotron_model`, `_is_apriel_model`). |
| 15.07. | `src/assemble_blueprint.py`                       | `select_blueprint()` detects 4 new model families: phi-4-reasoning, ministral, nemotron, apriel. `REASONING_KEYWORDS` extended by `rnj`. |
| 15.07. | `doc-git/blueprint_definitions.yaml`          | 4 new reasoning blueprints: `phi4_reasoning`, `ministral_reasoning`, `nemotron_reasoning`, `apriel_reasoning`. |
| 15.07. | `doc-git/model_registry.yaml`                 | 4 new blueprint assignments for Phi-4-Reasoning-Plus, Ministral, Nemotron, Apriel. |
| 14.07. | `Architektur+Flow_v24.md`                     | p4: registry_tool.py, new CLI args in consolidate, offload/num_parallel in Registry, blank line formatting |
| 14.07. | `src/registry_tool.py`                            | **NEW:** Consolidates sync_model_configs.ps1-embedded-Python + sync_context_length.py + fmt_registry.py |
| 14.07. | `sync_model_configs.ps1`                      | Rewrite: calls registry_tool.py instead of embedded Python; new step 4 (configs) |
| 14.07. | `fmt_registry.py`                             | Rewrite: thin wrapper → registry_tool.py; module functions moved there |
| 14.07. | `sync_context_length.py`                      | Rewrite: thin wrapper → registry_tool.py sync-ctx |
| 14.07. | `src/assemble_blueprint.py`                       | Calls `format_blank_lines()` after `classify_registry()` (automatic blank line normalization) |
| 14.07. | `model_registry.yaml`                         | 46 entries filled with `context_length: 16384`; offload+num_parallel in all entries; blank lines formatted; duplicate key `deepseek-coder-33b-instruct-i1` cleaned |
| 14.07. | `src/consolidate_results.py`                  | New CLI: --merge, --since, --until, --all-runs, --no-installed; Default: installed-only + latest-run |
| 04.07. | `custom_benchmark_v12.py`                     | REASONING_PATTERNS set, `--thinking` activates thinking for AceMath+DeepSeek+Gemma |
| 04.07. | `run_benchmarks_v12.py`                       | `_get_lmeval_params()` thinking for Reasoning+Gemma on MathQA/MMLU-Pro |
| 30.06. | `Architektur+Flow_v24.md`                     | Update: QUANT_MAP, qwen3.6 class, konsolidiert_aktuell.csv, Qwen3/Qwen3.6 results |
| 28.06. | `run_benchmarks_v10.py`                       | Launcher v10 (previously v7): Type hints, all_summary bugfix, API_BASE from model_manager, task-retry, MMLU-Pro helper |
| 28.06. | `custom_benchmark_v10.py`                     | Custom v10 (previously v24): Type hints, task-retry, no PandasEval, no interactive mode |
| 28.06. | `consolidate_results_v10.py`                  | Consolidation v10 (previously v8): Type hints, ModelData dataclass, median/p90 columns, width duplication removed |
| 11.07. | `run_benchmarks_v12.py`                       | **Bugfix: lm_eval parameters via `--gen_kwargs` instead of `--model_args`**; `eos_string` only for GPT-OSS; HellaSwag `min_limit=100` |
| 11.07. | `lm_eval_tasks/mathqa_gen/mathqa_gen.yaml`   | `max_gen_toks: 20→512`; Regex `[ABCDE]→[A-Ea-e]`; paths relative |
| 11.07. | `lm_eval_tasks/hellaswag_gen.yaml`            | `max_gen_toks: 20→100`; Regex `[ABCD]→[A-Da-d]`; `>-→\|` (newlines) |
| 11.07. | `lm_eval_tasks/mathqa_gen/utils.py`           | `process_docs()` regex more robust with comma values |
| 28.06. | `src/model_manager.py`                            | Versioning removed (previously _v2); API_BASE centralized; PIPELINE_TIMEOUTS retained |
| 28.06. | `src/csv_writer.py`                               | Versioning removed (previously _v2); fn_csv extended with median/p90 |
| 28.06. | `src/benchmark_config.py`                         | NEW: Central configuration for CAT_WEIGHTS, OVERALL_WEIGHTS, MMLU_PRO_SUBSETS, TOOL_EVAL_SCENARIO_IDS, DISPLAY_NAMES |
| 05.07. | `src/benchmark_config.py`                         | REMOVED: DISPLAY_NAMES + WHITELIST – replaced by dynamic auto-discovery |
| 05.07. | `consolidate_results_v12.py`                  | WHITELIST loop -> auto-discovery from result CSVs; `_lookup_vram(model_key)` instead of DISPLAY_NAMES reverse lookup; new `--models` CLI arg; `_get_display_name()` from `lms ls --json` |
| 05.07. | `generate_quant_map.py`                       | No import from benchmark_config anymore; keys dynamically via `lms ls --json` + result CSVs |
| 28.06. | `tests/test_scores.py`                        | NEW: 10 tests for compute_category_scores, _percentile, _threshold_filtered |
| 28.06. | `tests/test_csv.py`                           | NEW: 5 tests for read_custom_csv, auto_delimiter |
| 28.06. | `tests/fixtures/test_tasks.csv`               | NEW: Test data for CSV parsing |
| 28.06. | `run_all_dense.py` / `rerun_*.py`             | Wrapper updated to run_benchmarks_v12.py |
| 28.06. | `review_20260628.md`                          | NEW in Doku+Install: Code review with 9 critique points and recommendations |
| 28.06. | `Doku+Install/Alte_Skripte/`                  | 17 historical scripts scrapped (v18-v22, v6-v7, v1-v6) |
| 27.06. | `model_manager.py / csv_writer.py`            | Versioned as _v2; PIPELINE_TIMEOUTS dict |
| 27.06. | `Architektur+Flow_v22.md`                     | v24 architecture: v7/v24/v8/v2, dynamic script resolution |
| 27.06. | `model_manager_v2.py / csv_writer_v2.py`      | Copies of unversioned files |
| 26.06. | `src/model_manager.py`                            | `wait_for_model_ready`/`check_api_available` no longer used by launcher |
| 26.06. | `benchmark_lmstudio_v22.py`                   | v21->v22: System metric fix: per-task peak values instead of MetricsCollector (10s) |
| 25.06. | `consolidate_results_v6.py`                   | Whole percentages, TOP coding threshold, system metrics as % |
| 23.06. | `benchmark_lmstudio_v21.py`                   | MetricsCollector, CPU/GPU/RAM sampling (buggy) |
| 19.06. | `src/model_manager.py`                            | **NEW:** Shared module for model management |
| 19.06. | `run_benchmarks_v3.py`                        | Import from model_manager, _api_model mechanism, id_range fix |
| 17.06. | `run_benchmarks_v1.py`                        | First unified launcher |
| 14.06. | `benchmark_lmstudio_v12.py`                   | First stable version with 10 benchmarks |
