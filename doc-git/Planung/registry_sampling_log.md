# Migration-Log: Registry-Sampling (SSOT)

Protokoll der Änderungen an `doc-git/model_registry.yaml` (Sampling-Felder, Variante A).
Siehe Plan: `doc-git/Planung/registry_sampling.md`.

## 2026-08-13 – Phase 2: Recherchierte Werte + Reader-Umbau (Lesepfade)

**Was:** Die `sampling:`-Blöcke der 17 Modelle mit den recherchierten Werten aus
`MODEL_CATEGORY_SAMPLING` befüllt (vorher: einheitliche Platzhalter 0.6/0.95). Reader
(`get_model_config`/`_sampling_cell` in `src/benchmark_config.py`) liest jetzt
Registry-first (Precedence: Registry-`sampling:` → `MODEL_CATEGORY_SAMPLING` → Defaults).

**Entscheidungen (Nutzer, 13.08.):**
- Registry-Blöcke enthalten die recherchierten temperature/top_p (SSOT), NICHT Platzhalter.
- Reader übernimmt NUR temperature/top_p aus der Registry; top_k/min_p/enable_thinking
  kommen weiterhin aus der LMS-JSON (unverändert).
- `MODEL_CATEGORY_SAMPLING` bleibt als Fallback (30 Modelle ohne Block + fehlende Kategorien).

**Wert-Mapping (17 Modelle, 1 Block entfernt):**
- `intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround@q2_k`: Block ENTFERNT — keine
  recherchierte Zeile in `MODEL_CATEGORY_SAMPLING`; Platzhalter hätten das Nicht-Thinking-
  Verhalten (Kategorie-Defaults) verändert. Fallback (Thinking-Defaults 0.6/0.95) korrekt.
- Alle übrigen 17 Blöcke: recherchierte Werte pro Kategorie übernommen (z.B. gemma-4 1.0/0.95,
  ernie knowledge 0.8/1.0, glm-4.6v 0.8/0.6, qwen3-coder-reap 0.7/0.8). Kategorien ohne
  recherchierten Wert (z.B. ernie coding, kimi-linear agentic) sind NICHT im Block → Fallback.

**Code-Änderungen:**
- `src/benchmark_config.py`: +`_registry_sampling_block()` (match_registry_key gegen
  Registry-Keys), +`_sampling_cell()` (gibt Zelle + Quelle zurück), `get_model_config`
  nutzt Registry-first. Neue `_source`-Variante: "registry-sampling".
- `tests/test_benchmark_config.py`: 2 Tests auf "registry-sampling" umgestellt
  (autoround, gemma-4-thinking), 7 neue Registry-Sampling-Tests ergänzt.

**Verifikation:**
- 148 relevante Tests grün (test_benchmark_config, test_registry_tool, test_model_identity,
  test_csv); volle Suite 790 passed / 3 pre-existing TabbyAPI-Fehler.
- End-to-End-Vergleich: alle 17 Registry-Modelle × Kategorien liefern exakt die recherchierten
  Werte (0 MISMATCH vs. `MODEL_CATEGORY_SAMPLING`).
- `validate`: nur pre-existing Drifts (registry_no_config ×2, config_context_drift ×2,
  missing_quant ×1) — keine neuen Fehler.
- YAML valide: 47 Einträge, 17 mit `sampling:`.

## 2026-08-13 – Phase 1 abgeschlossen (14 Modelle gebündelt)

**Was:** Die restlichen 14 geplanten Modelle mit `sampling:`-Block (Variante A) ergänzt —
per Python-Skript eingefügt (nicht einzeln, da die Einzel-Patch-Strategie zu YAML-Indent-Corruption
führte). Einfügeposition: direkt nach der `arch:`-Zeile des jeweiligen Modell-Blocks.

**Betroffene Modelle (14):**
- mradermacher/qwen3.6-28b-reap-i1@iq3_s
- mradermacher/qwen3.6-28b-reap-i1@q3_k_s
- mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m
- mradermacher/gemma-4-26b-a4b-it-heretic-i1@iq3_m
- lmstudio-community/internlm2-math-plus-20b@q4_k_m
- quietimpostor/nemotron-3-nano-reap-21b-a3b@mxfp4
- intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k
- intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround@q2_k
- jetbrains/mellum2-12b-a2-5b-thinking-moe@mxfp4
- noctrex/lfm2-24b-a2b-moe@mxfp4
- crucible-labs/gemma4-26b-a4b-reap-25@mixed
- qwen/qwen3.5-9b@q6_k
- qwen/qwen3-14b@q6_k
- zai-org/glm-4.6v-flash@q6_k

**Standardwerte (alle Blöcke):** coding/knowledge/agentic/math: temperature 0.6, top_p 0.95,
top_k 40, min_p 0.0, enable_thinking false; thinking: enabled false, temperature 0.6, top_p 0.95.

**Vorfall:** Während der Einzel-Patch-Phase korrupte YAML (Duplikat-`sampling:`-Block in
`mradermacher/qwen3.6-27b-i1@q3_k_s` + Indent-Verluste). **Fix:** `sampling:`-Key-Indent auf
Zeile 412 repariert; danach `yaml.safe_load` wieder valide (47 Einträge, keine ParserError).

**Verifikation:** 141 relevante Tests grün (test_registry_tool, test_benchmark_config,
test_model_identity, test_csv); volle Suite 783 passed / 3 pre-existing TabbyAPI-Fehler;
`validate` nur bekannte pre-existing Drifts (registry_no_config ×2, config_context_drift ×2,
missing_quant ×1 — keine sampling-bezogenen Fehler).

## 2026-08-11 – Phase 0 (Pilot) abgeschlossen (4 Modelle einzeln)

**Was:** Erste 4 Modelle mit `sampling:`-Block (Variante A) ergänzt, jeweils einzeln gepatcht
und nach jedem Patch getestet.

**Betroffene Modelle (4):**
- noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4
- unsloth/gemma-4-12b-it-qat@q4_k_xl
- mradermacher/kimi-linear-reap-35b-a3b-instruct-i1@iq3_xxs
- mradermacher/qwen3.6-27b-i1@q3_k_s

**Nebenschluss:** `MODEL_CATEGORY_SAMPLING` in `src/benchmark_config.py` um neue Zeilen
erweitert (qwen3-6-27b, qwen3-6-28b-reap-i1, qwen3-5-9b, qwen3-14b, gemma4-26b-a4b-reap-25),
damit alle 47 Registry-Modelle über eine Sampling-Zeile verfügen. `field_owner.py`:
`"sampling": FieldRule("registry", "registry", False)` ergänzt. Test-Anpassung:
`test_thinking_without_flag_uses_category_defaults` → `qwen/qwen2.5-7b-instruct`.

**Verifikation:** 65 Tests grün (test_benchmark_config, test_model_identity, test_csv).

## 2026-08-13 – C4: Validate-Rest-Datenpflege (5 pre-existing Drifts bereinigt)

**Was:** Die 5 beim `validate` gemeldeten Altlasten bereinigt (Registry ist SSOT, Änderungen
wirken auf künftige Benchmark-Läufe).

**Änderungen an `doc-git/model_registry.yaml`:**
- `unsloth/qwen3-30b-a3b-instruct-2507` → `unsloth/qwen3-30b-a3b-instruct-2507@q3_k_s`
  (missing_quant; Quant laut LMS GUI/GGUF), `context_length` 43690 → 49152 (Config-Wert).
- `intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k` → `@q2_k_s`
  (laut LMS GUI), `quants` Q2_K → Q2_K_S, `context_length` 32768 → 131072 (Config-Wert).
- `jetbrains/mellum2-12b-a2-5b-instruct@q4_k_m` → `jetbrains/mellum2-12b-a2.5b-instruct@q4_k_m`
  (regkey laut LMS GUI „a2.5b" = 2,5 Mrd. aktive Parameter; registry_no_config).
- `mradermacher/qwen3-coder-reap-25b-a3b@q3_k_m` (ohne `-i1`) ENTFERNT — Phantom-Eintrag:
  das echte Modell ist die `-i1`-Variante (12 GB), die bereits einen eigenen Key mit
  `sampling:`-Block hat (`mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m`). Die imatrix-Datei
  (`qwen3-coder-reap-25b-a3b-i1@?`, 98 MB) ist eine Feintuning-Gewichtung, kein Modell —
  bekommt KEINEN Registry-Eintrag.

**Code-Änderungen (`src/model_identity.py`):**
- `_QUANT_DIR_SUFFIXES` um 3-teilige Quant-Suffixe erweitert (`-q2-k-s/-m/-l` … `-q6-k-*`,
  iQ-Quants). Vorher strippte `normalize_for_config` nur 2-teilige (`-q4-k`), sodass der
  JetBrains-Ordner `Mellum2-12B-A2.5B-Instruct-GGUF-Q4_K_M` (→ `-q4-k-m`) nicht broad-matchte.
- Folge: `match_registry_key("GLM-4.7-Flash-REAP-23B-A3B-Q4_K_S")` matcht jetzt eindeutig
  den REAP-Key (vorher mehrdeutig → None). Test angepasst + `test_dir_three_part_quant_suffix_stripped`
  ergänzt.

**Verifikation:**
- `validate`: **0 Probleme** (vorher 5).
- Volle Suite 792 passed / 3 pre-existing TabbyAPI-Fehler; `test_model_identity` + `test_benchmark_config`
  grün. `model_identity.py` lint-frei (I001 in `test_model_identity.py` pre-existing).

## Offene Nacharbeiten

- [x] Lesepfade: `get_model_config`/`_sampling_cell` auf Registry-`sampling:`-Felder umgestellt (Precedence: Registry → Fallback).
- [x] `MODEL_CATEGORY_SAMPLING` bleibt als Fallback (Entscheidung 13.08.).
- [x] Neue Tests für Registry-Lookup + Fallback (7 Tests, 13.08.).
- [x] CHANGELOG + Doku (`thinking-config_en.md`, `Temperature Recommondations_en.md`) aktualisiert (Schritt 7 des Plans, 13.08.).
- [x] Validate-Rest-Datenpflege (C4): 5 Drifts bereinigt, `validate` = 0 Probleme.
- [x] Ruff-Check (C10, 13.08.): 7 „neue“ Ruff-Fehler = 7 neue Registry-Sampling-Testmethoden (alle ANN201), konsistent mit 29 pre-existing Fehlern derselben Datei; `src/benchmark_config.py` ruff-clean. Als konsistent mit Style dokumentiert.
- [x] Abschluss-Check (C11, 13.08.): `validate` = 0 Probleme; 150 relevante Tests grün (test_benchmark_config, test_model_identity, test_registry_tool, test_csv); volle Suite 792 passed / 3 pre-existing TabbyAPI-Fehler. Git-Status siehe unten.

## Git-Status (13.08., vor evtl. Commit)

**Uncommitted (Migration + C4):**
- `M src/benchmark_config.py` (Registry-Sampling-Reader), `M src/model_identity.py` (`_QUANT_DIR_SUFFIXES` 3-teilig), `M tests/test_benchmark_config.py` (7 neue Tests), `M tests/test_model_identity.py` (2 neue/angepasste Tests), `M doc-git/model_registry.yaml` (sampling-Blöcke + C4-Fixes), `M doc-git/Planung.md`, `M CHANGELOG.md`, `M doc-git/thinking-config_en.md`, `M doc-git/Temperature Recommondations_en.md`, `?? doc-git/Planung/` (Plan + Log + ToDos).
- **Pre-existing (nicht Teil dieser Arbeit):** `M src/consolidate_results.py`, `M src/field_owner.py`, `D doc-git/Review-Artifacts/quarantine_registry_20260811_*.yaml` (9 Stück), `?? doc-git/Review-Artifacts/quarantine_registry_2026081[23]_*.yaml` (neu), `D doc-git/Developer-Docs/Compaction-Workflow.md`, `D doc-git/Model Specific Hints/GPT-OSS-20b_Harmony-Template-Injection_en.md` + `?? .../GPT-OSS-20b_Harmony-Chat-Format, Jinja-Template-Injection_en.md` (Umbenennung, offene C5-Entscheidung).
- HEAD: `41cb059e` (MTP-Drafter-Erkennung + MTP aus Registry entfernt).

---

## Pass-2-Nachlauf (C1) — 13.08. abends

**Registry-Einträge angelegt (4 neue, Recherche aus LMS-Configs + GGUF-Header + HF):**
- `mradermacher/f2llm-v2-4b@q6_k` (Q6_K, ctx 40960, k q8_0/v q5_1, ukv true, 3306262848 B, 36/2560, reasoning instruct, blueprint default_chat) — **Hinweis: Embedding-Modell** (HF-Tags feature-extraction/sentence-transformers, Config-SystemPrompt „general-purpose, multilingual embedding model"), kein Text-Generator.
- `mradermacher/f2llm-v2-1.7b@q8_0` (Q8_0, ctx 40960, k q8_0/v q8_0, ukv true, 1834428160 B, 28/2048, reasoning instruct, blueprint default_chat) — dito Embedding-Hinweis.
- `TheBloke/em_german_13b_v01@q6_k` (Q6_K, ctx 4096, k q8_0/v iq4_nl, ukv true, 10679140288 B, 40/5120, pub_url jphme/em_german_13b_v01).
- `TheBloke/em_german_leo_mistral@q4_k_m` (Q4_K_M, ctx 32768, k q8_0/v q5_1, ukv true, 4368438912 B, 32/4096, pub_url jphme/em_german_leo_mistral).
- `validate` nach Einträgen: **0 Probleme**.

**F2LLM-Entscheidung (Nutzer 13.08.):** F2LLM-v2-4B/1.7B sind reine Embedding-Modelle (kein Text-Generator) → aus der Pass-2-Spec entfernt (Registry-Einträge bleiben für Inventar). **em_german ×2 (Nutzer):** ebenfalls raus (Embedding/RAG-Modelle, kein Text-Generator) → Pass 2 läuft mit **4 Modellen**: Glm 4.6v, Gemma4-REAP-25, Phi-4, RNJ-1.

**Code-Fixes (nötig, damit die Spec-Modelle aufgelöst werden):**
- `src/model_manager.py`: `registry_only`-Filter matchte `model_identifier` (LMS modelKey, ohne Quant) gegen normalisierte Registry-Keys mit `@quant` → jetzt Basis-Key-Matching (`normalize_model_name(...).split("@")[0]`), deckt auch Mischquants ab (Registry `@mixed` vs. LMS `Q3_K` bei Gemma4-REAP-25).
- `src/benchmark_config.py`: `em_german` aus BLACKLIST entfernt (blockierte die 2 Spec-Modelle).
- `src/run_benchmarks.py`: `_load_registry_for_context()` registriert Basis-Varianten (`norm.setdefault(normalized_key.split("@")[0], key)`); `_resolve_num_parallel()` + `_get_safe_context()` nutzen `matched_key = rnorm.get(normalized_key) or rnorm.get(base_key)` (Context-Lookup schlug ohne Quant fehl).

**np-Policy-Refactor (Nutzer 13.08., „np kann aus der Registry raus"):**
- **`num_parallel` ist seit 13.08. KEIN Registry-Feld mehr.** Feste Regel: SS≥10 → np=4, sonst np=1 (hardcoded in `_resolve_num_parallel()`).
- CLI `--num-parallel` entfernt (Launcher + custom_benchmark.py Subprozess; beide leiten np aus sample_size ab).
- `registry_tool.py`: `fix-np` deprecated (Stub, informiert nur), `_compute_np_ukv()` → `_compute_ukv()` (nur UKV/ctx), `_NP_POLICY=4` für ctx-Formel, `num_parallel`-Lesen in fill-ctx/fix-ctx/add/suggest entfernt.
- `model_registry.yaml`: 49 `num_parallel`-Zeilen entfernt; `field_owner.py`, `type_defs.py` (RegistryEntry) bereinigt; Tests angepasst (107 Tests grün).
- UKV hängt weiterhin von Speicher/Kontextlänge/KV-Quant ab — aber nicht mehr np.

**Lauf gestartet 13.08. 21:01** (PID 19776, läuft): `run.qwen-re-run-pass2.yaml` (4 Modelle, SS=10, np=4, seed 2026, thinking false), Log `Doku-intern\Terminalausgabe Benchmark-Qwen-Pass2_20260813_210111.log`. MBPP+-`make_model()`-Fehler = pre-existing (auch in Pass-1-Log).