### COMPACTIONS.md für Projekt "C:\Users\pskra\Python-Projekte\Benchmarks" ###

Compaction-Blöcke werden hier fortlaufend hinten angehängt (Anlass-bezogen oder per Kommando). CHANGELOG = was, Compaction = warum/was nächste.

=============== Compaction 14.08.2026 / 11:30 ================
## Objective
- (Current) Grundsätzliche Lösung verankern: modellspezifische Jinja-Chat-Templates, Systemprompts und Stop-Strings müssen dauerhaft in der **Blueprint-Datei als einziger Quelle** (`blueprint_definitions.yaml`) liegen und von `assemble_blueprint.py` + `benchmark_config.py` gelesen werden, damit sie `registry_tool.py`/`pipeline`-Revisionen nicht verlieren.
- (Completed) Verifikationslauf 4 komplett erfolgreich; alle 6 Gemma-4-Modelle auf `gemma_reasoning` + korrektes Template umgestellt und assembliert; AGENTS.md erweitert.

## Important Details
- **Entscheidung (User, question-Tool):** Blueprint-Datei als einzige Quelle — `template:` + `stop_strings:` verpflichtend pro Blueprint; Registry-`template:`-Feld deaktivieren/ignorieren. Grund: Viele Familien (GLM, phi, Granite, GPT-OSS, Magistral, Qwen3.6) brauchen spezielle Templates/Prompts/Stop-Strings; Info ging bisher bei `model_registry.py`-Überarbeitungen verloren.
- **Gemma-4-Umstellung:** Alle 6 Einträge `blueprint: gemma_reasoning` (12B/19B/26B je eigenes Template aus `doc-git\Jinja-Chat-Templates\`), inkl. REAP-25 (vorher fälschlich `reasoning_assistant`, weil `select_blueprint` nur `"gemma-4"` mit Bindestrich erkennt, REAP-Key `gemma4-26b-a4b-reap-25` ohne). `assemble` geschrieben, `validate` 68/68 OK.
- **Ist-Zustand (vor Umbau):** Kein Blueprint hatte `template:`; nur 9/48 Registry-Modelle mit `template:`; `benchmark_config.py` baut nur Sampling-Parameter; Stop-Strings hartkodiert in `custom_benchmark.py` (STOP_TOKENS_CODING/DEFAULT); Template-Konsumenten: `assemble_blueprint.py` Z.950, `registry_tool.py` (sync-templates Z.1949, validate Z.2232+), `run_benchmarks.py` Z.1946.
- **Umbau bereits umgesetzt:** `blueprint_definitions.yaml` um `template:`/`template_map:`/`stop_strings:`/`reasoning_parsing:` pro Blueprint erweitert (gemma_map 12b/19b/26b, gptoss→gpt-oss-20b_harmony.jinja, phi4→phi-4_template_unsloth.jinja, granite→granite-4.1-30b/-4.0-h-tiny, magistral/ministral→[THINK]/[ANSWER], gemma parsing enabled:false).
- **Probelauf:** `run.gemma4-probelauf.yaml` (unsloth/gemma-4-26b-a4b-it@iq3_s) schlug fehl: Lauf-Key ≠ Registry-Key, `[ERROR] No model found`. Keys aus `lms ls --json` `modelKey`; korrektes Format noch zu klären.

## Work State
### Completed
- Verifikationslauf 4 (09:35): DS1000 0.1, CoderEval 0.7, HumanEval+ 0.6, MBPP+ 0.8, Agentic 0.75; `_eval_results.json` geschrieben. Commits `8ed30dfb`, `6253a014`, `38cc0e0`.
- Planung C12 DONE + Item 20 verifiziert (GLM-4.6V in API-Modellliste nach LMS-Restart).
- AGENTS.md: Abschnitte „Wichtige Pfade" + „LM Studio Doku / Links".
- Gemma-4-Registry + assemble + validate + `run.gemma4-probelauf.yaml` erstellt.
- blueprint_definitions.yaml um Template/Stop-Strings/Parsing erweitert (Code-Anpassung läuft).

### Active
- assemble_blueprint.py auf Blueprint-Quelle umstellen (resolve_template_name, assemble_prompts, classify_registry).
- registry_tool.py (sync-templates/validate), run_benchmarks.py Z.1946, Stop-Strings-Durchreichung.

### Blocked
- Probelauf-Lauf-Key-Auflösung (unsloth-26B) ungeklärt.

## Next Move
1. assemble_blueprint.py: `resolve_template_name()` implementieren, `assemble_prompts` + `classify_registry` auf Blueprint umstellen.
2. registry_tool.py sync-templates/validate + run_benchmarks.py Z.1946 auf Blueprint-Quelle umbauen.
3. Stop-Strings/Parsing aus Blueprint in `get_model_config` durchreichen.
4. Registry-`template:`-Felder deaktivieren/ignorieren.
5. Tests ergänzen + ruff + pytest; Probelauf-Key klären, Lauf starten.
6. Gemma-4-Änderungen + AGENTS.md committen (fremde Diffs LM-Studio-API-References.md/.ods nicht committen).

## Relevant Files
- `doc-git\blueprint_definitions.yaml`: erweitert (Template/Stop/Parsing pro Blueprint)
- `doc-git\model_registry.yaml`: 6 Gemma-4-Einträge → gemma_reasoning
- `src\assemble_blueprint.py`: Template-Leser Z.950/356, classify Z.578, select_blueprint Z.298 („gemma-4"-Hyphen-Falle)
- `src\registry_tool.py`: sync-templates Z.1949, validate Z.2232+, TEMPLATE_DIR Z.1934
- `src\run_benchmarks.py`: Template-Check Z.1946, resolve_models Z.610+
- `src\benchmark_config.py`: get_model_config Z.762 (nur Sampling; braucht Stop/Parsing)
- `src\custom_benchmark.py`: STOP_TOKENS_CODING/DEFAULT Z.236-237, stop-Nutzung Z.925/1681
- `run.gemma4-probelauf.yaml`: NEU (Key ungelöst)
- `AGENTS.md`: neue Abschnitte Pfade/Links


=============== Compaction 14.08.2026 / 14:30 (Uhrzeit kann nicht stimmen: wo ich das lese, sind es erst 13:55 ) ================
## Objective
- (Completed) Grundsätzliche Lösung umgesetzt: Blueprint-Datei als EINZIGE Quelle für modellspezifische Templates, Stop-Strings und Reasoning-Parsing. Code-Leser von Registry-`template:` auf Blueprint umgestellt, 9 Registry-Felder entfernt.

## Important Details
- **Architektur-Entscheidung (Refactor abgeschlossen):** blueprint_definitions.yaml ist SSOT für `template:`/`template_map:`/`stop_strings:`/`reasoning_parsing:`. Registry trägt nur noch den Blueprint-Namen. 9 veraltete Registry-`template:`-Felder entfernt (per ruamel, YAML-Erhaltung).
- **Neue Funktionen:** `assemble_blueprint.resolve_template_name(bp_def, model_name)` (template_map-Substring-Match, Punkte↔Bindestriche robust für granite-4.1→granite-4-1), `blueprint_features()` (liefert template/stop_strings/reasoning_parsing), `load_blueprint_defs()` (cached); `registry_tool._registry_template_name()` + `_load_blueprints()`; `benchmark_config._blueprint_features()` (lazy import, kein Zyklus).
- **Verhaltensänderungen:** (1) GPT-OSS bekommt jetzt `until=["<|return|>"]` aus Blueprint (Harmony-EOS; Template-Kommentar: „<|return|> beendet Generation, <|end|> nicht") statt `eos_string=<|endoftext|>`; Tests `test_gptoss_*` angepasst. (2) `select_blueprint` erkennt jetzt auch `gemma4` ohne Bindestrich (REAP-Key-Falle gefixt). (3) Gemma/GPT-OSS/Granite-Configs bekommen promptTemplate aus Blueprint-Map (verifiziert: unsloth-12B-Config = exakt gemma4_12b_template_minijinja.jinja, 2685 Zeichen).
- **Bewusst NICHT geändert:** Granite-8b hat kein Template (Datei existiert nicht, vorher auch keins). google/gemma-4-12b-q4_0-Config hat leeres promptTemplate — vorbestehendes Publisher-Zuordnungsproblem (kein Registry-Key unter google/), nicht Teil dieses Umbaus.
- **Stop-Strings Plain-Modelle:** default_chat/coding_agent/reasoning_* haben KEINE stop_strings (bewusst — sonst würde lm-eval `until` für alle Modelle setzen, massive Verhaltensänderung). Nur modellspezifische Blueprints (gptoss/magistral/ministral/nemotron/apriel/phi4) haben stop_strings.

## Work State
### Completed
- blueprint_definitions.yaml erweitert (template_map gemma 12b/19b/26b + granite, template gptoss/phi4, stop_strings, reasoning_parsing)
- assemble_blueprint.py: resolve_template_name/blueprint_features/load_blueprint_defs, classify_registry/assemble_prompts aus Blueprint, select_blueprint gemma4-Fix
- registry_tool.py: sync-templates + validate aus Blueprint (_registry_template_name), Import erweitert
- run_benchmarks.py: Template-Check Z.1946 aus Blueprint + eos_string-Harmony-Fix
- benchmark_config.py: get_model_config liefert stop/reasoning_parsing aus Blueprint
- Registry: 9 template:-Felder entfernt; validate 68/68; assemble 48/0 Fehler
- Tests: +13 neue; 817 passed, nur 3 vorbestehende model_manager-Umgebungsfehler (Baseline-verifiziert)

### Blocked
- Probelauf-Key-Auflösung (unsloth-26B) weiterhin ungeklärt — run.gemma4-probelauf.yaml wartet auf korrekten Lauf-Key.

## Next Move
1. Probelauf-Key klären: `lms ls --json` ausgeben, korrekten Key für unsloth-26B in run-Spec einsetzen, Lauf starten (SS=10, DS1000/HumanEval+/MATH-500/Agentic).
2. Committen: Gemma-4-Registry + AGENTS.md + Blueprint-Refactor + Tests (fremde Diffs LM-Studio-API-References.md/.ods NICHT committen).
3. Grundsätzlich: weitere Familien-Hints (GLM parsing enabled:true, Magistral, Qwen3.6) in Blueprint-Definitionen übernehmen wo sinnvoll.
4. CHANGELOG-Eintrag zum Refactor schreiben.

## Relevant Files
- `doc-git\blueprint_definitions.yaml`: SSOT — template/template_map/stop_strings/reasoning_parsing pro Blueprint
- `doc-git\model_registry.yaml`: 9 template:-Felder entfernt, Gemma-4-Einträge gemma_reasoning
- `src\assemble_blueprint.py`: resolve_template_name/blueprint_features/load_blueprint_defs, classify_registry, select_blueprint
- `src\registry_tool.py`: _registry_template_name/_load_blueprints, sync-templates, validate
- `src\benchmark_config.py`: _blueprint_features, get_model_config (stop/reasoning_parsing)
- `src\run_benchmarks.py`: Template-Check aus Blueprint, eos_string=Harmony-Fix
- `tests\test_assemble_blueprint.py`, `tests\test_registry_tool.py`, `tests\test_run_benchmarks.py`: +13 neue Tests
- `Doku-intern\compaction\compactions.md`: Compaction-Datei (hinten anhängen)


============= Compcation 14.08.2026 / 13:55 ==================
## Objective
- Blueprint-Datei (`blueprint_definitions.yaml`) als **einzige Quelle** für modellspezifische Templates, Stop-Strings und Reasoning-Parsing — Refactor ist vollständig umgesetzt und verifiziert.
- Neuer Auftrag des Users: **Probelauf mit ALLEN Gemma-4, GLM, phi, GPT-OSS und Granite Modellen, für die Jinja-Chat-Templates entwickelt wurden** — jeweils `sample_size: 10` und je eine Benchmark aus jeder Pipeline (bisherige Spec: DS1000, HumanEval+, MATH-500, Agentic).

## Important Details
- **Blueprint-SSOT-Refactor (14.08.) abgeschlossen:** `blueprint_definitions.yaml` trägt jetzt `template:`/`template_map:`/`stop_strings:`/`reasoning_parsing:`; Registry trägt nur noch den Blueprint-Namen. 9 veraltete Registry-`template:`-Felder wurden per ruamel entfernt (YAML-Erhaltung). `validate` 68/68, `assemble` 48/0 Fehler.
- **Verhaltensänderung GPT-OSS:** `stop_strings: ["<|return|>"]` (Harmony-EOS, Template-Kommentar bestätigt: „`<|return|>` beendet Generation, `<|end|>` nicht") — ersetzt alten `eos_string=<|endoftext|>`-Fallback; `run_benchmarks._build_lmeval_cmd` ebenfalls auf `<|return|>` angepasst; Tests `test_gptoss_*` aktualisiert.
- **`select_blueprint`-Fix:** erkennt jetzt auch `gemma4` ohne Bindestrich (REAP-Key-Falle, z.B. `gemma4-26b-a4b-reap-25`).
- **`resolve_template_name` robust:** Punkte↔Bindestriche austauschbar (nötig für `granite-4.1-30b`-Muster gegen Registry-Key `granite-4-1-30b`).
- **Modell-Set für den Probelauf (Registry-Keys):** mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m, mradermacher/gemma-4-26b-a4b-it-i1@iq4_xs, unsloth/gemma-4-26b-a4b-it@iq3_s, unsloth/gemma-4-12b-it-qat@q4_k_xl, mradermacher/gemma-4-26b-a4b-it-heretic-i1@iq3_m, crucible-labs/gemma4-26b-a4b-reap-25@mixed, openai/gpt-oss-20b@mxfp4, ibm-granite/granite-4-0-h-tiny@q8_0, ibm-granite/granite-4-1-30b@q3_k_s, unsloth/phi-4@q5_k_m, unsloth/glm-4-7-flash@q3_k_s, zai-org/glm-4.6v-flash@q6_k, ibm-granite/granite-4-1-8b@q6_k.
- **Templates vorhanden** in `doc-git\Jinja-Chat-Templates\`: gemma4_12b/19b/26b minijinja, gpt-oss-20b_harmony.jinja (+gpt-oss-20b-template_unsloth.jinja), granite-4.0-h-tiny/4.1-30b, phi-4_template_unsloth.jinja, google_gemma-4-12B/26B chat_templates. **KEIN GLM-Template existiert** — User hat GLM explizit genannt (GLM braucht laut Hints stattdessen `reasoning.parsing: enabled:true` mit ` thinking`/` response`); Frage: GLM trotzdem in den Lauf?
- **Granite-8b hat kein Template** (Datei existiert nicht; BP-Map nur granite-4.0 + granite-4.1-30b). google/gemma-4-12b-q4_0-Config hat leeres promptTemplate (vorbestehendes Publisher-Zuordnungsproblem, kein Registry-Key unter `google/`).
- **Stop-Strings nur für modellspezifische Blueprints** (gptoss/magistral/ministral/nemotron/apriel/phi4) — default_chat/coding_agent/reasoning_* bewusst ohne, sonst würde lm-eval `until` für alle Modelle setzen.
- **Lauf-Keys:** Registry-Key ≠ Lauf-Key; Keys kommen aus `lms ls --json` Feld `modelKey` (z.B. `gemma-4-26b-a4b-it-qat-nvfp4`, `unsloth/gpt-oss-20b`). Früheres Blocking-Problem: Registry-Key `unsloth/gemma-4-26b-a4b-it@iq3_s` wurde von `run_benchmarks` nicht aufgelöst.
- **Compaction-Anweisung (User):** Compactions regelmäßig/Anlass-bezogen in `C:\Users\pskra\Python-Projekte\Benchmarks\Doku-intern\compaction\compactions.md` schreiben, **hinten anhängen** — Datei angelegt (2 Blöcke: 14.08. 11:30 + 14:30). PowerShell-Here-Strings mit Backticks/`<|…|>` problematisch → Write/Edit-Tool nutzen.
- **Commit-Politik:** Fremde Diffs (`doc-git\Developer-Docs\LM-Studio-API-References.md`, `Zusammenfassung_Benchmarks_kombiniert.ods`) nicht committen. Gemma-4-Registry + AGENTS.md + Blueprint-Refactor + Tests noch nicht committet.
- **Vorbestehend:** 3 `test_model_manager.py`-Fehler (HTTP/Umgebung, Baseline-stash-verifiziert, nicht vom Refactor verursacht). Tests gesamt: 817 passed.
- Verifikationslauf 4 war erfolgreich (Commits `8ed30dfb`, `6253a014`, `38cc0e0`); AGENTS.md enthält neue Abschnitte „Wichtige Pfade" + „LM Studio Doku / Links".

## Work State
### Completed
- Blueprint-SSOT-Refactor komplett: `blueprint_definitions.yaml` erweitert; `src/assemble_blueprint.py` (`resolve_template_name`, `blueprint_features`, `load_blueprint_defs`, `classify_registry`/`assemble_prompts` aus Blueprint, `select_blueprint` gemma4-Fix); `src/registry_tool.py` (`_registry_template_name`, `_load_blueprints`, sync-templates + validate aus Blueprint); `src/run_benchmarks.py` (Template-Check Z.1946 aus Blueprint, eos_string-Harmony-Fix); `src/benchmark_config.py` (`_blueprint_features`, `get_model_config` liefert `stop`/`reasoning_parsing`).
- Registry: 9 `template:`-Felder entfernt; `validate` 68/68; `assemble` 48 assembled/2 skipped/0 not found.
- Tests: +13 neue (TestResolveTemplateName 8, TestBlueprintFeatures 5, TestRegistryTemplateName 4, gptoss 3 angepasst); 817 passed, 3 vorbestehende Fehler; ruff sauber (src).
- Gemma-4-Configs verifiziert: unsloth-12B-Config = exakt `gemma4_12b_template_minijinja.jinja` (2685 Zeichen); Granite-30b/-h-tiny-Configs haben Templates.
- Compaction-Datei `Doku-intern\compaction\compactions.md` angelegt + 2. Block angehängt.
- Todo-Liste komplett abgearbeitet (Alle 7 Punkte completed).

### Active
- Probelauf-Aufbau für alle Familien-Modelle: `lms ls --json` ausgeführt, Ausgabe zeigt erste Modelle (`gemma-4-26b-a4b-it-qat-nvfp4`, `unsloth/gpt-oss-20b`, `qwen3-coder-30b-a3b-instruct-q2ks-mixed-autoround`, `qwen3.6-27b-nvfp4`) — vollständige Modellliste noch nicht ausgewertet, Lauf-Keys für die 13 relevanten Registry-Modelle fehlen noch.

### Blocked
- **Lauf-Keys nicht vollständig ermittelt:** `lms ls --json`-Ausgabe war abgeschnitten; Zuordnung Registry-Key → `modelKey` für gemma-12b/19b/26b/REAP/Heretic, granite-h-tiny/30b/8b, phi-4, glm-4-7-flash/4.6v-flash ausstehend.
- **GLM-Frage offen:** kein Jinja-Template für GLM entwickelt — soll GLM in den Probelauf (vermutlich mit Standard-Template + `reasoning.parsing`)? Unklart ohne Rücksprache.

## Next Move
1. `lms ls --json` vollständig ausgeben und `modelKey` je relevantem Modell notieren (gemma-4-12b/19b/26b/REAP/Heretic, gpt-oss-20b, granite-4.0-h-tiny/4.1-30b, phi-4, glm-Frage); ggf. `model_manager.get_available_models` (Z. 397+) für Key-Format prüfen.
2. `run.gemma4-probelauf.yaml` auf alle Modelle mit korrekten Lauf-Keys erweitern (SS=10, benchmarks DS1000/HumanEval+/MATH-500/Agentic, seed 2026, Agentic random, thinking false) — oder neue Spec-Datei anlegen.
3. Bei GLM-Unsicherheit kurz beim User nachfragen, ob GLM (ohne eigenes Jinja-Template, mit `reasoning.parsing`) in den Lauf soll.
4. Lauf starten, Ergebnisse je Pipeline prüfen; anschließend Gemma-4-Registry + AGENTS.md + Refactor + Tests + Compaction/CHANGELOG committen (fremde Diffs auslassen).

## Relevant Files
- `run.gemma4-probelauf.yaml`: aktuelle Spec (nur unsloth/gemma-4-26b-a4b-it@iq3_s) zum Erweitern
- `doc-git\blueprint_definitions.yaml`: SSOT — template/template_map/stop_strings/reasoning_parsing pro Blueprint
- `doc-git\model_registry.yaml`: 9 template:-Felder entfernt, 6 Gemma-4-Einträge `gemma_reasoning`, 13 Modelle der Ziel-Familien
- `doc-git\Jinja-Chat-Templates\`: verfügbare Templates (kein GLM)
- `doc-git\Model Specific Hints\`: GLM (parsing enabled:true), GPT-OSS Harmony, Magistral, Granite
- `src\assemble_blueprint.py`, `src\registry_tool.py`, `src\benchmark_config.py`, `src\run_benchmarks.py`: Refactor-Stand (geänderte Leser-Quellen)
- `src\model_manager.py` (Z. 397+), `src\type_defs.py` (`AvailableModelInfo`): Key-Auflösung `lms ls --json`/`modelKey`
- `tests\test_assemble_blueprint.py`, `tests\test_registry_tool.py`, `tests\test_run_benchmarks.py`: +13 neue Tests
- `Doku-intern\compaction\compactions.md`: Compaction-Zieldatei (hinten anhängen), 2 Blöcke vorhanden
- `AGENTS.md`: Abschnitte „Wichtige Pfade" + „LM Studio Doku / Links" (uncommittet)


=============== Compaction 15.08.2026 / 20:00 ================
## Objective
- **Probelauf aller 13 Registry-Modelle** (Gemma-4, GPT-OSS, Granite, phi, GLM) als Smoke-Test der modellspezifischen Konfiguration 
    (Systemprompt + Jinja-Template + reasoning.parsing), SS=10, je DS1000/HumanEval+/MATH-500/Agentic.
- Lauf ist **abgebrochen** (Prozess gekillt bei MATH-500 5/10); Ergebnisauswertung + Compaction standen an.

## Important Details
- **Lauf-Keys (13, aus `lms ls --json`/`get_available_models`):** `gemma-4-19b-a4b-it-reap-i1@q4_k_m`, `gemma-4-26b-a4b-it-i1@iq4_xs`, `gemma-4-26b-a4b-it@iq3_s`, 
    `gemma-4-12b-it-qat@q4_k_xl`, `gemma-4-26b-a4b-it-heretic-i1@iq3_m`, `gemma4-26b-a4b-reap-25@Q3_K`, `openai/gpt-oss-20b@mxfp4`, `granite-4.1-8b@Q6_K`, `granite-4.1-30b@Q3_K_S`, 
    `granite-4.0-h-tiny@Q8_0`, `unsloth/phi-4@Q5_K_M`, `glm-4.7-flash@Q3_K_S`, `zai-org/glm-4.6v-flash@q6_k`. Run-Spec: `run.probelauf-familien.yaml`.
- **User-Entscheidungen:** GLM gehört in den Lauf (Steuerung über `reasoning.parsing.enabled:true` laut Hints-Datei, kein eigenes Jinja-Template); 
    alle 13 Registry-Modelle testen (nicht nur 10 mit Templates); GLM-Configs auf `enabled:true`; `registry_tool.glm_patch_config` dauerhaft auf `enabled:true` („GLM sind Reasoning-Modelle"); 
    Logs gehören nach `C:\...\Benchmarks\logs\`, nicht `Doku-intern\logs`.
- **`glm_patch_config`-Fix (src\registry_tool.py):** setzt jetzt `reasoning.parsing.enabled:true` (vorher false), Docstring + Pipeline-Ausgabe „[5a] GLM-Configs verankern (reasoning parsing enabled, kein JSON-Zwang)". 
    `pipeline full` ruft das auf → jetzt sicher. 5 neue Tests (`TestGlmPatchConfig`) in `tests\test_registry_tool.py`.
- **Bugfix Template-Skip (src\run_benchmarks.py `_check_registry_for_model`):** `return None` stand auf falscher Einrückungsebene 
    → JEDES Modell mit Template wurde übersprungen (Lauf 14.08. nur 4/13 Modelle). 
    Fix: `return None` nur bei fehlender Template-Datei. 3 neue Tests (`TestCheckRegistryForModel`).
- **GLM-Configs gepatcht** (Backups `.bak-parsing`): `zai-org\glm-4.6v-flash.json`, `unsloth\GLM-4.7-Flash-GGUF\GLM-4.7-Flash-Q3_K_S.gguf.json` → `enabled:true` verifiziert.
- **Aktueller Lauf (15.08. 19:33, PID 25572):** Modell 1/13 (gemma-4-19b-reap) DS1000 done 28s, HumanEval+ pass@1 0.700, dann MATH-500 bei 5/10 abgebrochen 
    — `lm_eval returncode=3221225786` (=0xC000013A STATUS_CONTROL_C_EXIT, extern gekillt). **Kein Python-Prozess mehr aktiv.**
- **Modell gesund:** Direkter API-Test an `gemma-4-19b-a4b-it-reap-i1@q4_k_m` antwortet in 1,5 s („Hello."). 
    Es „schläft" nur, weil es als `idle` in LMS geladen blieb (LMS-Server läuft, Port 1234).
- **Skill-Bug gefunden:** `SKILL.md` (compaction-Skill) zeigte auf `Doku-intern/Chatverlauf*.md` statt `Doku-intern\compaction\compactions.md` 
    → Compactions wurden nicht korrekt angehängt. Zielpfad korrigiert + „hinten anhängen" explizit.

**Dieser Block ist der erste nach der Fix-Verifikation.**

## Work State
### Completed
- 13 Lauf-Keys ermittelt; `run.probelauf-familien.yaml` erstellt (alle lösen auf).
- GLM-Configs auf `enabled:true` gepatcht (mit Backups); `glm_patch_config` umgestellt + 5 Tests.
- `_check_registry_for_model`-Bug gefixt + 3 Tests; 87 Tests (run_benchmarks) + 79 (registry_tool) grün.
- Logs nach `logs\` verschoben; Lauf mit Fix neu gestartet.
- `SKILL.md` (compaction) Zielpfad korrigiert.

### Active
- Probelauf abgebrochen (MATH-500, externer Kill 0xC000013A) — **Ursache ungeklärt**, Modell hängt als idle in LMS. Neustart-Entscheidung offen (robust per schtasks vs. manuell).

### Blocked
- **Run-Wiederaufnahme offen:** User-Frage „Skill-Datei ändern für automatische Compaction?" beantwortet (ja, Zielpfad korrigiert); Lauf-Neustart noch nicht erfolgt.

## Next Move
1. Compaction-Skill-Fix bestätigen (dieser Block ist der Beleg).
2. Probelauf robust neu starten (entkoppelt von Shell-Wrapper, z.B. schtasks/geplanter Task), ggf. zuerst LMS-Modell unloaden; abwarten bis FINISHED.
3. Ergebnisse konsolidieren (nur CSVs Timestamp 20260815, 20260814 = fehlerhafter Lauf), alle 13 Modelle × 4 Benchmarks prüfen.
4. Offene Commits: registry_tool.py, run_benchmarks.py, Tests, run.probelauf-familien.yaml, AGENTS.md, Gemma-4-Registry (fremde Diffs auslassen).

## Relevant Files
- `run.probelauf-familien.yaml`: Run-Spec 13 Modelle, SS=10
- `src\registry_tool.py`: `glm_patch_config` enabled:true-Fix
- `src\run_benchmarks.py`: `_check_registry_for_model` Template-Skip-Fix
- `tests\test_registry_tool.py` (`TestGlmPatchConfig`), `tests\test_run_benchmarks.py` (`TestCheckRegistryForModel`)
- `logs\probelauf-familien-14.08.log` (+`.err`, `.pid`): abgebrochener Lauf
- `Doku-intern\compaction\compactions.md`: Ziel-Datei (jetzt korrekt befüllt)
- `C:\Users\pskra\.agents\skills\compaction\SKILL.md`: Zielpfad-Fix
- GLM-Configs (`user-concrete-model-default-config\`): `enabled:true` gepatcht (+ `.bak-parsing`)


=============== Compaction 16.08.2026 / Session-Skills ================
## Objective
- (Completed) Skill-Landschaft fuer lokal installierte LLMs gesichtet; offizielle Hersteller-Skills vs. Cloud/Community eingeordnet; 
    nemotron-customize installiert; glmv-caption fuer lokalen OpenAI-kompatiblen Endpunkt als lokale Kopie adaptiert.

## Important Details
- **Skill-Provenienz:** `gemma-dev` stammt aus `google-gemma/gemma-skills` (quell-verifiziert); lokale SKILL.md am 11.08. modifiziert gewesen (1.081 B vs. 9.142 B upstream) 
    -> Original wiederhergestellt; volle Version greift erst nach OpenCode-Neustart.

- **Hersteller-Skills (Recherche):** nur 3 offizielle Repos relevant: `google-gemma/gemma-skills` (gemma-dev+gemma-trainer, einziges echtes LOCAL-Deployment), 
    `zai-org/GLM-skills` (17 Skills, aber alle `ZHIPU_API_KEY`-Cloud), `nvidia/skills` (nemotron-customize etc., CUDA/Finetune-lastig). 
    Qwen/Kimi/DeepSeek/Phi/ERNIE/InternLM: keine offiziellen Skills, nur Community/Cloud-Wrapper. 
    Generische lokale Alternativen auf skills.sh (grepai-ollama-setup 748, local-llm-ops 346, llm-wiki 1.4K).

- **nemotron-customize installiert** (`npx skills add nvidia/skills@nemotron-customize -g -y`, Safe/0 Alerts). User hat CUDA 12.8-Backup llama.cpp.

- **GLM-skills Lokalisierung geprueft:** `glmv-caption.py` nutzt bereits OpenAI-kompatibles `/chat/completions` + base64 `image_url` -> direkt adaptierbar. 
    `glm_ocr_cli.py` nutzt proprietären `…/v4/layout_parsing`-Endpoint (hartkodiert, explizit kein Custom-URL-Support) -> NICHT lokalisierbar.

- **glmv-caption-local erstellt** unter `C:\Users\pskra\.agents\skills\glmv-caption-local\` (SKILL.md + `scripts\glmv_caption.py` + requirements.txt): 
    Base-URL via `GLM_LOCAL_API_BASE` (Default `http://127.0.0.1:1234/v1`), kein API-Key noetig, Default-Modell `zai-org/glm-4.6v-flash`,
    nur Bilder (kein video/file_url, kein thinking-Payload), deutscher Default-Prompt.

- **Verifikation:** Python-Syntax OK, `--help` OK, Pipeline erreicht Server korrekt (400 = Modell nicht geladen, kein Script-Fehler). 
    `zai-org/glm-4.6v-flash` laedt via `lms load` in 13.36s (9.36 GiB) - VLM lauffaehig.

## Work State
### Completed
- Recherche offizieller/Community-Skills fuer Qwen, GLM, Granite, Phi, Mistral, GPT-OSS, ERNIE, Kimi, Nemotron, DeepSeek (skills.sh + GitHub).
- gemma-dev SKILL.md-Original wiederhergestellt.
- nemotron-customize installiert.
- glmv-caption-local erstellt + statisch verifiziert.

### Active
- End-to-End-Test von glmv-caption-local offen (wartet auf Benchmark-Run-Ende im anderen Chat - dort wechseln staendig geladene Modelle).

### Blocked
- End-to-End-Test: aktuell NICHT moeglich, da ein Benchmark-Run aus anderem Chat laeuft (Modelle werden stetig geladen/entladen).

## Next Move
1. Nach Benchmark-Ende: `python scripts/glmv_caption.py --images <bild>` mit geladenem GLM-4.6V testen.
2. GLM-Skills-Ergebnis dem Nutzer als Liste praesentieren (falls gewuenscht weitere installieren).
3. Skills (glmv-caption-local, gemma-dev-Version) nach OpenCode-Neustart nutzbar; ggf. CHANGELOG-Eintrag.

## Relevant Files
- `C:\Users\pskra\.agents\skills\glmv-caption-local\` (NEU): SKILL.md, scripts\glmv_caption.py, scripts\requirements.txt
- `C:\Users\pskra\.agents\skills\nemotron-customize\` (NEU, installiert)
- `C:\Users\pskra\.agents\skills\gemma-dev\SKILL.md`: wiederhergestelltes Original (9.142 B)
- `C:\Users\pskra\.agents\.skill-lock.json`: Provenienz (google-gemma/gemma-skills, vercel-labs/skills)
- Referenz: `zai-org/GLM-skills` (glmv-caption = adaptierbar, glmocr = nicht)


=============== Compaction 17.08.2026 / 16:22 ================
## Objective
- (Current) Einen konkreten, Docker-freien Härtungsvorschlag für den hohen Security-Befund zur Ausführung modellgenerierten Python-Codes entwickeln.
- (Completed) Standard Security Scan abgeschlossen, Reports übersetzt und beide Fassungen im Projektstamm abgelegt.

## Important Details
- **Security-Befund:** `src/custom_benchmark.py:1193-1239` verwendet eine endliche Modul-Denylist und einen Allow-by-default-Import-Hook; `:1293-1305` startet normalen Host-Python; `:1809-1820` führt Modellantworten zur Auswertung. Das ist keine echte Sandbox und ermöglicht Builtins-Recovery.
- **Scanstatus:** Standard-Scan `0907d45e-324f-4275-b9f8-1950108f4f3d`, 2 Befunde: 1 hoch, 1 mittel. Bewertung war statisch, ohne Laufzeit- oder Netzwerk-Reproduktion.
- **Schwesterprojekt:** `Inspect-Evals\inspect_process_sandbox.py` nutzt frische Temp-Ordner, Pfadbegrenzung, bereinigte Environment-Allowlist, Output-Limits, Timeouts und Windows-Prozessbaum-Abbruch. Die eigene Dokumentation erklärt ausdrücklich, dass dies keine starke Sicherheitsgrenze ist.
- **Tradeoff:** Docker/WSL2 werden wegen Speicher- und Betriebsaufwand nicht vorausgesetzt. Windows Job Objects begrenzen Prozesse und Ressourcen, blockieren aber allein weder Netzwerk noch Dateisystem.
- **Entscheidungsvorschlag:** Kurzfristig einen Windows-native Worker mit JSON-stdin/stdout, `python -I -B -X utf8`, minimaler Umgebung, Temp-Root, strikter Import-Allowlist und Job Object bauen. Für wirklich feindlichen Modell-Output zusätzlich separates Windows-Benutzerkonto, NTFS-Beschränkung und ausgehende Firewall-Sperre.
- **Profile:** `strict` als Standard ohne Drittanbieterimporte; `compat` für DS1000 mit NumPy/Pandas/Matplotlib nur für vertrauenswürdige lokale Läufe. In-Process-Filter bleiben stets nur Korrektheitsfilter.

## Work State
### Completed / Active / Blocked
- Completed: Scan-Kontext und Quellstellen geprüft; `security-report-de.md` und `security-report-en.md` erstellt.
- Active: Architekturentscheidung für die Worker-Härtung steht aus.
- Blocked: Keine technische Blockade; eine echte Datei-/Netzwerkisolation ohne separates Konto oder vergleichbare OS-Grenze kann nicht ehrlich zugesichert werden.

## Next Move
1. Option für die Implementierung auswählen: pragmatische Job-Object-Härtung oder vollständigerer Worker mit separatem Windows-Konto und Firewall.
2. Vor der Implementierung die benötigten DS1000-Kompatibilitätsimporte und Ressourcenlimits festlegen.
3. Worker, Windows-Job-Object-Wrapper und Regression-/Windows-Integrationstests implementieren.
4. Danach gezielten Security-Diff-Scan beziehungsweise erneute Validierung durchführen.

## Relevant Files
- `src/custom_benchmark.py`: aktueller Modell-zu-Code- und Sandbox-Ausführungspfad.
- `C:\Users\pskra\Python-Projekte\Inspect-Evals\inspect_process_sandbox.py`: Referenz für den bestehenden Windows-Prozessrahmen.
- `C:\Users\pskra\Python-Projekte\Inspect-Evals\README_inspect_evals.md`: dokumentierte Grenzen des `process`-Backends.
- `security-report-de.md`: deutsche Scanfassung.
- `security-report-en.md`: englischer Originalreport.

=============== Compaction 17.08.2026 / 16:41 ================
## Objective
- (Current) Die kurzfristige Docker-freie Worker-Härtung für modellgenerierten Python-Code ist implementiert und verifiziert.
- (Completed) Inspect-Evals-Prozessmodell in Benchmarks integriert: JSON-Worker, bereinigte Umgebung, Import-Allowlist und Windows Job Object.

## Important Details
- **Worker:** `src/sandbox_worker.py` liest eine JSON-Anfrage über stdin und schreibt genau einen `__SANDBOX__`-JSON-Marker über stdout. Drittanbieter- und wissenschaftliche Module sind explizit allowlisted, bleiben aber ein Kompatibilitätsmodus und keine harte Sicherheitsgrenze.
- **Policy:** `os`, `sys`, `warnings`, `subprocess`, `socket`, `ctypes`, `pathlib`, `importlib` und weitere gefährliche Module sind nicht allowlisted. Dunder-Zugriffe werden vor `exec` per AST-Prüfung abgewiesen; gefährliche Builtins fehlen.
- **Process boundary:** `src/windows_job_object.py` setzt Kill-on-Close, maximal einen aktiven Prozess sowie Prozess-/Job-Speicherlimit. Der Worker startet suspendiert, wird per Toolhelp32-Threadsuche nach Job-Zuweisung fortgesetzt und beim Timeout beendet.
- **Windows-Fix:** Python 3.12 hält den primären Thread-Handle in `Popen` nicht öffentlich vor. Der Adapter nutzt deshalb `CreateToolhelp32Snapshot`/`Thread32First`/`OpenThread`/`ResumeThread` statt eines privaten `_thread`-Attributs.
- **Tests:** Echte Windows-Smoke-Checks waren erfolgreich: Basiscode und `math` laufen; `os`/`warnings` werden abgewiesen; Endlosschleife endet nach Timeout. Fokussierte Suite: 38 passed. Vollsuite: 847 passed, 3 isoliert reproduzierbare bestehende `model_manager`-Fehler außerhalb dieser Änderung.

## Work State
### Completed / Active / Blocked
- Completed: Worker-Integration, Job Object, Environment-Filter, JSON-Protokoll, Tests und Ruff-Prüfung.
- Active: Die Härtung ist Defense-in-depth; echte Datei-/Netzwerkisolation ohne separates Windows-Konto und Firewall ist weiterhin nicht zugesichert.
- Blocked: Keine Blockade für die implementierte kurzfristige Variante.

## Next Move
1. DS1000 mit echten wissenschaftlichen Setup-/Referenz-Imports als Kompatibilitätstest ausführen.
2. Optional separates Worker-Konto mit NTFS- und Firewall-Regeln ergänzen, wenn feindlicher Modell-Output das Bedrohungsmodell ist.
3. Danach gezielten Security-Diff-Scan gegen die geänderten Sandbox-Dateien durchführen.

## Relevant Files
- `src/custom_benchmark.py`: Worker-Start, Environment-Filter und Timeout-/Cleanup-Pfad.
- `src/sandbox_worker.py`: JSON-Protokoll, Allowlist und In-Process-Policy.
- `src/windows_job_object.py`: Windows Job Object und suspendierter Worker-Start.
- `tests/test_sandbox_worker.py`: Policy- und Recovery-Regressionstests.
- `tests/test_custom_benchmark_io.py`: Parent-/Prozessprotokoll- und Environment-Tests.

=============== Compaction 17.08.2026 / 17:31 ================
## Objective
- (Current) Die kurzfristige Docker-freie Worker-Isolation im Benchmark-Projekt beibehalten und die reale DS1000-Kompatibilitaet sowie den verbleibenden Security-Abstand weiter pruefen.
- (Completed) Inspect-Evals-inspiriertes Prozessmodell mit strikter Import-Allowlist, JSON-Worker-Protokoll, bereinigter Umgebung und Windows Job Object umgesetzt.

## Important Details
- `src/custom_benchmark.py` startet `src/sandbox_worker.py` isoliert mit `python -I -B -X utf8`, frischer Temp-Umgebung, Pipes, gefilterten Umgebungsvariablen und Ressourcen-/Timeout-Limits.
- `src/sandbox_worker.py` verarbeitet genau eine JSON-Anfrage und liefert einen begrenzten JSON-Marker. Dunder-Recovery, gefaehrliche Builtins und nicht allowlistete Imports werden abgewiesen. Wissenschaftliche Bibliotheken bleiben fuer DS1000-Kompatibilitaet allowlisted, sind aber keine harte Sicherheitsgrenze.
- `src/windows_job_object.py` setzt Kill-on-Close, Prozessanzahl- und Speicherlimits. Da Python 3.12 keinen nutzbaren primaeren Thread-Handle ueber `Popen` bereitstellt, wird der suspendierte Thread ueber Toolhelp32 gefunden und fortgesetzt.
- Ein anfänglicher Windows-Handle-Konflikt bei temporaren stdout/stderr-Dateien wurde durch Pipes und einen begrenzten Worker-Writer behoben.
- Verifikation: `compileall`, Ruff und fokussierte Suite erfolgreich; fokussiert 38 Tests bestanden. Live-Smoke: Basiscode und `math` erfolgreich, `os`/`warnings` blockiert, Timeout erfolgreich. Vollsuite: 847 bestanden, 3 reproduzierbare bestehende `model_manager`-Fehler ausserhalb dieser Aenderung.

## Work State
### Completed / Active / Blocked
- Completed: Worker-Integration, Allowlist, JSON-Protokoll, Environment-Filter, Job Object, Timeout-/Cleanup-Pfad und Regressionstests.
- Active: DS1000-Kompatibilitaet mit echten wissenschaftlichen Imports sowie Bewertung eines separaten Windows-Kontos mit NTFS-/Firewall-Regeln fuer feindlichen Modell-Output.
- Blocked: Keine Blockade fuer die kurzfristige Implementierung; die drei bestehenden `model_manager`-Fehler verhindern lediglich eine vollstaendig gruene Gesamtsuite.

## Next Move
1. Einen kleinen DS1000-Kompatibilitaetslauf mit echten Setup- und Referenz-Imports ausfuehren.
2. Bei hoeherem Bedrohungsniveau separates Worker-Konto, NTFS-Berechtigungen und Firewall-Regeln ergaenzen.
3. Einen gezielten Security-Diff-Scan fuer die geaenderten Sandbox-Dateien starten.

## Relevant Files
- `src/custom_benchmark.py`
- `src/sandbox_worker.py`
- `src/windows_job_object.py`
- `tests/test_sandbox_worker.py`
- `tests/test_custom_benchmark_io.py`
- `CHANGELOG.md`
- `security-report-de.md`
- `security-report-en.md`

=============== Compaction 17.08.2026 / 18:48 ================
## Objective
- (Current) Provider-Schicht fuer die Benchmark Suite beginnen und LM-Studio-Abhaengigkeit schrittweise entkoppeln.
- (Completed) Detaillierte Zwischenplanung in PLANUNG.md dokumentiert und aus doc-git verschoben; Phase-1-Providergrenze implementiert.

## Important Details
- **Context:** Der bestehende Launcher importiert weiterhin stabile Funktionen aus model_manager.py. LM Studio besitzt neben OpenAI-kompatibler Inferenz native CLI-/REST-Lifecycle-Funktionen; TabbyAPI hat eigene /model-Endpunkte; OpenAI-Kompatibilitaet standardisiert Load/Unload nicht.
- **Decision:** LLM_PROVIDER steuert lmstudio, tabbyapi oder openai_compat. In Phase 1 bleibt lmstudio auf dem bisherigen Legacy-Pfad, damit vorhandene Tests und Runtime-Seams stabil bleiben. Alternative Provider laufen bereits ueber src/providers.
- **Source of Truth:** model_registry.yaml fuer Benchmark-Policy; GGUF-Header fuer technische Modelldaten; LM-Studio-JSON nur als LM-Studio-Runtimeartefakt.
- **Finding:** OpenAICompatProvider darf unload nicht als erfolgreiches No-op ausgeben. TabbyAPI-Load braucht versionsabhaengige Polling-/Payload-Verifikation, insbesondere max_seq_len und cache_size.

## Work State
### Completed / Active / Blocked
- Completed: Provider-Vertraege, Provider-Fabrik, drei Providerdateien, Nicht-LM-Studio-Delegation, 10 Contract-Tests, Planung und Changelog.
- Active: Phase 2, Extraktion der bestehenden LMS-CLI-/REST-Logik aus model_manager.py.
- Blocked: Kein Architektur-Blocker. Ein bestehender Windows-Berechtigungsfehler verhindert aktuell eine vollstaendig gruene model_manager-Teilsuite.

## Next Move
1. Bestehenden LM-Studio-Code schrittweise nach lmstudio_provider.py verschieben und Legacy-Aliase beibehalten.
2. TabbyAPI-Endpunkte gegen die lokal installierte Version pruefen; danach sample_size=1-Smoke-Test.
3. Registry-Runtimewerte fuer provider-neutrale und provider-spezifische Load-Parameter trennen.

## Relevant Files
- PLANUNG.md: Architekturentscheidungen und Phasenplan.
- src/model_manager.py: Kompatibilitaetsfassade und aktuelle Delegationsgrenze.
- src/providers/base.py: Provider-Vertraege und HTTP-Basis.
- src/providers/lmstudio_provider.py: Zielmodul fuer Phase-2-Extraktion.
- src/providers/tabbyapi_provider.py: ExLlamaV3-/TabbyAPI-Lifecycle.
- src/providers/openai_compat_provider.py: Inference-only Provider.
- tests/test_provider_architecture.py: Contract- und Auswahltests.

=============== Compaction 17.08.2026 / Phase 2 ===============
## Objective
- (Completed) Die eigentliche LM-Studio-CLI-/REST-Lifecycle-Logik aus `model_manager.py` in `LMStudioProvider` verschieben und den Launcher provider-neutral anbinden.
- (Current) TabbyAPI-Endpunkte und Registry-Runtimewerte gegen die lokal installierte Version verifizieren.

## Important Details
- `LMStudioProvider` besitzt jetzt `lms ls --json`, `lms ps --json`, native Load-/Unload-Aufrufe, Readiness-Polling und den LM-Studio-Serverstart inklusive `llmster.exe`-Fallback.
- `model_manager.py` ist eine Kompatibilitaetsfassade: `get_provider()`, Registry-Anbindung, Identifier-Validierung sowie provider-neutrale `load_model()`/`unload_all()` bleiben dort. `load_model_via_lms()` und `has_unloaded_all_models()` sind Aliase fuer bestehende Aufrufer.
- Die bisherige implizite LMS-zu-Tabby-Ausweichlogik wurde entfernt. TabbyAPI wird ausschliesslich ueber `LLM_PROVIDER=tabbyapi` gewaehlt; dadurch bleiben Fehler und Messungen backend-eindeutig.
- `run_benchmarks.py` ruft fuer Lifecycle-Operationen die neutralen Manager-Funktionen auf. `custom_benchmark.py` und `tools/parallel_ab.py` duerfen die alten Aliase vorerst weiterverwenden.
- Verifikation: `py -3.12 -m compileall -q src/providers src/model_manager.py tests/test_provider_architecture.py`; Ruff erfolgreich; fokussiert 85 Provider-/Manager-Tests plus 4 Launcher-Regressionstests bestanden. Danach Vollsuite in einem explizit freigegebenen Temp-Pfad: 860 gesammelt, 858 passed, 2 failed, 0 Setup-Fehler. Die zwei verbleibenden Fehler sind eine bestehende Registry-/Testbaseline-Differenz fuer GLM-4.7 (Registry 0.8/0.6, Test 0.7/1.0), ohne Providerbezug.

## Work State
### Completed / Active / Blocked
- Completed: Phase-2-Extraktion, provider-neutraler Launcher-Lifecycle, Legacy-Aliase und Regressionstests.
- Active: Phase 3 TabbyAPI-Produktionsverifikation sowie Phase 5 Registry-/GGUF-Runtime-Kontrakt.
- Blocked: Kein Architektur-Blocker. Kein echter Load-/Unload-Smoke-Test wurde ausgefuehrt, um keinen laufenden lokalen Modellserver zu veraendern.

## Next Move
1. TabbyAPI-Endpunkte, Authentifizierung und Load-Polling gegen die installierte Version pruefen.
2. Runtimewerte aus `model_registry.yaml` und GGUF-Headern fuer TabbyAPI abbilden.
3. Danach einen kontrollierten `sample_size=1`-Smoke-Test mit `run.tabbyapi.yaml` ausfuehren.

## Relevant Files
- `src/providers/lmstudio_provider.py`
- `src/model_manager.py`
- `src/run_benchmarks.py`
- `src/providers/base.py`
- `tests/test_provider_architecture.py`

=============== Compaction 17.08.2026 / Phase 3 ===============
## Objective
- TabbyAPI als produktionsfaehigen Lifecycle-Provider gegen die lokal installierte ExLlamaV3-Umgebung verifizieren und die technische Modell-ID von der kanonischen Registry-Identitaet trennen.

## Important Details
- Lokale Laufzeit: `C:\Users\pskra\Python-Projekte\exllamav3\exllamav3_env`, Python 3.12, Torch `2.10.0+cu128`, ExLlamaV3 `1.4.1`, TabbyAPI-Commit `3d2848d0`.
- TabbyAPI-Contract live bestaetigt: `/v1/models` liefert die Modellordner; `/v1/model` liefert `503` ohne Modell und danach verschachtelte `parameters`; `/v1/model/load` antwortet als SSE-/Detached-Task; `/v1/model/unload` antwortet mit HTTP 200 und JSON `null`.
- Providerfix: Load und Unload lesen den Response-Body nicht mehr aus, wenn nur der HTTP-Erfolg relevant ist. API-Key und Admin-Key bleiben getrennte Header-/Umgebungsvariablen.
- Registry-Identitaet: Der technische Tabby-Name `google_gemma-4-26b-a4b-it`, API-ID und Pfad werden in `AvailableModelInfo` getrennt vom kanonischen Key `unsloth/gemma-4-26b-a4b-it@iq3_s` gefuehrt. Registry-only-Filterung erfolgt zentral in `model_manager.py`.
- Registry-Runtime live angewendet: `max_seq_len=32768`, `cache_size=32768`, `cache_mode=FP16`; TabbyAPI meldete diese Werte nach dem Load zurueck. Eine kleine 1B-Chat-Anfrage lief ebenfalls erfolgreich.
- Echter Run-Spec-Smoke: `run.tabbyapi.yaml`, CLI-Override `--model google_gemma-4-26b-a4b-it --benchmarks HellaSwag --sample-size 1 --seed 2026`. Ergebnis: 101 interne Chat-Anfragen, Score `0.23`, sauberes Unload um 21:50:06. Die hohe GPU-Auslastung war durch aktiviertes Thinking und die vielen lm-eval-Requests erwartbar; kein OOM und kein Prozesshaenger.

## Verification
- Ruff fuer geaenderte Provider-/Manager-/Runner-Dateien erfolgreich.
- Fokussierte Regression: 177 Tests bestanden, 1 bestehender `uses_newest_llmster_version`-Test ausgeschlossen.
- Die Vollsuite-Baseline bleibt: 860 gesammelt, 858 bestanden, 2 Registry-/Testbaseline-Mismatches fuer GLM-4.7, 0 Setup-Fehler bei explizitem beschreibbarem Temp-Pfad.

## Work State
- Completed: Phase 3, inklusive echter TabbyAPI-Inferenz und Lifecycle-Cleanup.
- Next: Phase 4 OpenAI-kompatibler Provider/Unsloth-Endpoint; danach Phase 5 als formaler zentraler Registry-/GGUF-Runtime-Kontrakt.

=============== Compaction 17.08.2026 / Phase 4 Zwischenstand ===============
## Objective
- Den OpenAI-kompatiblen Provider als Inference-only-Backend belastbar in die Benchmark-Fassade integrieren und Unsloth Studio auf Wiederverwendung dieses Providers pruefen.

## Important Details
- `/v1/models` liefert technische Modell-IDs unveraendert; keine LM-Studio-Normalisierung.
- Generische OpenAI-Kompatibilitaet besitzt keinen standardisierten Current-/Load-/Unload-Lifecycle. Fuer `LLM_PROVIDER=unsloth` sind jedoch die authentifizierten Erweiterungen `/v1/load` und `/v1/unload` belegt; `current_model()` nutzt das explizite `loaded`-Feld, und Load/Unload werden mit Polling ausgefuehrt.
- Auth-Header: expliziter Key, `OPENAI_COMPAT_API_KEY`, `OPENAI_API_KEY`, `LLM_API_KEY`.
- Unsloth-Konfiguration kann eindeutig ueber `LLM_PROVIDER=unsloth`, `UNSLOTH_API_BASE` und `UNSLOTH_API_KEY` erfolgen; die generischen Variablen bleiben kompatibel. `PYTHONPATH` ist beim normalen Launcher-Aufruf aus dem Projektroot nicht erforderlich.
- Der Runner fragt Provider-Capabilities ab, reloadet bei Inference-only-Providern nicht blind und weist `--unload-between` mit klarer Meldung zurueck.
- Unsloth Studio wurde auf Port 8888 authentifiziert: `/v1/models` lieferte 69 Modelle, davon eines mit `loaded=true`; eine kleine Chat-Anfrage lief in 2,28 s. Die OpenAPI bestaetigt Load/Unload mit `model_path`.

## Verification
- Ruff erfolgreich.
- Python-3.12-Compileall erfolgreich.
- Fokussierte Regression: **183 passed, 1 deselected**.
- Vollsuite: **871 gesammelt, 869 passed, 2 bekannte GLM-4.7-Registry-/Testbaseline-Mismatches, 0 Setup-Fehler**.
- Nach Lifecycle-Erweiterung bereinigte fokussierte Regression: **187 passed, 1 deselected**. Die globale Benutzerkonfiguration `LLM_PROVIDER=unsloth` muss fuer die Legacy-Testbaseline temporär aus der Testprozessumgebung entfernt werden.
- Vollsuite nach Lifecycle-Erweiterung: **875 gesammelt, 873 passed, 2 bekannte GLM-4.7-Registry-/Testbaseline-Mismatches, 0 Setup-Fehler**.

## Work State
- Completed: OpenAI-kompatibler Provider-Vertrag und Runner-Integration.
- Completed: Authentifizierte Unsloth-Discovery und Chat-Smoke; OpenAI-Provider um expliziten Unsloth-Lifecycle erweitert.
- Open: Nicht-destruktiver Live-Load/Unload-Smoke mit einem geeigneten Wechselmodell; Registry-Runtimewerte fuer Unsloth folgen in Phase 5.
- Next: Phase 5 Registry-/GGUF-Runtime-Kontrakt.

=============== Compaction 18.08.2026 / 10:32 ================
## Objective
- (Completed) Variante B fuer Unsloth als eigenstaendigen, vom Runner gestarteten `llama-server.exe` umsetzen und die lokale Modellaufloesung an die tatsaechliche Unsloth-Ablage anpassen.
- (Current) Den provider-neutralen Registry-/GGUF-Runtime-Kontrakt in Phase 5 weiterfuehren.

## Important Details
- Unsloth legt echte GGUF-Dateien sowohl direkt unter `~\\.lmstudio\\models` als auch im Cache `~\\.lmstudio\\models\\hub\\models--<org>--<repo>\\snapshots\\<revision>` ab. `~\\.lmstudio\\hub` ist dagegen der separate LM-Studio-Konfigurationsbereich und wird vom Unsloth-Resolver nicht durchsucht.
- Die erste exakte Registry-Pruefung verwarf gueltige Cache-Modelle mit `-GGUF` im Ordnernamen. Eine flexible Pruefung konnte dagegen eine falsche Quantisierung zuweisen, etwa lokales `Q4_K_XL` als Registry-`Q8_0`. Der Resolver normalisiert jetzt die Basis-ID, verlangt die exakt passende Quantisierung und akzeptiert nur die bewusst definierte `@mixed`-Ausnahme.
- Inventur: 42 lokale GGUFs sind Registry-gueltig; 17 weitere bleiben wegen fehlendem oder nicht passendem Registry-Key ausgeschlossen. Das ist fuer den Benchmark-Provider beabsichtigt.

## Work State
### Completed / Active / Blocked
- Completed: Unsloth-Cache-Erkennung, Quantisierungs-Schutz, Tests und Dokumentation. Der echte Zwei-Modell-Load/Inference/Unload-Smoke war bereits erfolgreich; Port `8890` ist danach frei.
- Verification: Fokussiert 36 Tests bestanden; Vollsuite ohne `tests/test_model_manager.py`: 808 bestanden, 2 bekannte unabhaengige Sampling-/Thinking-Fehler.
- Blocked: Kein Provider-Blocker. Die Legacy-`model_manager`-Tests bleiben wegen alter Mock-Seams separat offen.

## Next Move
1. Phase 5 als zentralen Registry-/GGUF-Runtime-Kontrakt konkretisieren.
2. Kontextlaenge, Sampling, Reasoning, Quant und Parallelitaet provider-neutral aus Registry/GGUF ableiten.
3. Provider-spezifische Load-Parameter fuer LM Studio, TabbyAPI und Unsloth daraus ableiten und gezielt testen.

## Relevant Files
- `src/local_model_resolver.py`: Unsloth-Cache-Aufloesung und quant-sicheres Registry-Matching.
- `src/providers/unsloth_server_provider.py`: Prozess-Lifecycle des lokalen Unsloth-Servers.
- `tests/test_local_model_resolver.py`: Cache-, Registry- und Fehlquantisierungs-Regressionen.
- `PLANUNG.md`: Phase-4b-Abnahme und korrigierte Pfad-/Inventardokumentation.

=============== Compaction 18.08.2026 / 14:27 ================
## Objective
- (Completed) Phase 5 abschliessen: GGUF-Header plus `model_registry` als Laufzeit-/Benchmark-Quelle der Wahrheit festziehen, LM-Studio-JSON-Artefakte provider-lokal halten und den Runner weiter von LM Studio entkoppeln.
- (Current) Den Zustand sauber festhalten, damit die naechsten Provider-Schritte ohne Rueckfall in die alte LM-Studio-Kopplung weitergehen koennen.

## Important Details
- Architekturentscheid: Der GGUF-Header definiert die Modellarchitektur und ihre technischen Grenzen; `doc-git/model_registry.yaml` definiert Benchmark-Metadaten, Sampling, Reasoning, Quantisierung und Kontextpolitik; LM-Studio-JSON-Konfigurationen sind nicht mehr globale Laufzeit-Wahrheit.
- `src/model_registry.py` loest Registry-Aliase auf und leitet provider-spezifische Runtime-Views ab, inklusive nativer vs. Benchmark-Kontextlaengen und technischer Grenzpruefung.
- `src/model_manager.py` delegiert Runtime-Auswahl jetzt an `ModelRegistry` und haelt die LM-Studio-spezifische Logik nur noch als schmale Provider-Schnittstelle fuer das zusammengesetzte Systemprompt-Artefakt.
- `src/providers/lmstudio_provider.py` prueft das LM-Studio-Artefakt fuer das assemblete Systemprompt; `src/run_benchmarks.py` nutzt dafuer jetzt diesen Provider-Hook statt direkt LM-Studio-JSON-Dateien auszuwerten.
- Letzte Verifikation: fokussierte Tests fuer Registry-/Provider-Architektur bestanden, Ruff war sauber. Es wurde kein neuer Funktionsblocker eingefuehrt.
- Das Working Tree ist bewusst unruhig und enthaelt fremde bzw. vorbestehende Aenderungen und temporäre Benchmark-Artefakte; weitere Arbeit muss strikt scoped bleiben und darf nichts Unerreichtes zuruecksetzen.

## Work State
### Completed / Active / Blocked
- Completed: provider-neutraler Runtime-Kontrakt, Trennung des LM-Studio-Prompt-Artefakts und die dazugehoerigen Regressionstests.
- Active: kein Code-Blocker an dieser Stelle; der naechste sinnvolle Schritt ist, die restlichen Provider-Start-/Load-Parameter ebenfalls konsequent aus Registry/GGUF abzuleiten.
- Blocked: keiner.

## Next Move
1. Provider-spezifische Launch-/Load-Parameter weiter nur aus Registry und GGUF-Metadaten ableiten, nicht aus ad-hoc JSON-Seitenkanaelen.
2. Model-familien-spezifische Template- oder Runtime-Overrides nur dort erweitern, wo es dafuer explizite Evidenz gibt.
3. Beim Start der naechsten Phase die betroffenen Provider-Pfade mit einem kleinen, fokussierten Testslice verifizieren, bevor die Flaeche erweitert wird.

## Relevant Files
- `src/model_registry.py`
- `src/model_manager.py`
- `src/providers/lmstudio_provider.py`
- `src/run_benchmarks.py`
- `tests/test_model_registry.py`
- `tests/test_provider_architecture.py`
- `doc-git/model_registry.yaml`
