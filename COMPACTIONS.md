### COMPACTIONS.md für Projekt "C:\Users\pskra\Python-Projekte\Benchmarks" ###

Compaction-Blöcke werden hier fortlaufend hinten angehängt (Anlass-bezogen oder per Kommando). CHANGELOG = was, Compaction = warum/was nächste.


============== Compaction 06.08.2026 / 19:35 ==================
## Objective
- Review-Prozess-Konzept (3 Säulen) umsetzen, das der Nutzer mit „Ja, so umsetzen" abgesegnet hat: (1) CHANGELOG.md als zentrale Design-/Bug-/Fix-Doku, (2) Pre-Commit-Gate (pre_review_checks.ps1 v2 + validate-Erweiterung + pre-push-Hook + CI-Fix), (3) Transparenz-Artefakte (repro_issues.md, lint_issues.md committet, Logs ignoriert).

## Important Details
- Nutzer-Entscheidungen aus den 3 Konzept-Fragen:
  1. Artefakte: `repro_issues.md` + `lint_issues.md` werden committet; `validate_errors.log` + `pre_review_checks_*.log` → `.gitignore` (transient).
  2. CHANGELOG: **Root `CHANGELOG.md`** (neu); §20 „Version Changelog" aus `doc-git/Architecture, Flow & ChangeLog_en.md` (Z. ~1312) wandert vollständig dorthin, Architecture-Doku behält nur Verweis. Eintrag-Format: Datum | Datei(en) | Entscheidung/Fix + Zeilen `Grund:`/`Quelle:`.
  3. Push-Gate: **pre-push-Hook + CI-Fix** (nach Erklärung von Hook/CI gewählt; Hook bricht `git push` bei Fehlern ab, CI läuft nach Push auf GitHub als Sicherheitsnetz).
- Zusatz-Anmerkung des Nutzers: Artefakte ersetzen **nicht** den Review-Bericht; CHANGELOG entlastet README (reiner Quickstart); Fehler treten auch im laufenden Betrieb auf (z. B. Benchmark-Runs), nicht nur bei Reviews; Verfahren muss einfach/sicher sein („nichts vergessen" bei vielen Schritten).
- Geplante Dateien laut Konzept/Todo: `CHANGELOG.md` (Root), `doc-git/Review-Prozess.md`, `doc-git/Reviews/_templates/{Phase1-Prompt.md, Phase2-Prompt.md, Review-Report-Template.md}` (konsolidiert aus `Doku-intern/Review-Checkliste (Single-Entwickler).md` + `Doku-intern/Review Prompt für Benchmarktest.md` + Heise-Prinzipien), `doc-git/Review-Artifacts/` (repro_issues.md + lint_issues.md als Snapshot je Review), `scripts/pre-push.ps1` + Installer (via `core.hooksPath`), `.gitignore`-Ergänzung, `.github/workflows/review.yml`-Fix.
- Umsetzungsreihenfolge: validate-Erweiterung (──repro/--verbose) → Skript v2 → Hook → CI-Fix → CHANGELOG (§20-Umzug) → Templates → Prozess-Doku/Artefakte/gitignore → End-to-End-Test (Gate-Lauf, Hook-Test, CI-YAML-Syntax).
- Für `--repro`: Nutzung von `src/tools/gguf_full_metadata_reader.py` (nutzt `from gguf import GGUFReader`); Vergleichsquellen: `~/.lmstudio/hub/models/{publisher}/{model}/model.yaml`, JSON-Configs, `model_registry.yaml`, GGUF-Header.
- Offene Kleinigkeit aus Konzept: `gguf`-Paket verfügbar? → **geklärt: installiert** (`C:\Users\pskra\AppData\Local\Programs\Python\Python314\Lib\site-packages\gguf\__init__.py`); ebenso ruamel.yaml + psutil OK.
- Verbleibende Altlasten: 5 untracked `pre_review_checks_20260806_*.log` bleiben uncommittet; DeepSeek-Registry-Einträge bleiben (6 „missing"); Registry = 64 Keys; validate = 0 Probleme (Stand vor dieser Sitzung).

## Work State
### Completed
- Konzept (3 Säulen, 11 Schritte) erstellt, vom Nutzer freigegeben; 3 Folge-Fragen beantwortet; Zusatz-Anmerkungen integriert.
- Todo-Liste (9 Items) angelegt — aktuelle Reihenfolge: Baseline → validate --verbose/--repro → Skript v2 → Hook → CI → CHANGELOG → Templates → gitignore/Artefakte → E2E-Test.
- Basline-Checks z. T. durchgeführt:
  - `gguf` (Python314 site-packages), `ruamel.yaml`, `psutil` importierbar.
  - `pre_review_checks_20260806_132030.log` zeigt Bug #1: Skript ruft `registry_tool.py validation` (falsch) statt `validate` → `[ERROR] Unknown command: validation`.
  - Bug #2 (bekannt): Skript-Schritt 4 ruft gelöschtes `src\tools\_check_gguf_ctx.py` auf.
  - **Neuer Bug #3**: `ruff check .` bricht mit `unknown field 'tool'` ab — verursacht durch `--config .\.pyproject.toml` im Skript: die Root-`pyproject.toml` enthält jetzt nur `[tool.pytest.ini_options]`, keinen `[tool.ruff]`-Block (Ruff-Configs liegen in `.ruff.toml` + `.pyproject.toml` versteckt).
- Frühere Sitzung (Kontext für CHANGELOG/Review): Review-Berichte von 2026-06-28 bis 2026-08-03 in `doc-git/Reviews/` (10 Stück, Format: ISO/IEC 9126, Artefakt-Referenzen, Commit-Hashes, P0/P1/P2-Priorisierung).

### Active
- Todo 1 „Baseline: ruff/mypy-Status, gguf-Paket, pre_review-Log auswerten" fast fertig — ruff-Status noch unklar, weil `ruff check .` am Config-Fehler abstürzt; mypy-Status noch nicht gelaufen.
- Todo 2 „registry_tool.py: validate --verbose + --repro" noch nicht begonnen.

### Blocked
- (none) — aber `ruff check .` muss zunächst ohne die kaputte `--config .\.pyproject.toml`-Angabe getestet werden (bzw. auf `.ruff.toml` umgestellt).

## Next Move
1. Ruff-Config-Problem verifizieren/lösen: `ruff check .` **ohne** `--config` testen (nutzt dann auto-detect von `.ruff.toml`); ggf. Doppel-Config-Konflikt `.ruff.toml` ↔ verstecktes `.pyproject.toml` prüfen; Fehlerbehebungs-Entscheidung für v2-Skript festhalten.
2. Todo 2: `validate` in `src/registry_tool.py` erweitern — `--verbose` (Detail je Prüfpunkt) + `--repro` (schreibt `doc-git/Review-Artifacts/repro_issues.md` mit Diskrepanzen Registry ↔ JSON-Configs ↔ `hub/models/*/model.yaml` ↔ GGUF-Header via `gguf_full_metadata_reader.py`).
3. Todo 3: `pre_review_checks.ps1` v2 schreiben — ① Git-Status/Branch-Info ② `validate` (immer zusätzlich in `validate_errors.log`) ③ `ruff check` + `mypy` → `lint_issues.md` ④ `pytest tests/` ⑤ `validate --repro` → `repro_issues.md`; harte Stopps bei Exit-Code ≠ 0; Bug `validation`→`validate` fixen; toten `_check_gguf_ctx.py`-Aufruf ersetzen; `--config`-Flag korrigieren.
4. Danach gemäß Todo-Liste: pre-push-Hook + Installer (`scripts/hooks/`, `core.hooksPath`), CI-Fix (`review.yml`: Runner `windows-2025`, Deps via `[project]`-Metadaten ergänzen oder `requirements.txt`), CHANGELOG.md (§20-Umzug + neue Einträge), `_templates/` + `Review-Prozess.md`, `.gitignore` + `Review-Artifacts/`-Initialisierung, abschließender End-to-End-Test.

## Relevant Files
- `src/registry_tool.py` — validate erweitern (`--verbose`, `--repro`); Dispatch `elif cmd == "validate"` (Z. ~2265), `cmd_validate`-Report (Z. ~1825)
- `pre_review_checks.ps1` — v2-Rewrite; bekannte Bugs: `validation`-Aufruf, toter `_check_gguf_ctx.py`-Aufruf, `--config .\.pyproject.toml` (→ „unknown field `tool`")
- `pyproject.toml` (Root, neu) — nur `[tool.pytest.ini_options]`; Ursache des ruff-Config-Fehlers im Skript
- `.ruff.toml`, `.pyproject.toml` (versteckt) — Ruff/pylint/mypy-Configs (aus Mistral/Vibe https://chat.mistral.ai/work/e4dd489b-946d-412d-9538-ec17a803c108), entstehen als neue Dateien bereits committet (a276f160)
- `.github/workflows/review.yml` — aktuell kaputt: `runs-on: Windows 11` (ungültig), `pip install -e .` scheitert (kein `[project]`-Block), fehlende Deps (ruamel.yaml/psutil/gguf)
- `doc-git/Architecture, Flow & ChangeLog_en.md` — §20 „Version Changelog" (Z. ~1312) wandert in CHANGELOG.md; Verweis statt §20
- `src/tools/gguf_full_metadata_reader.py` — GGUF-Metadaten-Extraktion für `--repro`
- `doc-git/Reviews/` (10 Berichte) + `Doku-intern/Review-Checkliste (Single-Entwickler).md`, `Doku-intern/Review Prompt für Benchmarktest.md` — Quelle für `_templates/`-Konsolidierung
- `C:\Users\pskra\.lmstudio\hub\models\{publisher}\{model}\model.yaml` — Vergleichsquelle für `--repro`
- `.gitignore` — Ergänzen: `validate_errors.log`, `pre_review_checks_*.log`; `doc-git/Review-Artifacts/` wird committet

================= Compaction 06.08.2026 / 20:42 ===========
## Objective
- Review-Prozess-Konzept (3 Säulen) umsetzen: CHANGELOG.md, Pre-Commit-Gate (pre_review_checks.ps1 v2 + validate-Erweiterung + pre-push-Hook + CI-Fix), Transparenz-Artefakte (repro_issues.md/lint_issues.md committet).
- Aktueller Arbeitsschritt: Baseline abschließen (ruff/mypy) und `validate --verbose/--repro` in `registry_tool.py` implementieren.

## Important Details
- **Config-Konsolidierung abgeschlossen**: verstecktes `.ruff.toml` + `.pyproject.toml` per `git rm` entfernt; **alle** Tool-Configs (pytest/ruff/mypy/pylint) jetzt in sichtbarem Root-`pyproject.toml`; `ruff check .` ohne `--config`-Flag im Skript.
- **Mistral-Regelliste ist nur Vorschlag** (expliziter Nutzerhinweis): „Empfehlungen aus Mistral-Chat müssen nicht streng gefolgt werden … lieber einmal mehr fragen, wenn etwas unklar ist".
- Nutzer-Entscheidungen dieser Sitzung:
  1. FBT001/002/003 + S310/S603/S607 → in `pyproject.toml` ignore-Liste aufgenommen (mit Begründungskommentaren, Entscheidung 06.08.2026).
  2. mypy im Gate: **nur informativ, nicht blockierend** (195 Legacy-Typfehler).
  3. ANN101/ANN102 aus ignore entfernt (Ruff-Warnung: Regeln entfernt, Ignorieren wirkungslos).
- **Ergebnis Baseline**: `ruff check .` → „All checks passed!" (0 Fehler, Ausgangslage 531); `python -m pytest -q` → 741 passed (4.19–4.61 s); `mypy .` → 195 Fehler in 13 Dateien (informativ; Top: custom_benchmark 40, run_benchmarks 36, assemble_blueprint 23, consolidate_results 22, gguf_full_metadata_reader 22; Top-Kategorien: type-arg 51, assignment 24, attr-defined 22, var-annotated 18).
- Wichtige Fixes: B023 **echter Thread-Bug** in `custom_benchmark.py` (~Z. 589–599: Closures eingefroren als Default-Argumente `result_lock`/`result`/`cancel_event`/`current_start_timeout`, danach ANN001-Typannotationen `threading.Lock`/`dict[str, Any]`/`threading.Event`); Re-Export `USE_UNIFIED_KV_CACHE_THRESHOLD_GB as _USE_UNIFIED_KV_CACHE_THRESHOLD_GB` + `# noqa: F401` in `registry_tool.py` wiederhergestellt (Tests importieren ihn); S506-noqa in `run_benchmarks.py` Z. 300 („_NoopLoader ist bewusst sicher – yaml.safe_load scheitert an lm_eval-`!function`-Tags"); B007-Bereinigung via `_`/`.values()`; B905 `strict=True`; TYPE_CHECKING-Blöcke in 5 Dateien.
- Bekannte Skript-Bugs für v2-Rewrite (noch offen): `registry_tool.py validation` (falscher Befehl) + toter `src\tools\_check_gguf_ctx.py`-Aufruf.
- Geplante Artefakte/Doku unverändert (CHANGELOG.md Root, `doc-git/Review-Prozess.md`, `doc-git/Reviews/_templates/`, `doc-git/Review-Artifacts/`, `scripts/pre-push.ps1` + Installer via `core.hooksPath`, `.github/workflows/review.yml`-Fix, `.gitignore` um `validate_errors.log`/`pre_review_checks_*.log`).

## Work State
### Completed
- **Todo 1 (Baseline) komplett**: ruff 531→0 Fehler; Config-Durcheinander gelöst; B023-Bug behoben; Suite grün; mypy-Status geklärt (informativ); 5 untracked alte `pre_review_checks_*.log` bleiben uncommittet.
- `pyproject.toml` enthält jetzt: `[tool.pytest.ini_options]`, `[tool.ruff]` (line-length 120, target py314, exclusions für Archiv/simple_evals/tests/Legacy), `[tool.ruff.lint]` select/ignore/fixable (ignore: ANN401, B008, B011, S101, S311, PERF203, PERF401, FBT001, FBT002, FBT003, S310, S603, S607), `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.format]`, `[tool.pylint.main]`, `[tool.mypy]` (strict=true, exclude: simple_evals/, Archiv/, Doku-intern/, doc-git/, backups/, lm_eval_tasks/, human[-_]eval, ds1000_official/, ergebnisse/, runs/, logs/, tests/).
- `src/tools/gguf_full_metadata_reader.py` & `src/tools/lmeval_proxy.py`: `Optional[str]`/`Optional[bytes]`-Typen ergänzt (RUF013-Fix).

### Active
- **Todo 2 in Arbeit**: `validate --verbose` + `--repro` in `src/registry_tool.py` implementieren; `cmd_validate` (Z. 1656) angefangen zu lesen — Checks bisher: `template_missing_file`, `template_missing_config` (weitere folgen bis ~Z. 1830, Report folgt); Dispatch: `"validate": cmd_validate` (Z. 2123), Aufruf `elif cmd == "validate": cmd_validate()` (Z. 2268).

### Blocked
- (none)

## Next Move
1. `cmd_validate`-Funktion komplett lesen (Z. 1656–1830+), um Ergebnisstruktur (`errors`-Dict, exit/report-Logik) für `--verbose`-Detailausgabe und `--repro`-Artefakt zu verstehen.
2. Argument-Parsing/Dispatch um `--verbose`/`--repro` erweitern; `--repro` nutzt `hub/models/*/model.yaml` + `GGUFReader` (`src/tools/gguf_full_metadata_reader.py`) → schreibt `doc-git/Review-Artifacts/repro_issues.md`.
3. Danach: `pre_review_checks.ps1` v2 (Gate: validate→log, ruff→lint_issues.md, mypy informativ, pytest, `--repro`→repro_issues.md, CHANGELOG-Erinnerung; Fix `validation`→`validate`, toten gguf-Aufruf ersetzen, ohne `--config`).

## Relevant Files
- `src/registry_tool.py` — `cmd_validate` Z. 1656; Dispatch Z. 2123/2268; Re-Export-Fix in Import-Block (~Z. 100–115); TYPE_CHECKING für `RegistryEntry`.
- `pyproject.toml` (Root) — zentrale Tool-Config (ruff/mypy/pytest/pylint), Grundlage für Gate-Skript und CI-Fix.
- `pre_review_checks.ps1` — v2-Rewrite offen; bekannte Bugs (falscher Command-Name, toter `_check_gguf_ctx.py`).
- `src/custom_benchmark.py` — B023-Fix (~Z. 589–599), `_TaskProgress` (~Z. 1832–1870, Einrückungs-Fix enthalten).
- `src/run_benchmarks.py` — S506-noqa Z. 300; F821-noqas für `model_obj` (~Z. 1140–1150).
- `.github/workflows/review.yml` — weiterhin kaputt (Runner `Windows 11` ungültig → `windows-2025`, `pip install -e .` ohne `[project]`, fehlende Deps ruamel.yaml/psutil/gguf).
- `doc-git/Architecture, Flow & ChangeLog_en.md` — §20 „Version Changelog" (~Z. 1312) → CHANGELOG.md-Umzug offen.
- `src/tools/gguf_full_metadata_reader.py` — für `--repro` (Type-Fix enthalten).

==================== Compaction 06.08.2026 / 23:15 =======================
*OC:
## Objective
- Review-Gate-Tooling etablieren (abgeschlossen: Todos 1–3, Planung 18, BLACKLIST-Feinschliffe) und Dokumentation vereinheitlichen: neue deutsche Review-HowTo in `Doku-intern`, alle Publikations-Dokumente in `doc-git` vollständig auf Englisch umstellen (`Reviews/` bleibt ausdrücklich unangetastet).

## Important Details
- `doc-git/` = alles zur Veröffentlichung (GitHub); `Doku-intern/` = intern (deutsch).
- `Reviews/` NICHT anpassen (Nutzer-Entscheid). `Review-Artifacts/` wird als Publikations-Artefakt weiterhin übersetzt.
- F2LLM: gesamte Familie inkl. 14B bleibt geblacklistet (Embedding per HF-Cards, `Feature Extraction`); trotz „Reasoning"-Anzeige in LMS (Qwen3-Backbone + Chat-Template) — Nutzer bestätigt: „Passt schon!".
- Qwen3.5/3.6: Dual-Mode, Default Thinking (`enableThinking.defaultValue: true`); Punkt 18 abgeschlossen.
- GGUF = Source of Truth (unveränderlich); Registry editierbar; Hub-`model.yaml` nie anfassen; Mistral-Regelliste = Vorschlag.
- mypy nur informativ (195 Legacy); Commit-Stil `fix:`/`feat:`/`docs:`; CHANGELOG-Referenzen auf `main`.
- Übersetzungsregeln: Markdown-Struktur, Pfade, Modellnamen, Hashes, Zahlen, Datumsformate (TT.MM. behalten) NICHT ändern; Ablauf: HowTo → 3 große Dateien (parallel) → kleine Dateien → Code-Artefakt-Generierung → Umbenennungen → Verifikation/Commits.

## Work State
### Completed
- **Todo 3 abgeschlossen**: 3 Commits — `98e0700f` (CHANGELOG.md aus §20, §20 → kurzer Verweis, UTF-8 verifiziert via Python), `dec76d4d` (HowTo Windows-Backslash-Pfade, separater Commit), `ff8898f` (BLACKLIST: `text-embedding`/`granite-embedding` entfernt, Substring `embed` deckt ab; Konstanten an Dateianfang verschoben).
- `87e51863`: BLACKLIST-Kommentar `em_german` präzisiert (deckt `em_german_13b` + `em_german_leo_mistral` ab).
- `0061df90`: f2llm auf `f2llm-v2-1.7b`/`f2llm-v2-4b` präzisiert (14B erlaubt) — **widerrufen** durch:
- `e8de48c`: f2llm wieder generisch (HF-Cards belegen: gesamte Familie Embedding, inkl. 14B).
- **Planung 18 fertig** (`fc49787c`): `qwen/qwen3.5-9b` → `reasoning: thinking` + `max_context_length: 262144`; `assemble_blueprint.py:248-249`-Kommentar korrigiert; enable_thinking-Handling geprüft (kein Code-Change nötig); `validate --repro` = 0 Abweichungen, ruff 0, 741 Tests grün; Planung.md `[x]`, CHANGELOG-Eintrag ergänzt.
- **HowTo-Review-Gate_de.md** in `Doku-intern/` geschrieben (deutsch): 3 Säulen, 5 Check-Checks-Tabelle, Phase-2-Stichproben, ausführliche Prompt-Vorlage, Phasen/Regeln.
- **Parallel-Agenten (3 große Übersetzungen)**: `Temperature Recommondations.md` (244 Zeilen, vollständig englisch, verifiziert per Regex) ✓; `Planung.md` (53 Zeilen, englisch, Checkbox-Status erhalten, Dateiname bleibt) ✓; `Architecture, Flow & ChangeLog_en.md` — Agent lieferte 2× leeres Ergebnis, Datei NIE angefasst (git status unverändert) → **mache ich selbst, aktuell in Arbeit**.
- Front-Tabelle abgeschlossen: 105 Zeilen mit deutschen Treffern identifiziert via `lang_lines.py`; bisher übersetzt: Z.1, 77, Flow-Diagramm, §2.1a (Pre-Run-Checks komplett), §2.7-Sectionen (Reasoning-Quellen/Used-by, Qwen3-Familie, Registry-getriebenes enable_thinking, §2.11 YAML-Run-Spec komplett, §2.12 Seed-Durchgängigkeit, tool-eval-bench-CLI inkl. AGENTIC_SAFETY-Abschnitt, §3-Sektionen Struktur-Gate + main()/consolidate_results + _write_tbl, F5-Structured-Output-exclusions), Interne-Namen/Index-Tabelle `blueprint`/`truncation`/`custom_template`.
- `lang_scan.py` + `lang_lines.py` in `C:\Users\pskra\AppData\Local\Temp\opencode\` (UTF-8-Wrapper gegen Kodierungsprobleme; Mischtabelle der 124 Muttersprachen; Zeilen-Trefferliste als `%TEMP%\opencode\arch_lines.txt`).

### Active
- **Architecture-Datei in Arbeit (selbst, batch-edit)**: bisher ~24 Edit-Blöcke x4 Sprachen fertig; **offen der Rest aus `arch_lines.txt`**; aktueller Read-Punkt Z. 790–1033 (nach Edit 4); Z. 795, 799, 800–801, 820–850 (Struktur-Gate + consolidate_results + _write_tbl) fertig — **Rest der Treffer-Liste (Z. > 860, Details in `arch_lines.txt`) noch nicht übersetzt**.
- `Planung.md` und `Temperature Recommondations.md` sind uncommittet im Working Tree (git status: `M doc-git/Planung.md`, `M "doc-git/Temperature Recommondations.md"`).

### Blocked
- (none)

## Next Move
1. `doc-git/Architecture, Flow & ChangeLog_en.md` zu Ende übersetzen: Read-Reste (ab Z. 860/`arch_lines.txt`) + Zeilen außerhalb der Edit-Blöcke, dann lang_scan, Commits „docs: … englisch".
2. Kleine Dateien übersetzen: `A-B-Vergleich*` (2, 29+63 Treffer), `Modell Specific Hints/*` (x3 Dateien inkl. Ordnerumbenennung, 4 Dateien: GPT-OSS-Harmony/README, Qwen3.6-Fix, phi-4), `HowTo-Install-and-Configure-New-LLM_en.md` (19), `Model-Parameters-and-Benchmarks_en.md` (Check).
3. Code/Umbennungen: `registry_tool.py` `_write_repro_issues` + `pre_review_checks.ps1` GGUF-Check auf Englisch („kein"/„gefunden" vs. „none"/„found"), Artefakte neu generieren; `git mv` „Temperature Recommondations.md"→„..._en.md", „A-B-Vergleich …"→„A-B-Comparison …", Ordner „Modell Specific Hints"→„Model Specific Hints" (Code-Referenzen prüfen); `HowTo-Review-Gate_de.md` committen.
4. Finale Verifikation: lang_scan → 0 Mischungen (mit 3-Treffer-Schwelle), ruff, pytest (741), validate; Commits mit `docs:`.

## Relevant Files
- `Doku-intern/HowTo-Review-Gate_de.md` — neu, deutsch, committet noch nicht.
- `doc-git/Architecture, Flow & ChangeLog_en.md` — Übersetzung in Arbeit (noch ~Reste aus `arch_lines.txt`).
- `doc-git/Temperature Recommondations.md` + `doc-git/Planung.md` — übersetzt, uncommittet, Umbenennung nur für Temperature auf `_en` geplant (nicht Planung; Dateiname bleibt).
- `doc-git/A-B-Vergleich*` (2 Dateien) + `doc-git/Modell Specific Hints/` (4 .md) — kleine Übersetzungen offen.
- `src/benchmark_config.py` — BLACKLIST-Änderungen committet (`ff8898f`, `87e5186`, `e8de48c`); Referenzen auf „Modell Specific Hints" prüfen (Datei-Doku).
- `doc-git/Review-Artifacts/repro_issues.md` — bei Umstellung `registry_tool.py` neu generieren (deutsche Meldungen).
- `src/registry_tool.py` — `_write_repro_issues` (deutsche Strings: „kein", „gefunden", „Hub-Abweichungen") → auf Englisch.
- `pre_review_checks.ps1` — GGUF-Check-Abschnitt (deutsche Meldungen) → auf Englisch.

==================================================


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

=============== Compaction 19.08.2026 / 16:00 ================
## Objective
- (Completed) CI-/Review-Gates auf den aktuellen Provider-/Registry-Architekturstand synchronisieren.
- (Completed) Versionierte Git-Hooks fuer Pre-Commit, Commit-Msg und Pre-Push einfuehren und fuer dieses Arbeitsverzeichnis aktivieren.
- (Completed) Aenderungen zusammen mit ihrer Dokumentation committen und nach GitHub pushen.

## Important Details
- `core.hooksPath` ist lokal auf `.githooks` gesetzt; die Einstellung liegt in `.git/config` und wird von Git nicht automatisch mit einem Clone uebertragen. `.githooks/README.md` beschreibt die einmalige Aktivierung.
- Pre-Commit ist ein schneller staged-only-Sicherheitszaun. Pre-Push fuehrt das vollstaendige `pre_review_checks.ps1 -NoArtifacts` sowie fokussiertes mypy aus. CI bleibt eine unabhaengige zweite Kontrollinstanz.
- Registry-Validierung besitzt mit `validate --ci` einen echten headless Modus ohne LM-Studio-Konfigurationen, lokale Hub-Dateien oder lokale GGUF-Inventur.
- Die Laufzeitparameter und Modellquelle bleiben provider-neutral aus GGUF und `model_registry.yaml` abgeleitet; LM-Studio-JSON-Dateien sind keine globale Source of Truth.
- Der Readiness-Check war erfolgreich: **894 Tests bestanden**, Ruff und Compile-Pruefungen sauber, Workflow-YAML und PowerShell-Syntax gueltig, `validate --ci` ohne Probleme, fokussiertes mypy ohne Befunde. Bekannt bleiben die informative Vollbaum-mypy-Legacylast und die `pynvml`-Deprecation-Warnung.
- `.devin/wiki.json` ist ein versioniertes Devin/DeepWiki-Manifest. Es ist nicht das separate GitHub-Wiki-Repository (`<repo>.wiki.git`) und wird nicht durch einen normalen Push automatisch als GitHub-Wiki veroeffentlicht.
- Der erste Commit/Push (`8ca45d31`) lief erfolgreich. Eine anschliessende Pre-Commit-Pruefung zeigte eine nicht-blockierende Ruff-Argumentwarnung; der Hook wird deshalb in einem kleinen Folgecommit mit flacher Argumentliste und CI-kompatiblem Regelsatz korrigiert.

## Work State
### Completed / Active / Blocked
- Completed: Hook-Skripte, CI-/Review-Synchronisierung, headless Registry-Validierung, UTF-8-Erzwingung, Dokumentation und Tests.
- Active: den kleinen Ruff-Hook-Folgefix committen und pushen; vorbestehende untracked Dateien `utils/` sowie die beiden Server-Hilfe-Texte bleiben unangetastet.
- Blocked: keiner.

## Next Move
1. Beabsichtigte Dateien explizit stagen und den Commit durch die neuen Hooks laufen lassen.
2. `git push origin main` fuer den Folgefix ausfuehren; dabei den vollstaendigen Pre-Push-Gate erneut abwarten.
3. Push-Status und die Frage zur separaten GitHub-Wiki-Aktualisierung im Abschluss klaeren.

## Relevant Files
- `.githooks/`: versionierte lokale Gates.
- `.github/workflows/ci.yml`: CI-Test- und Typecheck-Gate.
- `.github/workflows/review.yml`: Review-/Registry-Gate.
- `pre_review_checks.ps1`: gemeinsames Pre-Review-Gate.
- `src/registry_tool.py`: headless Registry-Validierung.
- `AGENTS.md`, `doc-git/HowTo-Review-Gate_de.md`: dauerhafte Betriebsdokumentation.

=============== Compaction 20.08.2026 / 14:20 ================
## Objective
- (Current) Einen reproduzierbaren lokalen TabbyAPI-Start für Benchmarks mit der gemeinsamen ExLlamaV3-Umgebung herstellen.
- (Completed) Provider-Endpunkte trennen, das vorhandene kleine EXL3-Testmodell verwenden und den Ablauf verifizieren.

## Important Details
- **User intent:** TabbyAPI und exllamav3 sollen dieselbe virtuelle Umgebung verwenden; keine zweite Installation von Torch/Transformers/PyTorch.
- **Context:** Das Testmodell liegt unter `C:\Users\pskra\LLM-Modelle\Llama-3.2-1B-Instruct-exl3-4.0bpw`; `tabbyAPI\models` verweist per Junction auf diesen Modellordner.
- **Root cause:** Das alte `run-tabbyapi.ps1` startete keinen Server. `tabbyAPI\start.bat` verwendet außerdem standardmäßig `tabbyAPI\venv`, was die vereinheitlichte Umgebung verfehlt. Die bestehende TabbyAPI-Konfiguration enthielt zudem einen nicht vorhandenen Gemma-Modellnamen.
- **Decision:** Das neue Skript startet `tabbyAPI\start.py` direkt mit `exllamav3\exllamav3_env\Scripts\python.exe`, erzeugt eine temporäre Konfiguration ohne vorab geladenes Modell, wartet auf `127.0.0.1:5000` und lädt das Benchmarkmodell anschließend über die API.
- **Provider separation:** `LMSTUDIO_API_BASE`, `UNSLOTH_API_BASE`, `UNSLOTH_LOCAL_API_BASE` und `TABBYAPI_API_BASE` sind provider-spezifisch; `LLM_API_BASE` bleibt nur als Kompatibilitäts-Fallback. `LLM_PROVIDER` bleibt ein Prozess-Selector.

## Work State
### Completed / Active / Blocked
- Completed: Start-/Preflight-Skript, temporäre TabbyAPI-Konfiguration, provider-spezifische API-Aliase, README und Regressionstest.
- Verification: TabbyAPI `/v1/models`, Modell laden, Chat-Smoke und Entladen erfolgreich; 31 Provider-Architekturtests bestanden; Ruff und PowerShell-Parserprüfung sauber; Port 5000 nach Cleanup frei.
- Blocked: keiner.

## Next Move
1. Für Benchmarks `run-tabbyapi.ps1` verwenden und nicht `tabbyAPI\start.bat`.
2. Bei Bedarf getrennte LM-Studio-, Unsloth-GUI- und Unsloth-CLI-Smokes mit den dokumentierten Endpunkten durchführen.
3. Den im Screenshot sichtbaren `UNSLOTH_API_KEY` rotieren/revozieren.

## Relevant Files
- `run-tabbyapi.ps1`: Lokaler TabbyAPI-Start, Readiness-Prüfung, Benchmark-Aufruf und Cleanup; absichtlich unversioniertes lokales Hilfsskript.
- `src/model_manager.py`: Provider-spezifische API-Basisauflösung mit Rückwärtskompatibilität.
- `tests/test_provider_architecture.py`: Regressionstest für die neuen Endpunkt-Aliase.
- `README.md`: Bedienung und Provider-Endpunkte.

=============== Compaction 21.08.2026 / 01:06 ================
## Objective
- (Current) Eine belastbare Referenz vor der Security-Haertung herstellen, damit spaetere Score-Verluste der Allowlist/Worker-Haertung messbar sind.
- (Completed) Den ungueltigen DS1000-Baseline-Lauf diagnostiziert, die fehlende lokale Harness-Quelle ergaenzt und den korrigierten Lauf mit vier Modellen und SampleSize 30 abgeschlossen.

## Important Details
- **User intent:** Die Baseline darf vor der Security-Haertung liegen, aber keinen unabhaengigen DS1000-Ausgabe-/Ausfuehrungsfehler enthalten. Nullwerte oder fehlende Ergebniszeilen sind keine Referenz.
- **Root cause:** Im isolierten alten Baseline-Worktree fehlte `ds1000_official/execution.py`; der ungehaertete DS1000-Pfad scheiterte deshalb mit `ModuleNotFoundError: No module named 'execution'`.
- **Correction:** Die lokale `ds1000_official`-Quelle wurde per Junction in den Baseline-Worktree eingebunden. Die temporaere task-lokale Fehlerprotokollierung stellte zudem sicher, dass Fehlerzeilen erhalten bleiben; die Security-Haertung blieb fuer die Referenz ausgeschlossen.
- **Evidence:** Der korrigierte Lauf schrieb fuer jedes Modell 30 DS1000-Aufgaben ohne unerwartete Task-Fehler. Ergebnisse: Phi 4 66,7 %, Qwen3 Coder 66,7 %, Gemma 4 66,7 %, Granite 4.1 60,0 %. CoderEval: 75,0 %, 75,0 %, 66,7 %, 75,0 %.
- **Limitation:** Das lokale `simple_evals/codereval_selfcontained.jsonl` enthaelt nur 12 CoderEval-Aufgaben. `--sample-size 30` kann dort nicht mehr als 12 Aufgaben ausfuehren. Das ist eine Daten-/Benchmark-Grenze, kein Laufzeitfehler.
- **Decision:** DS1000-S30 ist jetzt die gueltige Vergleichsreferenz. CoderEval bleibt ein 12-Aufgaben-Kompatibilitaets-Smoke-Test; fuer eine groessere Coding-Stichprobe muss ein anderes lokales Set wie HumanEval+/MBPP+ verwendet oder der offizielle CoderEval-Datensatz samt Projektabhaengigkeiten ohne Docker adaptiert werden.

## Work State
### Completed / Active / Blocked
- Completed: Korrigierter Baseline-Lauf und Report `ergebnisse/baseline_security_compat_s30_20260820.md` aktualisiert; die acht Task-CSV-Artefakte und Modellzusammenfassungen liegen in `ergebnisse/`.
- Active: Weitere Hardening-Vergleiche muessen gegen genau diese korrigierte Referenz laufen.
- Blocked: Eine statistisch groessere CoderEval-S30-Referenz ist mit dem lokalen 12-Aufgaben-Datensatz nicht moeglich.

## Next Move
1. Fuer Security-Kompatibilitaet DS1000-S30 gegen die korrigierte Baseline vergleichen.
2. Fuer Coding-Scores ein groesseres, klar anders benanntes Referenzset ausfuehren oder zuerst den offiziellen CoderEval-Datensatz adaptieren.
3. Beim Vergleich Security-bedingte Ablehnungen (`os`, `re`, `textwrap`, `lxml`) getrennt von Modellfehlern ausweisen.

## Relevant Files
- `ergebnisse/baseline_security_compat_s30_20260820.md`: Korrigierter Baseline-Bericht und methodische Einschraenkungen.
- `src/custom_benchmark.py`: Task-lokale Fehler-/Traceback-Erfassung, die auch bei Ausfuehrungsfehlern Ergebniszeilen schreibt.
- `simple_evals/codereval_selfcontained.jsonl`: Lokale CoderEval-Quelle mit nur 12 Aufgaben.
- `ds1000_official/`: Benoetigte lokale Harness-Quelle fuer den ungehaerteten DS1000-Baseline-Pfad.

=============== Compaction 21.08.2026 / 15:05 ================
## Objective
- (Current) Die ausgewogene Baseline mit DS1000, HumanEval+ und MBPP+ fortsetzen und die EvalPlus-Auswertung unter Windows belastbar und beobachtbar machen.
- (Completed) Den scheinbar inaktiven Qwen-Lauf untersucht und den ersten fehlerhaften Thread-Parallelisierungsansatz ersetzt.

## Important Details
- **User intent:** Ein geladener LLM-Prozess ohne CPU-/GPU-Aktivitaet darf nicht als laufende Auswertung missverstanden werden; bei reiner Ergebnispruefung muss wenigstens der Evaluator nachvollziehbar arbeiten.
- **Root cause:** Der erste Parallelisierungsversuch rief EvalPlus aus ThreadPool-Threads auf, obwohl EvalPlus intern `multiprocessing.Process` verwendet. Unter Windows blieb der Parent praktisch untätig (ca. 2,89 CPU-Sekunden, keine Kindprozesse und keine neuen Ergebniszeilen).
- **Decision:** EvalPlus-Aufgaben werden nun aus dem Parent heraus als unabhaengige Python-Worker-Subprozesse gestartet. Dadurch werden Threads nicht mehr mit verschachteltem Multiprocessing kombiniert; vier Worker sind im Prozessbaum sichtbar.
- **Evidence:** Der aktuelle Qwen-HumanEval-Evaluator (PID 1624) hat vier Kinder `evalplus_task_worker.py`, startet aus vorhandenen 164 Modellantworten und erzeugt bisher weder Fehlerausgabe noch Fortschrittszeile. Das ist ein echter Prozessstart, aber noch kein abgeschlossener Task-Nachweis.
- **Tradeoff:** Die Worker vermeiden den Windows-Deadlock, verursachen aber pro Aufgabe Prozessstart- und Serialisierungskosten. CPU-Leerlauf zwischen einzelnen Aufgaben ist moeglich; dauerhaftes Leerlaufen ohne Workerwechsel waere weiterhin ein Fehlerbild.

## Work State
### Completed / Active / Blocked
- Completed: Worker-Modul und Parent-Delegation implementiert; fokussierte Tests (89) bestanden, Ruff und `py_compile` bestanden.
- Active: Qwen-HumanEval+-Auswertung mit vier Worker-Prozessen laeuft bzw. wird diagnostisch beobachtet.
- Blocked: Noch kein belastbarer Qwen-HumanEval-Score, solange keine Ergebniszeilen oder ein sauberer Abschluss vorliegen.

## Next Move
1. Worker- und Parent-Logs sowie Prozesswechsel beobachten; bei fehlendem Fortschritt einen einzelnen Worker-Payload direkt reproduzieren.
2. Nach erfolgreichem Abschluss das EvalPlus-Ergebnis ins Projekt-`ergebnisse` uebernehmen.
3. Danach Qwen-MBPP+ und die noch offenen Modelle abarbeiten; die LLM-Inferenz muss dafuer nicht erneut laufen, wenn die JSONL-Antworten vorhanden sind.

## Relevant Files
- `src/evalplus_subset_eval.py`: Startet pro EvalPlus-Aufgabe einen unabhaengigen Worker und protokolliert Fortschritt.
- `src/evalplus_task_worker.py`: Fuehrt genau eine EvalPlus-Aufgabe aus und liefert ein JSON-Ergebnis.
- `tests/test_run_benchmarks.py`: Testet die parallele Worker-Ausfuehrung.
- `ergebnisse/evalplus_humaneval_qwen_parallel.stdout.log`: Aktueller Qwen-Evaluator-Log.
- `ergebnisse/evalplus_humaneval_qwen_parallel.stderr.log`: Aktueller Fehlerlog.

=============== Compaction 18.09.2026 / 23:37 ================
## Objective
- (Current) Registry-Wartungsbefehle sollen die LM-Studio-JSON-Configs nicht verändern.
- (Completed) Die Ursache für verschwundene Systemprompts und KV-Cache-Werte wurde gefunden und im Code abgesichert.

## Important Details
- **Root cause:** `pipeline full` rief `assemble_prompts(preview_only=False)`, `cmd_patch_glm_configs()` und eine nicht-dry-run Missing-Quarantäne auf. Der Assembly-Schreibpfad schrieb komplette JSON-Dateien neu; fehlende `systemPrompt`-Felder wurden nicht ergänzt.
- **Decision:** `sync` bleibt Config-lesend. `pipeline full` verwendet nur noch Quarantäne-Dry-Run und Prompt-Preview und überspringt den GLM-Config-Patch. Explizite Assembly-/Patch-Kommandos bleiben bewusst schreibend.
- **Protection:** Beim expliziten Assembly werden vorhandene `load.fields` und unbekannte Felder erhalten; ein fehlendes `llm.prediction.systemPrompt` wird ergänzt. Siehe CHANGELOG.md, Abschnitt `LM-Studio-Config-Schreibschutz`.

## Work State
### Completed / Active / Blocked
- Completed: Read-only-Grenze für `pipeline full`, Systemprompt-Ergänzung, Regressionstests.
- Verification: 170 fokussierte Tests bestanden; Ruff für Produktivdateien und `py_compile` sauber.
- Active: Bereits veränderte LM-Studio-Configs, insbesondere `mistralai/ministral-3-14b-reasoning.json`, sind noch nicht rekonstruiert.
- Blocked: Keine belastbare Sicherung für jede beschädigte Config identifiziert.

## Next Move
1. Verlässliche Backups oder frühere Config-Inhalte für die Wiederherstellung auswählen.
2. Optional eine separate read-only Config-Differenzprüfung ergänzen.
3. Die alte schreibende Pipeline-Version nicht erneut ausführen.

## Relevant Files
- `src/registry_tool.py`: `pipeline full` nutzt Dry-Run/Preview und schreibt keine LM-Studio-Configs.
- `src/assemble_blueprint.py`: Explizites Assembly bewahrt Load-/Unbekannte Felder und ergänzt fehlende Systemprompts.
- `tests/test_registry_tool.py`: Regression für Config-Schreibschutz und Feld-Erhaltung.

=============== Compaction 19.09.2026 / 09:34 ================
## Objective
- (Current) Sampling-Recherche als einmaligen, reproduzierbaren Registry-Onboarding-Schritt ausführen; Benchmark-Läufe bleiben vollständig lokal.
- (Completed) Recherche, Statuspersistenz, Base-Model-Auflösung, begrenztes Hersteller-Crawling und manueller Codex-Review-Pfad umgesetzt.

## Important Details
- **Decision:** `registry_tool.py add/sync` recherchiert neue Modelle einmalig; `confirmed`, `unresolved`, `conflict` und `not_found` werden mit Zeitstempel, URLs und Evidenz gespeichert. Terminale Status werden bei späteren `sync`-Läufen übersprungen; `--refresh-sampling` ist der explizite Neuversuch.
- **Architecture:** Hugging-Face-Modellkarten werden über API-/`base_model`-Metadaten und alternative Repository-Namen aufgelöst. Offizielle Links werden nur über HTTPS, bekannte Domains und eine begrenzte Seiten-/Tiefenfrontier verfolgt.
- **Safety:** Sampling-Werte werden nur bei plausibler, profilbewusster und widerspruchsfreier Evidenz übernommen. LM-Studio-JSONs werden nicht geschrieben; die Registry wird nur über `registry_tool` aktualisiert.
- **Escalation:** `.codex/skills/registry-sampling-review/SKILL.md` unterstützt manuelle Prüfung ungelöster Fälle und schreibt nach Freigabe über `apply_sampling_review`, nicht direkt in YAML.
- **Evidence:** Live-Auflösung für Qwen3.6, Bonsai, Ministral und Darwin erfolgreich; Registry-Validierung meldete 0 blockierende Probleme.

## Work State
### Completed / Active / Blocked
- Completed: 933 Tests bestanden; 136 fokussierte Registry-/Sampling-/Config-Tests bestanden; Ruff, Format, Mypy-Scope und Skill-Validierung grün.
- Active: Die bestehende, nutzereigene `model_registry.yaml` wurde nach dieser Implementierung nicht durch einen produktiven `sync`-Lauf verändert.
- Blocked: Keine technische Blockade; der erste produktive `sync`-Lauf schreibt die einmaligen Recherche-Statuswerte in die Registry.

## Next Move
1. `py -3.12 .\src\registry_tool.py sync` einmalig für die aktuellen Modelle ausführen.
2. Für verbleibende `unresolved`/`conflict`-Einträge den Review-Skill verwenden.
3. `--refresh-sampling` nur bei bewusst gewünschter erneuter Web-Recherche einsetzen.

## Relevant Files
- `src/sampling_research.py`: API-/Base-Model-Auflösung, strukturierte Extraktion, Crawler und Evidenz.
- `src/registry_tool.py`: Einmal-Status, Refresh-Schalter, Validierung und manueller Schreibpfad.
- `src/benchmark_config.py`: Lokale Nutzung von Web-/manuell bestätigten Sampling-Profilen.
- `.codex/skills/registry-sampling-review/SKILL.md`: Manuelle Codex-Eskalation.
- `doc-git/Planung/registry_sampling.md`: Architektur- und Betriebsdokumentation. Siehe CHANGELOG-Eintrag `Registry Sampling Onboarding`.

=============== Compaction 19.09.2026 / 16:45 ================
## Objective
- (Current) Den abgeschlossenen Commit-/Hook-/Push-Vorgang zur dauerhaften Behebung des Windows-`WinError 5` bei pytest dokumentieren.
- (Completed) Isolierte pytest-Tempverzeichnisse in Hooks, Review-Gate und CI umgesetzt, geprüft, committed und nach `origin/main` gepusht. Siehe CHANGELOG-Eintrag `Pytest-Temp-Isolation für Hooks und CI`.

## Important Details
- **Root cause:** Das gemeinsam verwendete `.pytest-temp\\pytest-of-pskra` konnte unter Windows zwischen Läufen gesperrt oder unzugänglich werden; globale Temp-/Cache-Umleitungen verstärkten die Kollision.
- **Decision:** Jeder pytest-Lauf verwendet ein frisches OS-Tempverzeichnis; der pytest-Cacheprovider ist im Gate deaktiviert. `pre-push` führt die Suite isoliert vor dem übrigen Review-Gate aus; Registry- und LM-Studio-Config-Artefakte bleiben unangetastet.
- **Validation:** Commit-Hook und echter, nicht sandboxed ausgeführter Pre-Push liefen erfolgreich: 934 Tests, Registry 0 blockierende Probleme, Ruff/GGUF/fokussiertes Mypy erfolgreich. Der verbleibende Legacy-Mypy-Hinweis und zwei LM-Studio-`numParallelSessions`-Warnungen sind nicht blockierend.

## Work State
### Completed / Active / Blocked
- Completed: Commit `1cafcb014a9a8eb356dd0cd4bdd19e820666b228` ist auf `origin/main`; die übrigen nutzereigenen Worktree-Änderungen bleiben unberührt.
- Active: Keine offenen Arbeiten für diese Fehlerbehebung.
- Blocked: Keine technische Blockade; Legacy-Mypy und LM-Studio-Warnungen können separat behandelt werden.

## Next Move
1. Künftige Commits und Pushes normal über die versionierten Hooks ausführen, ohne `--no-verify`.
2. Den Legacy-Mypy-Fehler und die beiden LM-Studio-Warnungen nur bei Bedarf separat bereinigen.

## Relevant Files
- `.githooks/pre_push.ps1`, `pre_review_checks.ps1`: isolierter pytest-Aufruf und Gate-Ausführung.
- `.githooks/pre_commit.ps1`, `pyproject.toml`, `tests/conftest.py`: per-run Temp-Umgebung ohne geteilte Cache-/Temp-Umleitung.
- `.github/workflows/ci.yml`, `.github/workflows/review.yml`, `.gitignore`: CI-Dokumentation und Ignorieren generierter pytest-Artefakte.

=============== Compaction 19.09.2026 / 21:33 ================
## Objective
- (Current) README und Architektur-Dokumentation als verständliche Einstiegs- und Workflow-Dokumente strukturieren.
- (Completed) Datenhoheit, Modell-Onboarding, Registry-Pipeline und Benchmark-Ausführung aus Nutzersicht neu beschrieben.

## Important Details
- **Decision:** Die beiden zentralen PowerShell-Einstiegspunkte werden ausdrücklich getrennt: `registry_tool.py` bereitet Registry und Prompt-Policy vor; `run_benchmarks.py` führt die Benchmarks aus.
- **Pipeline distinction:** `status` ist read-only; `sync` pflegt die Registry; `pipeline sync` ergänzt Vergleich und Klassifikation; `pipeline full` ergänzt Preview und Validierung, schreibt aber keine LM-Studio-Config-JSONs.
- **Data model:** `publisher/model@quant`, Registry als Benchmark-SSOT, GGUF als technische Quelle und LM-Studio-JSONs als backend-lokale Runtime-Artefakte.

## Work State
### Completed / Active / Blocked
- Completed: README und `doc-git/Architecture, Flow & ChangeLog_en.md` vollständig auf Nutzerworkflow, Datenstruktur, Sampling-Onboarding, Provider, Ergebnisse und Prüfungen ausgerichtet.
- Verification: CLI-Hilfe für beide Programme, zentrale Dokumentbegriffe und `git diff --check` geprüft.
- Active: Dokumentationsänderung für fokussierten Commit vorbereitet.
- Blocked: Keine technische Blockade.

## Next Move
1. Nur die beiden Dokumente sowie diesen Compaction-/Changelog-Nachweis committen.
2. Pre-Commit- und Pre-Push-Hooks ausführen.
3. Nach erfolgreichem Push den Remote-Stand verifizieren.

## Relevant Files
- `README.md`: Einsteigerorientierter Setup-, Registry- und Benchmark-Workflow.
- `doc-git/Architecture, Flow & ChangeLog_en.md`: Datenhoheit, Kontrollfluss, Pipeline-Semantik und Architektur.
- `CHANGELOG.md`: Eintrag `User-facing Workflow Documentation` für diesen Vorgang.

=============== Compaction 19.09.2026 / 21:51 ================
## Objective
- (Completed) Den gesamten gemeinsam erarbeiteten Code-, Registry-, Test-, Hardening- und Dokumentationsstand committen und nach `origin/main` pushen.
- (Completed) Die Windows-Pytest-Temp-Isolation so korrigieren, dass Commit und Push künftig ohne `WinError 5` in der Pytest-Aufräumlogik laufen.

## Important Details
- **Scope:** 53 projektbezogene Dateien wurden in den Gesamtcommit aufgenommen, darunter Registry-/Blueprint-/Sampling-Code, Benchmark- und Sandbox-Code, Tests, Hardening-Vorschläge, Hooks, Review-Gate, README und Architektur-Dokumentation.
- **Excluded:** Lokale Backups, `.compat-baseline-20260828`, generierte Security-Scan-Ausgaben, lokale Konflikt-/Notizdateien und der ausdrücklich fremde `utils/`-Bestand blieben uncommitted.
- **Hook fix:** Pytest verwendet pro Lauf einen eindeutigen `--basetemp`-Pfad, lässt diesen von Pytest selbst erzeugen, verändert `TMP`/`TEMP` nicht und wird im Pre-Push-Hook direkt mit Python statt über `Start-Process` ausgeführt.
- **Gate policy:** Das Review-Gate verwendet für die erste Registry-Prüfung `validate --ci --repro`; lokale LM-Studio-Config-Drifts blockieren damit keinen Repository-Push. Der separate GGUF-Abgleich bleibt aktiv.

## Validation
- Commit-Hook: bestanden; Registry-Validierung 0 blockierende Probleme; fokussierte Registry-Tests 94/94.
- Pre-Push-Hook und tatsächlicher Push: 940 Tests bestanden, Ruff 0 Probleme, GGUF 0 Abweichungen bei 55 Einträgen, fokussierter mypy-Check bestanden.
- Nicht blockierend: ein `pynvml`-FutureWarning und zwei LM-Studio-`numParallelSessions`-Hinweise.

## Work State
### Completed / Active / Blocked
- Completed: Commit `158ce379` ist auf `origin/main`.
- Active: Der Arbeitsbaum enthält weiterhin bewusst nicht einbezogene lokale Artefakte/Notizen.
- Blocked: Keine technische Blockade für Commit oder Push.

## Next Move
1. Künftige Änderungen normal über `pre_commit.ps1` und `pre_push.ps1` prüfen lassen.
2. Die beiden advisory LM-Studio-Parallel-Session-Hinweise bei Bedarf separat untersuchen; keine Config-Dateien im Hook automatisch ändern.

## Relevant Files
- `.githooks/pre_commit.ps1`, `.githooks/pre_push.ps1`, `pre_review_checks.ps1`: stabile per-run Pytest-Basis und drift-tolerante CI-Registry-Prüfung.
- `src/registry_tool.py`, `src/sampling_research.py`, `doc-git/model_registry.yaml`: Registry-/Sampling-Onboarding und Policy.
- `src/task_manifest.py`, `src/evalplus_task_worker.py`, `tests/test_task_manifest.py`: neue Integritäts-/Worker-Pfade mit Tests.

=============== Compaction 20.09.2026 / 00:40 ================
## Objective
- (Completed) `custom_benchmark.py` von der veralteten `pynvml`-Wrapper-Abhängigkeit auf die NVIDIA-Bindings aus `nvidia-ml-py` umstellen und die Änderung verifizieren.

## Important Details
- **Package/import distinction:** Die Distribution heißt `nvidia-ml-py`, stellt ihre öffentliche Python-API aber weiterhin unter dem Modulnamen `pynvml` bereit. Deshalb verwendet der Code `import pynvml as _nvml`; ein Import `nvidia_ml_py` existiert nicht.
- **Environment cleanup:** Die zusätzlich installierte, veraltete Distribution `pynvml==13.0.1` wurde entfernt. `nvidia-ml-py==13.610.43` blieb installiert; dadurch verschwand die FutureWarning beim Import.
- **Regression protection:** Der Monitor-Test simuliert NVML-Initialisierung, GPU-Auslastung und VRAM-Auslesung über den `_nvml`-Binding-Punkt.

## Work State
### Completed / Active / Blocked
- Completed: Code, Entwicklungsabhängigkeit und fokussierter Test aktualisiert; Ruff und `pip check` bestanden.
- Verification: 96 fokussierte Tests und die vollständige Suite mit 941 Tests bestanden; direkter Smoke-Test meldet `nvmlInit = True` ohne FutureWarning.
- Active: Die drei Änderungen sind noch nicht committed.
- Blocked: Keine technische Blockade.

## Next Move
1. Bei Bedarf die drei geänderten Dateien gezielt committen.
2. Vor einem Push die normalen Commit-/Pre-Push-Hooks ausführen.

## Relevant Files
- `src/custom_benchmark.py`: NVML-Aufrufe über den `_nvml`-Alias und `nvidia-ml-py`-Dokumentation.
- `requirements-dev.txt`: explizite Abhängigkeit `nvidia-ml-py>=13.0`.
- `tests/test_custom_benchmark.py`: Regressionstest für die NVML-Bindings.
- `CHANGELOG.md`: Eintrag `NVIDIA NVML Binding Migration` für diese Änderung.

=============== Compaction 20.09.2026 / 16:00 ================
## Objective
- (Completed) Den bereinigten Gesamtstand des Benchmarks-Repositories committen und nach `origin/main` pushen.
- (Completed) Sicherstellen, dass künftig nur bewusst ausgeschlossene lokale Artefakte außerhalb des Repository-Scopes verbleiben.

## Important Details
- **Reconciliation:** Die zuvor getrennt zurückgehaltenen Änderungen wurden nach ausdrücklicher Nutzerfreigabe in einem gemeinsamen Commit zusammengeführt. Darin enthalten sind Registry-/Sampling-Logik, Benchmark-Code, GGUF-Root-Auflösung, Dokumentation, Tests und `src/model_paths.py`.
- **Generated artifacts:** `.compat-baseline-*`, `hardening/`, `model-list.txt`, lokale llama-server-Hilfe und `utils/` wurden nicht gelöscht, sondern in `.gitignore` aufgenommen.
- **Registry SSOT:** Nachgestellte Leerzeichen in der Registry-Evidenz wurden entfernt; die Registry-Validierung blieb semantisch fehlerfrei. Veraltete Tests wurden an aktuelle Sampling-/Reasoning-Werte und die entfernte crucible-labs-Variante angepasst.
- **Hook environment:** Die Windows-Pytest-Aufräumfehler (`WinError 5`) lagen am systemweiten Temp-Pfad. Commit und Push liefen mit einem kontrollierten repository-eigenen Temp-Bereich und ohne `--no-verify`.

## Work State
### Completed / Active / Blocked
- Completed: Commit `499fe85e4fd1902a5f173f713455bc04c0376302` ist auf `origin/main`; Arbeitsbaum sauber.
- Verification: Commit-Hook bestanden; fokussierter Umfang `284 passed`; vollständige Suite `980 passed`; Registry `0` blockierende Probleme; Ruff `0` Probleme; GGUF-Abgleich `54` Einträge ohne Abweichung; fokussierter mypy-Check bestanden.
- Advisory: Zwei bestehende LM-Studio-Hinweise zu `numParallelSessions != 4` bleiben separat zu bewerten.
- Blocked: Keine technische Blockade.

## Next Move
1. Künftige Änderungen normal über die versionierten Commit-/Push-Hooks prüfen und vollständig committen.
2. Die beiden nicht-blockierenden LM-Studio-Config-Hinweise nur bei Bedarf separat untersuchen; keine automatische Änderung an lokalen Runtime-Konfigurationen vornehmen.

## Relevant Files
- `.gitignore`: Lokale, regenerierbare Analyse- und Hilfsartefakte aus dem Versionsumfang ausgeschlossen.
- `src/model_paths.py`, `src/local_model_resolver.py`, `src/registry_tool.py`: Konfigurierbare GGUF-Suche und Registry-/Pipeline-Anpassungen.
- `src/sampling_research.py`, `doc-git/model_registry.yaml`: Kategoriebezogene Sampling-Evidenz und Registry-SSOT.
- `README.md`, `doc-git/Architecture, Flow & ChangeLog_en.md`, `PLANUNG.md`: Datenfluss-, Architektur- und Planungsdokumentation.
- `CHANGELOG.md`: Eintrag `Worktree Reconciliation and GitHub Push` für diesen Vorgang.

=============== Compaction 20.09.2026 / 21:09 ================
## Objective
- (Completed) Granite-Sampling-Evidence generationssicher recherchieren und redundante Registry-Evidence nachhaltig durch Producer-Logik straffen.
- (Completed) Den Refresh mit `pipeline full --refresh-sampling` ausführen und Registry, Tests und Validierung prüfen.

## Important Details
- **Generation boundary:** IBM-Granite-4.0- und 4.1-Modelle verwenden keine Granite-4.2-Quellen mehr. Granite 4.0 und 4.1-30B bleiben bei fehlendem vollständigem Herstellerprofil `unresolved`; Granite 4.2 bleibt mit seiner eigenen Empfehlung bestätigt.
- **Evidence structure:** Direkte Profile speichern ein gemeinsames `values`-Mapping mit URL/Excerpt; abgeleitete Profile speichern nur `derived_from`. Terminale Recherchequellen sind auf acht priorisierte URLs begrenzt.
- **Inventory drift:** Während der Pipeline änderte sich der LM-Studio-Bestand. Zwei K2-Horizon-Modelle wurden deshalb automatisch als aktuelle Registry-Einträge aufgenommen. Die Quarantäne blieb Dry-Run.

## Work State
### Completed / Active / Blocked
- Completed: 76 Registry-Einträge, 369 Evidence-Einträge, keine alten `field`/`value`-Evidence-Einträge, maximal acht Sampling-Quellen pro Modell.
- Verification: 114 fokussierte Tests bestanden; Ruff bestanden; `validate --ci` mit 0 Problemen; Prompt-Assembly 91/91 bestanden; `git diff --check` bestanden.
- Active: Änderungen sind noch nicht committed oder gepusht.
- Blocked: `pipeline full` meldet weiterhin 43 lokale Config-Context-Drifts, fünf fehlende Config-Zuordnungen und eine fehlende Techhermit-Template-Config; diese sind nicht Teil der Sampling-Korrektur.

## Next Move
1. Vor einem Commit den Gesamt-Diff prüfen und die bereits vorhandenen Dokumentationsänderungen bewusst vom Sampling-Scope abgrenzen oder gemeinsam freigeben.
2. Danach die versionierten Commit-/Push-Hooks ausführen.

## Relevant Files
- `src/sampling_research.py`: generationstreue Granite-Quellen, kompakte Evidence und begrenzte terminale Quellenlisten.
- `tests/test_sampling_research.py`: Tests für kompakte Evidence, Granite-Generationstrennung und Quellenbegrenzung.
- `doc-git/model_registry.yaml`: durch den Refresh erzeugte Sampling- und aktuelle Inventardaten.
- `doc-git/Temperature Recommondations_en.md`: Dokumentation des neuen Evidence-Schemas.
- `CHANGELOG.md`: Eintrag `Generation-Safe Sampling Evidence` für diese Änderung.

=============== Compaction 21.09.2026 / 01:33 ================
## Objective
- (Completed) Registry-/Config-Abgleich für die aktuelle LM-Studio-Modellmenge korrigieren und die neue enge Schreibvariante `sync-from-configs --write-context` dokumentieren.
- (Completed) Quarantänisierte LM-Studio-JSONs aus aktiver Config-Erkennung und `validate` ausschließen.

## Important Details
- **Context import:** `--write-context` schreibt ausschließlich `context_length` in `model_registry.yaml`; Offload, UKV sowie K-/V-Cache bleiben unverändert. Passende erhaltene Configs werden auch dann berücksichtigt, wenn sie nicht mehr im aktuellen LMS-Inventar stehen.
- **Quarantine boundary:** `quarantine-missing` bleibt ein ausdrücklich auszuführender Bereinigungsbefehl. `pipeline full` führt nur den Dry-Run aus, weil die echte Variante Configs verschiebt und Registry-Einträge entfernt. `read_lms_configs()` überspringt jetzt direkte `_quarantine_*`-Verzeichnisse.
- **Identity/matching:** QAT/NVFP4-Namen werden symmetrisch erkannt; `q8_0_i`, BF16-Formatmarker, zusammengesetzte Quantmarker und unbekannte Quant-Platzhalter sind durch Regressionstests abgesichert. DFlash-Dateien gelten als Zusatzdateien.
- **Registry cleanup:** Muse Glimmer ist als `@nvfp4` klassifiziert; der falsche Muse-`@q4_0`-Eintrag sowie stale Nerdsking- und F2LLM-Einträge wurden entfernt.

## Work State
### Completed / Active / Blocked
- Completed: Dokumentation in README, Architektur-/Workflow-Doku, CHANGELOG und `registry_tool.py --help` aktualisiert; Markdown-Tabellen geprüft.
- Verification: Fokussierte Assemble-/Registry-Suite `187 passed`; Ruff für geänderten Code und Test bestanden; neuer `validate --verbose` prüft keine Quarantäne-Configs mehr.
- Active: Arbeitsbaum enthält zusätzlich bereits vorhandene Änderungen und ist nicht committed oder gepusht.
- Open: Ein verbleibender Context-Drift betrifft eine nicht quarantänisierte `peculiar-ragdoll/tiel-coder-35b-a3b@iq3_xxs`-Config; er ist unabhängig von der Quarantänefilterung.

## Next Move
1. Bei Bedarf `quarantine-missing --dry-run` für den verbleibenden alten Modellbestand prüfen.
2. Erst nach Scope-Abgrenzung den gewünschten Gesamtstand gezielt testen, über `.githooks/pre_commit.ps1` committen und mit `.githooks/pre_push.ps1` pushen.

## Relevant Files
- `src/assemble_blueprint.py`: Quarantänefilter und symmetrisches Config-/Registry-Matching.
- `src/registry_tool.py`: `--write-context`, Registry-Synchronisierung und Dry-Run-Quarantäne in `pipeline full`.
- `tests/test_assemble_blueprint.py`, `tests/test_registry_tool.py`: Regressionen für Quarantänefilterung, Matching und Config-Sync.
- `README.md`, `doc-git/Architecture, Flow & ChangeLog_en.md`, `CHANGELOG.md`: Benutzer- und Workflow-Dokumentation.

=============== Compaction 21.09.2026 / 12:05 ================
## Objective
- (Completed) Translate the `--help` documentation of `assemble_blueprint.py` and `registry_tool.py` into English.
- (Completed) Audit directly executable Python scripts for missing or inadequate help output.

## Important Details
- **Help language:** Both user-facing help texts are now consistently English, including the distinction between `pipeline full` preview behavior and the explicit write command `assemble_blueprint.py assemble`.
- **Regression coverage:** Help assertions in the focused tests were updated to the English wording. The `fix-ctx` behavior and the earlier help requirements remain covered.
- **CLI audit:** Core entry points already provide argparse help. `evalplus_subset_eval.py`, `gguf_full_metadata_reader.py`, and `parallel_ab.py` have sparse or mixed-language help. `correlation_export.py` is directly executable but has no safe `--help` path and should be treated as the next candidate for a focused CLI documentation change.
- **Internal workers:** `evalplus_task_worker.py` and `sandbox_worker.py` use stdin/JSON protocols and are not normal user-facing command-line entry points.

## Work State
### Completed / Active / Blocked
- Completed: English help text, updated regression assertions, direct help smoke checks.
- Verification: 189 focused tests passed; Ruff, Python compilation, and `git diff --check` passed.
- Active: Worktree remains uncommitted and contains other pre-existing user changes; only the scoped files were modified in this step.
- Blocked: Nothing.

## Next Move
1. If desired, improve the three mixed-language/sparse help texts and add a guarded help path to `correlation_export.py`.
2. Before any commit, inspect the complete staged diff and run the repository hooks as required.

## Relevant Files
- `src/assemble_blueprint.py`: English module help and explicit prompt-assembly write-path explanation.
- `src/registry_tool.py`: Completely restructured English workflow, ownership, pipeline, command, and technical help.
- `tests/test_assemble_blueprint.py`: English help assertions.
- `tests/test_registry_tool.py`: English help assertions and `fix-ctx` regression coverage.
- `CHANGELOG.md`: Corresponding entry `English CLI Help and Entry-Point Audit`.

=============== Compaction 21.09.2026 / 20:56 ================
## Objective
- (Completed) GLM Structured-Output-Befunde mit der offiziellen LM-Studio-Dokumentation abgleichen.
- (Completed) Die direkte llama.cpp-Migration um den Reasoning-Format-Vorbehalt ergänzen.
- (Active) Den leeren finalen Inhalt des normalen Unsloth-GLM-4.7-Flash-Laufs weiter diagnostizieren.

## Important Details
- **LM Studio contract:** Die offizielle Dokumentation beschreibt für `/v1/chat/completions` JSON Schema als Structured-Output-Vertrag und nennt `choices[0].message.content` als JSON-String. Für GGUF wird llama.cpp Grammar-Sampling verwendet.
- **API evidence:** Der lokale LM-Studio-Endpunkt lehnt `response_format: {"type":"json_object"}` mit HTTP 400 ab: `response_format.type` muss `json_schema` oder `text` sein. Die Z.AI-Empfehlung `json_object` wird daher nicht in den LM-Studio-Runner übernommen.
- **Unresolved GLM result:** Der normale Unsloth-GLM-4.7-Flash-DS1000-Lauf war nicht trunciert, schrieb aber keinen finalen Inhalt in die CSV; REAP zeigte zusätzlich Budget-/Reasoning-Probleme. Vor weiterer Extraktion müssen rohe `message`-Felder einschließlich `content`, `reasoning_content`, `tool_calls` und `finish_reason` gesichert werden.
- **Migration decision:** `llama-cli --reasoning-format` (`auto`, `none`, `deepseek`, `deepseek-legacy`) ist ein separater llama.cpp-Providerparameter. Vor der Übernahme in `run_benchmarks.py` sind CLI und Server sowie Streaming und Nicht-Streaming per A/B-Smoke zu vergleichen.
- **GUI boundary:** LM Studios „llama.cpp Arguments Override“ bleibt ein Tuning-/Diagnosewerkzeug. Die Werte sind keine automatische Registry-Policy und beweisen keine identischen Defaults der separaten llama.cpp-Installation.

## Work State
### Completed / Active / Blocked
- Completed: GLM-Dokumentation in `doc-git/Model Specific Hints/` sowie den internen `Doku-intern/Modellspezifisches/GLM (Z.AI)`-Notizen ergänzt; `PLANUNG.md` und `CHANGELOG.md` aktualisiert; `git diff --check` ohne inhaltliche Fehler.
- Active: Mehrere Code-, Registry-, Test- und Dokumentationsänderungen liegen uncommittet im Worktree; vorhandene fremde Änderungen insbesondere in `src/model_manager.py` und `src/run_benchmarks.py` bleiben erhalten.
- Blocked: Keine technische Blockade, aber der GLM-Leerinhalt ist noch nicht behoben; ein vorschneller Wechsel von `json_schema` zu `json_object` wäre durch die LM-Studio-API widerlegt.

## Next Move
1. Den vollständigen Rohantwortpfad im LM-Studio-Client diagnostisch sichtbar machen, ohne die bestehende `json_schema`-Anfrage zu ändern.
2. Einen kleinen normalen GLM-4.7-Flash-Smoke mit derselben Prompt-/Schema-Kombination und vollständiger `message`-Aufzeichnung durchführen.
3. Danach `llama-server.exe`/`llama-cli.exe` mit `--reasoning-format` testen und erst dann den direkten Provider implementieren.
4. Vor Commit/Push Scope, staged Diff und die verpflichtenden `.githooks` prüfen.

## Relevant Files
- `doc-git/Model Specific Hints/GLM 4.5 - 4.7_Structured Output_en.md`: LM-Studio-`json_schema`-Vertrag, lokale 400-Antwort und llama.cpp-Migrationshinweis.
- `Doku-intern/Modellspezifisches/GLM (Z.AI)/`: interne GLM-Befunde, Familiengrenzen, API- und `--reasoning-format`-Hinweise.
- `PLANUNG.md`: neue A/B- und Provider-Aufgaben für `--reasoning-format` und GUI-Override-Abgrenzung.
- `src/custom_benchmark.py`: aktueller API-/Extraktionspfad; möglicher nächster Diagnosepunkt für rohe `message`-Felder.
- `CHANGELOG.md`: Eintrag `GLM Structured Output and llama.cpp Reasoning Boundary` für diese Compaction.

=============== Compaction 21.09.2026 / 22:05 ================
## Objective
- (Completed) Die llama.cpp-Migration als detaillierte, dokumentierte Hybridarchitektur planen.
- (Completed) Die drei lokalen `llama.exe`-Fundstellen prüfen und die eindeutig identifizierte Vulkan-Installation entfernen.
- (Active) Vor der Implementierung die Registry-/Preset-Schnittstelle und den GLM-Testabschluss vorbereiten.

## Important Details
- **Architecture decision:** `model_registry.yaml` bleibt die fachliche Quelle für Modellidentität, GGUF-/Architekturmetadaten, Blacklists, Blueprints, Sampling je Benchmarkkategorie, Provenienz und Validierungsstatus. llama.cpp-Argumente sowie optionale `preset.ini`-Dateien werden daraus generiert und nicht parallel manuell gepflegt.
- **Preset boundary:** Die aktuelle llama.cpp-Dokumentation beschreibt `preset.ini` als Runtime-/Routerkonfiguration. Für den geplanten Einzelprozess pro Modell sind explizite Startargumente beziehungsweise ein generiertes Argumentmanifest zunächst deterministischer; `--models-preset` wird separat als Routeroption geprüft.
- **Installation cleanup:** Das WinGet-Paket `ggml.llamacpp` wurde als `llama-b11046-bin-win-vulkan-x64.zip` identifiziert und mit `winget uninstall --id ggml.llamacpp --exact --silent` entfernt. Der Pfad unter `C:\Program Files\llama.cpp` mit `ggml-cuda.dll`, Build 10964, bleibt Produktionspfad.
- **Remaining llama.exe:** `C:\Users\pskra\AppData\Local\Microsoft\WindowsApps\llama.exe` bleibt vorerst unfreigegeben, weil es eine separate GUI/CLI-Bündelung Build 11046 ist und Backend/Lifecycle noch nicht unabhängig belegt sind. Der Provider soll nie von PATH-Reihenfolge abhängen.
- **Technical nuance:** Vulkan kann grundsätzlich NVIDIA-Hardware über den Vulkan-Treiber nutzen, ist aber nicht der für dieses Projekt gewünschte CUDA-Backendpfad. Deshalb wurde die Vulkan-Distribution entfernt, ohne die WindowsApps-Installation ungeprüft zu löschen.

## Work State
### Completed / Active / Blocked
- Completed: Migrationsphasen A–E, Verantwortungsmatrix, Exportstrategie, Installations-/PATH-Policy und Abnahmekriterien in `PLANUNG.md` ergänzt; CHANGELOG aktualisiert; WinGet-Vulkan-Paket entfernt; `where.exe llama.exe` zeigt nur noch WindowsApps und Program Files.
- Active: Der SampleSize-5-Lauf bleibt unvollständig; GLM-Rohantwortdiagnose, Providerimplementierung und Exportpfad sind offen. Der Worktree enthält weiterhin uncommittete Code-, Registry-, Test- und Dokumentationsänderungen.
- Blocked: Nichts technisch blockiert. Vor einer Umsetzung müssen die offenen GLM-Befunde und die konkrete Entscheidung „Einzelprozess-Argumentmanifest versus Router-Preset“ als Testspezifikation festgelegt werden.

## Next Move
1. GLM-Rohantwortpfad mit SampleSize 1 instrumentieren und den normalen Flash-/REAP-Unterschied sichern.
2. Einen kleinen `registry_tool.py`-Exportentwurf für ein Modell erstellen, ohne Runner-Code zu ändern.
3. Mit dem CUDA-`llama-server.exe` einen Einzelmodell-Lifecycle-Smoke inklusive Reasoning-Format, JSON-Schema und Logs durchführen.
4. Danach Providergrenze und Exportvertrag implementieren; erst anschließend den fehlenden SampleSize-5-Lauf auf dem neuen Backend starten.
5. Vor Commit/Push Scope, staged Diff und die verpflichtenden Hooks prüfen.

## Relevant Files
- `PLANUNG.md`: Hybridarchitektur, Installationsbereinigung, PATH-Policy, Migrationsphasen und Abnahmekriterien.
- `CHANGELOG.md`: Eintrag `llama.cpp-Preset-Grenze und Vulkan-Installation bereinigt`.
- `src/providers/`: Zielort für den neuen direkten llama.cpp-Provider; noch nicht implementiert.
- `doc-git/model_registry.yaml`: fachliche Registry-Quelle, nicht durch eine Runtime-INI zu ersetzen.

=============== Compaction 21.09.2026 / direct llama.cpp provider ================
## Objective
- (Completed) Die erste produktive Provider-Schnittstelle für direkte llama.cpp-
  Benchmarks implementieren, ohne den pausierten LM-Studio-SampleSize-5-Lauf
  fortzusetzen.
- (Completed) Start, Readiness, OpenAI-kompatible Inferenz, Modellauflistung und
  Stop über `C:\Program Files\llama.cpp\llama-server.exe` integrieren.
- (Active) Vollständige Pipeline-Smokes und der spätere Mehrmodelllauf bleiben
  nach der Backend-Integration offen.

## Important Details
- `LLM_PROVIDER=llama_cpp` bzw. `run_benchmarks.py --provider llama_cpp`
  aktiviert `src/providers/llama_cpp_provider.py`. Standardmäßig wird die
  CUDA-Binary unter `C:\Program Files\llama.cpp\llama-server.exe` verwendet;
  PATH und die WindowsApps-GUI werden nicht verwendet.
- `LLAMA_CPP_SERVER_EXE`, `LLAMA_CPP_API_BASE`, `LLAMA_CPP_MODEL_ROOT`,
  `LLAMA_CPP_LOG_DIR`, `LLAMA_CPP_REASONING_FORMAT` und
  `LLAMA_CPP_MAX_PARALLEL` sind explizite Providerkonfigurationen. Der Provider
  beendet ausschließlich den Prozess, den er selbst gestartet hat; ein fremder
  Server auf dem Zielport wird als Konflikt gemeldet.
- `model_registry.yaml` bleibt die fachliche Quelle. `context_length`, K-/V-
  Cache, Unified KV, Jinja, GPU-Layer, Batch-/Reasoning-Werte und
  `--reasoning-format` werden provider-spezifisch zu llama.cpp-Argumenten
  abgeleitet. Die Pipelines beziehen den Endpoint dynamisch über
  `get_api_base()`; `API_BASE` bleibt nur als Kompatibilitätsalias bestehen.
- Der lokale Resolver erkennt jetzt auch Root-level-Hugging-Face-Snapshots im
  Schema `models--publisher--model/snapshots/<revision>/*.gguf`.
- Echter CUDA-Server-Smoke am 21.09.2026 mit dem lokalen
  `gpt-oss-20b-MXFP4.gguf` war erfolgreich: Provider-Start, Modellladung,
  `/health`, `/v1/models`, Chat-Completions und kontrolliertes Stoppen. Log:
  `ergebnisse/llama-cpp-smoke-20260921/llama-server_ggml-org_gpt-oss-20b-GGUF_mxfp4.log`.

## Work State
### Completed / Active / Blocked
- Completed: Provider, Registry-Runtime-Mapping, Runner-Provideroptionen,
  Snapshot-Resolver, Provider-/Registry-/Runner-Regressionen, Registry-
  Validierung und echter Server-Smoke.
- Verification: Ruff und 142 fokussierte Tests bestanden; Registry
  `validate --ci` meldet 0 blockierende Probleme und 0 Hinweise.
- Known unrelated/pre-existing failure: vollständige Suite 1004/1005 grün;
  `tests/test_benchmark_config.py::TestRegistryBackedSampling::test_per_category_row_glm_4_7`
  erwartet noch Temperatur `1.0`, während die bereits geänderte GLM-Registry
  `0.7` liefert.
- Blocked: Nichts technisch blockiert. Der eigentliche Benchmarklauf wird auf
  ausdrückliche Fortsetzung nach dem Backend-Abschluss verschoben.

## Next Move
1. Mit einem festen Registry-Modell je Pipeline einen SampleSize-1-Smoke auf
   llama.cpp ausführen und stdout/stderr/Serverlog getrennt archivieren.
2. GLM-4.7 mit `auto`, `none`, `deepseek` und `deepseek-legacy` sowie Streaming
   und Nicht-Streaming vergleichen.
3. `llama-bench.exe` als technischen Preflight ergänzen und danach den
   sequenziellen Mehrmodell-Benchmarklauf starten.
4. Erst danach den pausierten LM-Studio-Lauf bzw. eine Vergleichsmessung
   wieder aufnehmen.

=============== Compaction 21.09.2026 / llama.cpp smoke and GGUF cache layout ================
## Ergebnis
- Der technische `llama-bench.exe`-Preflight mit
  `thebloke/em_german_leo_mistral@q4_k_m` ist abgeschlossen. Build 11081
  meldete CUDA und die RTX 5060 Ti mit 16 283 MiB VRAM.
- Der direkte Provider-Smoke mit SampleSize 1 wurde für DS1000, HumanEval+,
  ARC-Challenge und Agentic abgeschlossen. Die vier Pipelines erreichten den
  Server über `127.0.0.1:18080`, erhielten Antworten und wurden kontrolliert
  beendet. Die Einzelscores waren 0; daraus wird keine Qualitätsaussage
  abgeleitet.
- Die geforderten Laufdateien liegen getrennt unter
  `ergebnisse/llama-cpp-pipeline-smoke-20260921/`: Runner-stdout/stderr,
  llama-bench-Ausgaben und llama-server-Log.

## GGUF-Ablagebefund
- Der Resolver erkennt normale Publisher-/Modellordner sowie den in der
  llama-GUI verwendeten HF-Cache `models--publisher--model/snapshots/<revision>`
  direkt aus den vorhandenen `*.gguf`-Dateien.
- Die GUI muss ein Verzeichnis nicht anzeigen; der direkte Provider benötigt
  nur den aufgelösten lokalen Dateipfad und nutzt keine Router-Autodownloads.
- Das getestete gpt-oss-20b-Modell war zum Laufbeginn noch über die GUI als
  `unloaded` registriert. Es wurde nicht vom Benchmarkprovider geladen.

## Offene Befunde
- llama.cpp protokollierte wiederholt `Failed to initialize samplers` und
  `Unexpected empty grammar stack after accepting piece` für Structured Output.
  Die Testpipelines konnten danach normale Antworten verarbeiten. Vor GLM-
  Tests muss der Structured-Output-Vertrag pro Modell/Template geklärt werden.
- Der sequenzielle Mehrmodelllauf und der GLM-Reasoning-Format-A/B-Test sind
  weiterhin offen.

=============== Compaction 22.09.2026 / Structured Output and preset verification ===============
## Ergebnis
- Der llama.cpp-Structured-Outputpfad ist providerabhängig korrigiert. LM
  Studio verwendet weiterhin `json_schema`; llama.cpp erzwingt bei einer
  nicht expliziten Policy keine Grammatik, nutzt bei einem expliziten Profil
  `json_object` und deaktiviert Structured Output bei
  `reasoning-format=none`.
- Die fokussierten Tests für Registry, Provider, Resolver und Custom-Benchmark
  bestanden mit 299 Tests. `registry_tool.py validate --ci` meldete 0
  blockierende Probleme und 0 Hinweise. Die vollständige Ruff-Prüfung der
  betroffenen Testdatei meldet weiterhin bereits vorhandene Stilprobleme in
  `tests/test_registry_tool.py`; die geänderten Produktionsdateien sind sauber.
- GLM-4.7-Flash Q3_K_S wurde nicht gestreamt mit `auto`, `none`, `deepseek`
  und `deepseek-legacy` geprüft. Alle vier Läufe beendeten sich erfolgreich,
  ohne Grammar-/Samplerfehler; Taskstatus waren `json_ok`, `fenced`, `json_ok`,
  `json_ok`. `reasoning_format: deepseek` ist für die drei GLM-4.7-
  `deepseek2`-Registryeinträge gesetzt. GLM-4.6V bleibt getrennt.
- Ein sequenzieller direkter Lauf wechselte auf demselben Port zwischen
  `thebloke/em_german_leo_mistral@q4_k_m`,
  `unsloth/glm-4.7-flash@q3_k_s` und `qwen/qwen3-14b@q6_k`. Jeder Wechsel
  entlud das vorige Modell. Runner-stdout/stderr und drei Serverlogs liegen
  unter `ergebnisse/llama-cpp-multimodel-sequential-20260922/`.
- `registry_tool.py export-llama-preset` erzeugte unter
  `ergebnisse/llama-cpp-generated/preset.ini` 63 lokale Modellsektionen und
  meldete vier Einträge ohne lokale GGUF-Datei. Das Preset ist ein abgeleitetes
  Artefakt; `model_registry.yaml` bleibt die fachliche Quelle. Ein Router-Smoke
  mit `--models-preset` akzeptierte alle 63 Sektionen und listete sie über
  `/v1/models`, ohne ein Modell zu laden.

## Offene Punkte
- Der Streaming-Vergleich für GLM ist noch nicht durchgeführt; der produktive
  GLM-Benchmarkpfad bleibt bewusst nicht gestreamt.
- Ein separates llama.cpp-Argumentmanifest mit Registry-Hash, Build und
  Zeitstempel ist noch offen. Das generierte `preset.ini` ist der erste
  funktionale Exportpfad.
- Der pausierte SampleSize-5-Gesamtlauf wird erst nach Abschluss der Migration
  wieder aufgenommen.

=============== Compaction 22.09.2026 / 10:50 / config hierarchy and sampling aliases ================
## Objective
- (Current) Direkte llama.cpp-Migration mit reproduzierbarer Konfigurations-
  und Registry-Grenze fortführen.
- (Completed) Sampling-Alias-Erkennung, GLM-4.7-Policy, Preset-Merge und
  Umgebungsvariablen-Smoke dokumentiert und verifiziert.

## Important Details
- **Konfigurationsentscheidung:** Eine globale `config.ini` ist für getestete
  Hardware-Baselines sinnvoll. Die effektive Reihenfolge ist eingebaute
  Defaults, globale `config.ini`, `LLAMA_ARG_*`, Preset-`[*]`,
  modellbezogene Preset-Sektion und äußere CLI-Argumente. Die CLI gewinnt bei
  gleichnamigen Werten; Sampling und Request-Parameter bleiben pro Benchmark-
  Request steuerbar.
- **Pfadentscheidung:** Auf diesem System ist `%APPDATA%` gleich
  `C:\Users\pskra\AppData\Roaming`; die automatische globale Datei wäre
  `AppData\Roaming\llama.cpp\config.ini`. Das portable
  `C:\Users\pskra\.config\llama.cpp\preset.ini` bleibt ein explizit über
  `LLAMA_ARG_MODELS_PRESET` ausgewähltes Router-Preset. Die GUI-Logs unter
  `AppData\Local\Llama\logs` sind davon unabhängig.
- **Sampling:** `Terminal Bench`/`SWE-bench Verified` werden als Coding,
  `τ²-Bench` als Agentic erkannt. Nicht genannte Werte werden nicht erfunden;
  der Runner ergänzt nur Kategorie-Defaults. GLM-4.7 normal nutzt damit
  Coding/Math `0.7/1.0` und Agentic `temperature=0`.
- **Preset-Smoke:** `llama-server.exe` fand über die korrigierte
  Umgebungsvariable 65 Modelle einschließlich `gpt-oss-20b` und GLM-4.7.
  `mmap` wurde aus dem aktiven Preset entfernt, weil der aktuelle Router-
  Presetparser diesen Schlüssel ablehnt; die Sicherung liegt als
  `preset.ini.bak-20260922` vor.

## Work State
### Completed / Active / Blocked
- Completed: 160 fokussierte Tests, `validate --ci` ohne blockierende Probleme,
  Ruff für die geänderten Produktionspfade sauber.
- Active: direkte Provider-Migration und Konfigurationsmanifest weiterführen.
- Blocked/deferred: pausierter SampleSize-5-Lauf bleibt bis zum Abschluss der
  Backend-Migration zurückgestellt; GLM-REAP-Sampling bleibt wegen Quellenkonflikt
  separat ungeklärt.

## Next Move
1. Hardware-Baseline für `AppData\Roaming\llama.cpp\config.ini` festlegen,
   ohne modellabhängige Registrywerte zu duplizieren.
2. Direkten Provider gegen diese Hierarchie mit expliziten effektiven
   Startargumenten und Logs prüfen.
3. Danach SampleSize-5-Lauf und verbleibende GLM-/Streaming-Vergleiche planen.

## Relevant Files
- `src/sampling_research.py`: Benchmark-Aliase und partielle Samplingprofile.
- `src/benchmark_config.py`: Fallback für offiziell nicht angegebene Gegenwerte.
- `doc-git/model_registry.yaml`: bestätigte GLM-4.7-Basispolicy.
- `src/registry_tool.py`: llama.cpp-Preset-Export und idempotentes Merge.
- `PLANUNG.md`, `CHANGELOG.md`: Konfigurationshierarchie und Verifikation.

=============== Compaction 22.09.2026 / 12:00 / intermediate llama.cpp migration commit ================
## Objective
- (Current) Die direkte llama.cpp-Migration nach dem Zwischencommit mit den
  Provider-/Client-, Parametervertrags- und Verifikationspunkten fortführen.
- (Completed) Den bisherigen Registry-, Blueprint-, Provider-, Runner-, Test-
  und Dokumentationsstand als Commit `f5d37523` gesichert.

## Important Details
- **Produktionsbackend:** Ausschließlich `C:\Program Files\llama.cpp\llama-server.exe`;
  die gelöschte WindowsApps-Installation ist kein weiterer Prüfpfad.
- **Architektur:** `model_registry.yaml` bleibt fachliche Quelle; `config.ini`,
  Preset und Argumentmanifest sind abgeleitete bzw. allgemeine llama.cpp-
  Laufzeitkonfiguration.
- **Nächster Codeblock:** Globale `API_BASE`-Kompatibilität aus den normalen
  Runnerpfaden zurückdrängen, expliziten Provider-/Client-Kontext und
  capability-gesteuerte Parallelität für alle Pipelines durchsetzen.

## Work State
### Completed / Active / Blocked
- Completed: Zwischencommit mit bestandenem Pre-Commit-Hook, Registry-Validierung
  ohne blockierende Probleme und 101 fokussierten Registry-Tests.
- Active: Parametervertrag, Argumentmanifest und vollständige Providergrenze.
- Deferred: SampleSize-5-Gesamtlauf bis zur Migration; LM-Studio-Vergleich als
  separater Kompatibilitätstest.

## Next Move
1. Provider-/Client-Kontext und Capability-Grenze in Runner und Pipelines
   vervollständigen.
2. Registry-Runtime in validiertes llama.cpp-Argumentmanifest übersetzen.
3. Unit-, Contract- und echte CUDA-Smoke-Tests für die vier Pipelines ausführen.

## Relevant Files
- `src/run_benchmarks.py`, `src/model_manager.py`, `src/providers/base.py`: Providergrenze.
- `src/providers/llama_cpp_provider.py`: direkter Server-Lifecycle und Argumente.
- `src/registry_tool.py`, `src/model_registry.py`: Runtime-Export und Registryquelle.
- `PLANUNG.md`: Phasen A bis E und offene Abnahmepunkte.

=============== Compaction 22.09.2026 / 15:08 / Parallelitaet und llama.cpp Web-UI ================
## Objective
- (Current) Die direkte llama.cpp-Migration fachlich weiter schaerfen und die
  Parallelitaetsregel sowie die Rolle der integrierten Web-UI klaeren.
- (Completed) Unterschied zwischen Runner-Parallelitaet, llama-server-Slots,
  llama-cli und llama-server dokumentiert und die llama.cpp-Web-UI im Kontext
  des Benchmark-Projekts bewertet.

## Important Details
- **Parallelitaet:** Die Projektregel soll `SampleSize <= 5 -> num_parallel=1`
  und `SampleSize > 5 -> num_parallel=4` lauten. Der aktuelle Code verwendet
  noch `>= 10` als Schwelle und der llama.cpp-Provider meldet standardmaessig
  `max_parallel=1`; beides weicht von der beabsichtigten Policy ab.
- **Begriffe:** Runner-`num_parallel` steuert gleichzeitige Benchmark-Anfragen;
  llama.cpp-`--parallel` stellt Server-/KV-Cache-Slots bereit. Diese Werte sind
  verwandt, aber nicht identisch.
- **Web-UI:** PR #14839 ist in llama.cpp integriert. Die lokale Binary bietet
  UI-/WebUI-Optionen. Die UI ist ein geeignetes optionales Frontend fuer
  interaktive Modell- und API-Smoke-Tests, ersetzt aber weder Registry,
  `registry_tool.py`, `assemble_blueprint.py` noch die modellbezogenen GLM-,
  GPT-OSS- und Gemma-Regeln.
- **Benchmarkgrenze:** Automatisierte Laeufe sollen weiterhin mit expliziten
  Argumenten und moeglichst `--no-webui` erfolgen; Tools/MCP und Router-
  Automatik bleiben fuer reproduzierbare Laeufe deaktiviert.

## Work State
### Completed / Active / Blocked
- Completed: Migration points 1.A-C, 305 fokussierte Tests, Ruff-, Compile-,
  Registry- und llama-server-Hilfepruefungen.
- Active: Korrektur der Parallelitaets-Policy und Abgleich von Runner-
  Parallelitaet mit llama.cpp-Server-Slots.
- No code changes in this compaction turn; die aktuellen Migrationaenderungen
  befinden sich weiterhin uncommitted im Worktree.

## Next Move
1. `num_parallel` auf `<=5 -> 1`, sonst `4` korrigieren und die llama.cpp-
   Capability standardmaessig fuer vier Client-Anfragen freigeben.
2. Tests fuer SampleSizes 1, 5, 6 und groessere Laeufe sowie Provider-
   Begrenzungen ergaenzen; `--parallel`-Slotverhalten getrennt pruefen.
3. Optionalen llama.cpp-WebUI-Smoke-Test dokumentieren, ohne die UI in den
   automatisierten Benchmarkpfad zu verschieben.

## Relevant Files
- `src/run_benchmarks.py`: aktuelle Runner-Schwelle und Capability-Begrenzung.
- `src/providers/llama_cpp_provider.py`: aktuelle llama.cpp-Capability und
  Lifecycle-Grenze.
- `src/providers/llama_cpp_args.py`: explizites llama.cpp-`--parallel`.
- `tools/server/README.md`, `tools/server/README-dev.md`, `tools/ui/README.md`:
  upstreambezogene Einordnung der Server-/UI-Funktionen.

=============== Compaction 22.09.2026 / 13:00 / llama.cpp migration points 1.A-C ================
## Objective
- (Completed) Die Provider-/Runner-Grenze für den direkten llama.cpp-Pfad mit
  einem expliziten `ProviderContext` und Capability-basierter Parallelität
  vervollständigen.
- (Completed) Die Registry-Runtime zentral in llama.cpp-Startargumente und
  Request-Defaults übersetzen.
- (Completed) Die erledigten Architektur- und Exportpunkte in Planung, README,
  Architektur- und GLM-Dokumentation festhalten.

## Important Details
- Produktives Backend bleibt ausschließlich
  `C:\Program Files\llama.cpp\llama-server.exe`; die WindowsApps-Installation
  ist gelöscht und kein Fallback.
- `model_registry.yaml` bleibt die fachliche Quelle. `config.ini`, Router-
  `preset.ini` und `export-llama-args`-Manifest sind allgemeine bzw. abgeleitete
  llama.cpp-Laufzeitartefakte.
- Das Manifest enthält lokale GGUF-Auflösung, konkrete Startargumente,
  Sampling-/Reasoning-Defaults, Registry-SHA-256 und Servermetadaten.
- Der LM-Studio-Legacy-Pfad erhält frische Provider-Instanzen, damit die
  bestehenden REST-/Subprocess-Test-Seams funktionieren; der direkte Provider
  nutzt für seinen Lifecycle den stabilen Kontext-Client.

## Verification
- `py -3.12 -m pytest ...`: 305 fokussierte Tests bestanden.
- `py -3.12 -m ruff check` für alle geänderten Produktionsdateien: sauber.
- `py -3.12 src/registry_tool.py validate --ci`: 0 blockierende Probleme, 0 Hinweise.
- `llama-server.exe --version`: Build 11081, Commit `161755f29`; die Binary
  meldet `C:\Users\pskra\AppData\Roaming\llama.cpp\config.ini`.
- `llama-server.exe --help`: alle vom Argumentvertrag verwendeten Optionen
  wurden in der produktiven Binary gefunden.

## Work State
- Completed: Migration points 1.A-C at code/contract level.
- Deferred: fachlicher SampleSize-5-Gesamtlauf, LM-Studio/llama.cpp-
  Kompatibilitätsvergleich und separate Streaming-/Qualitätsbewertung.

=============== Compaction 22.09.2026 / 18:58 / Aktueller Migrationsstatus ================
## Objective
- (Current) Die direkte llama.cpp-Migration bis zur fachlichen Abnahme und zum
  reproduzierbaren SampleSize-5-Gesamtlauf weiterführen.
- (Completed) Den direkten Provider, Argument-/Preset-Export, GLM-
  Nicht-Streaming-Vergleich und sequenziellen Mehrmodell-Smoke verifiziert.
- (Completed) Millie als MoE-Hauptmodell mit separatem `mmproj`-Projektor
  korrekt in Inventarfilter und Registry eingeordnet.

## Important Details
- **Backend:** Produktiv bleibt ausschließlich
  `C:\Program Files\llama.cpp\llama-server.exe`; LM Studio dient nur zum
  Parameter-/VRAM-Tuning, Unsloth ist kein produktiver Lifecycle-Pfad.
- **Millie:** LM Studio benötigt für den Projektor die Namenskonvention
  `mmproj-...`. Der Projektor wird über alle Inventarfelder herausgefiltert;
  der Registry-Key des Hauptmodells ist `llmsforall/millie-35b-a3b-11gb@?`,
  mit `experts: 64` und `max_experts: 256`.
- **Registry:** `experts` ist der getestete Laufzeitwert, `max_experts` die
  unveränderliche GGUF-Obergrenze. `@?` ist ein zulässiger Platzhalter, wenn
  keine Quantisierung aus LM Studio/GGUF bestimmt werden kann.
- **Planungsabgleich:** Die Migration ist technisch weit fortgeschritten,
  aber `PLANUNG.md` enthält noch widersprüchliche Statusmarkierungen und den
  veralteten Kopfstatus `28.08.2026`.

## Work State
### Completed / Active / Blocked
- Completed: 233 fokussierte Tests, Ruff für die geänderten Produktionsdateien
  und `git diff --check` bestanden.
- Active: LM-Studio-/llama.cpp-Kompatibilitätsvergleich, GLM-Streaming-A/B,
  getrennte Fehler-/Warnungsanalyse und fachliche Qualitätsauswertung.
- Deferred: pausierter LM-Studio-SampleSize-5-Lauf; erst nach Backendabnahme
  den vollständigen direkten llama.cpp-Lauf starten.
- Open Registry: `mudler/gemma-4-26b-a4b-it-apex` benötigt einen getesteten
  Runtime-Expertwert und einen belastbaren Quantisierungssuffix.

## Next Move
1. `PLANUNG.md` mit dem tatsächlichen Status synchronisieren und die offenen
   Abnahmekriterien eindeutig markieren.
2. LM-Studio-/llama.cpp-Kompatibilität sowie GLM-Streaming reproduzierbar
   testen und Logs nach Ursache klassifizieren.
3. Task-Manifeste/Worker-Vergleichsläufe abschließen, danach den direkten
   SampleSize-5-Gesamtlauf und die Qualitätsbaseline dokumentieren.

## Relevant Files
- `PLANUNG.md`: Phasen, Abnahmekriterien und noch zu bereinigende Statusmarkierungen.
- `src/providers/llama_cpp_provider.py`, `src/run_benchmarks.py`: direkter Backendpfad.
- `src/benchmark_config.py`, `src/registry_tool.py`: Auxiliary-Filter und Registry-Import.
- `doc-git/model_registry.yaml`: Millie-Identität und MoE-Runtimewerte.
- `README.md`, `doc-git/Architecture, Flow & ChangeLog_en.md`: Backend- und Workflow-Doku.

============== Compaction 22.09.2026 / Commit checkpoint ==============
## Objective
- Den bis hierher angefallenen llama.cpp-Backend-, Registry-, Qualitätsauswertungs-
  und Dokumentationsstand sichern und lokal committen; kein Push.

## Important Details
- HEAD enthält bereits die Checkpoints `3eb964c4` (llama.cpp-Migration) und
  `f5d37523` (Backend-Grundlage). Die nachfolgenden Änderungen bauen fachlich
  auf diesem Projektstrang auf und umfassen Provider-/Runner-Anpassungen,
  Argumentauflösung, Registry- und Sampling-Regeln, Kompatibilitäts- und
  Qualitätswerkzeuge sowie zugehörige Tests und Dokumentation.
- Die jüngsten Registry-Korrekturen sind erledigt: Quant-Matching für
  `q2_g64`/`mini`, `@?` für nicht sicher quantisierte Millie, `@mini` für Gemma
  APEX, Import des live bestätigten `experts: 36` und erfolgreicher
  `validate --ci`-Lauf ohne Blocker oder Hinweise.
- Die aktuelle Help-Redaktion richtet die Erläuterungsspalten aus, entfernt die
  Sample-Size-Abkürzung und kennzeichnet `--refresh-sampling` als Websuche, die
  länger dauern kann.
- Vor Commit sind Compaction und CHANGELOG gemeinsam zu versionieren. Der
  Pre-Commit-Hook ist verpflichtend; ein Push ist ausdrücklich nicht Teil des
  Auftrags.

## Work State
### Completed / Active / Blocked
- Completed: fokussierte Tests für Registry-Help, Ruff für `registry_tool.py`,
  Python-Compile und Diff-Whitespace-Prüfung bestanden.
- Active: Änderungen aus dem laufenden Projektstrang sind ungestaged; die
  Änderungen umfassen 44 vorhandene oder neue Pfade und werden vor Commit als
  Gesamt-Diff geprüft.
- Deferred: kein Push; der pausierte SampleSize-5-Gesamtlauf bleibt pausiert.

## Next Move
1. Den vollständigen Diff und den Commit-Umfang prüfen, dann alle zum aktuellen
   Projektcheckpoint gehörenden Änderungen gezielt stagen.
2. `.githooks/pre_commit.ps1` und den normalen Commit-Hook erfolgreich
   ausführen; Commit erstellen, ohne Push.
3. Anschließend den neuen Commit-Hash und etwaige verbleibende Änderungen
   berichten.

## Relevant Files
- `CHANGELOG.md`: Kurzprotokoll der konkreten Änderungen; verweist auf diesen
  Compaction-Checkpoint.
- `PLANUNG.md`: aktueller Migrations- und Abnahmestatus.
- `src/`, `tests/`, `doc-git/`: zusammengehöriger Implementierungs-, Test- und
  Dokumentationsstand des aktuellen Checkpoints.

=============== Compaction 23.09.2026 / Commit checkpoint ================
## Objective
- Registry-Synchronisierung und direkter llama.cpp-Preset-Export als zusammenhängenden lokalen Checkpoint committen.
- Den Commit-Hook ausführen; kein Push.

## Important Details
- **Preset-Auflösung:** LM-Studios `model.yaml` kann auf ein anders benanntes GGUF-Repository zeigen. Der Export folgt dieser Zuordnung und prüft weiterhin die konkrete Quantisierung.
- **Datenbereinigung:** Veraltete Registry-Aliase wurden entfernt; unterschiedliche Qwen-Quantisierungen bleiben getrennte Einträge.
- **Verifikation:** Registry-CI ohne Blocker; fokussierte Registry-/Assembly-Tests bestanden. Die bestehenden mypy-Meldungen bleiben informativ und sind nicht Teil dieses Checkpoints.

## Work State
### Completed / Active / Blocked
- Completed: Code, Tests, Dokumentation und Registry-Daten sind geprüft und für den lokalen Commit vorbereitet.
- Active: staged Diff und Pre-Commit-Hook.
- Deferred: Push und der pausierte SampleSize-5-Gesamtlauf.

## Next Move
1. Staged-Diff auf Umfang, Whitespace und Secrets prüfen.
2. Commit mit dem normalen `.githooks`-Ablauf erstellen.
3. Commit-Hash und verbleibende Änderungen berichten; nicht pushen.

## Relevant Files
- `src/registry_tool.py`: Hub-Quellenauflösung für lokale GGUF-Dateien.
- `tests/test_registry_tool.py`: Regressionstest für den RNJ-1-Repository-Alias.
- `doc-git/model_registry.yaml`, `CHANGELOG.md`, `PLANUNG.md`: bereinigter und dokumentierter Projektstand.

=============== Compaction 23.09.2026 / Regression-Fix und Push ================
## Objective
- Die im vollständigen Testlauf gefundenen zehn Fehler und der Ruff-Befund
  wurden behoben und der aktuelle Arbeitsstand wird committed und gepusht.

## Important Details
- Die Tests erwarteten teilweise veraltete Modelle oder Samplingwerte. Sie
  verwenden jetzt die aktuelle Registry-SSOT: Granite 4.2, bestätigte bzw.
  bewusst nicht bestätigte Samplingprofile und den `@?`-Schlüssel für eine
  unbekannte Quantisierung.
- `llama_cpp` ist jetzt als Registry-Feld mit eigener Feldhoheitsregel erfasst;
  `max_experts` bleibt ein automatisch aus GGUF ableitbarer Architekturwert.
- Der globale `ModelRegistry`-Resolver wird im Provider-Test zurückgesetzt, damit
  Tests nicht voneinander abhängen.
- Pytest-Basisverzeichnisse der Review- und Pre-Push-Hooks liegen unter dem
  Windows-System-Temp und werden dort nach dem Lauf bereinigt. Dadurch wird der
  Repository-Arbeitsbaum nicht mehr durch Testordner belastet.

## Work State
### Completed / Active / Blocked
- Completed: 1.075 Pytest-Tests, Ruff, fokussierter mypy-Check,
  Registry-Validierung und PowerShell-Syntaxprüfung bestanden.
- Active: Commit und Push mit den verbindlichen Hooks.
- Blocked: kein bekannter technischer Blocker; eine separate Review-Verbindung
  wurde durch den vorherigen Turn-Abbruch nicht abgeschlossen.

## Next Move
1. Staged-Diff prüfen und Pre-Commit-Hook ausführen.
2. Commit erstellen und den Pre-Push-Hook mit vollständiger Testsuite ausführen.
3. Remote-Stand und Arbeitsbaum nach dem Push verifizieren.

## Relevant Files
- `src/field_owner.py`: Feldhoheit für `llama_cpp` ergänzt.
- `tests/`: veraltete Erwartungen und Testisolation korrigiert.
- `pre_review_checks.ps1`, `.githooks/pre_commit.ps1`, `.githooks/pre_push.ps1`: sichere Temp-Pfade.

=============== Compaction 23.09.2026 / Push abgeschlossen ================
## Objective
- Den Regression-Fix und die nachhaltige Windows-Temp-Pfad-Korrektur auf
  `origin/main` veröffentlichen.

## Work State
### Completed / Active / Blocked
- Completed: Commit `dc9070cb` erstellt und erfolgreich nach `origin/main`
  gepusht. Pre-Commit, vollständige Pytest-Suite, Registry-Validierung, Ruff,
  GGUF-Abgleich und fokussierter mypy-Check bestanden.
- Non-blocking: zwei vorhandene LM-Studio-Konfigurationen melden weiterhin
  `numParallelSessions=1` statt der Projektpolicy 4.
- Clean: Git-Arbeitsbaum und Remote-Branch sind synchron.

## Next Move
1. Die pausierten Benchmark-/Kompatibilitätsarbeiten fortsetzen.
2. Die beiden LM-Studio-Parallelitätswarnungen bei Gelegenheit fachlich prüfen.

## Relevant Files
- `dc9070cb`: Regressionstests, Feldhoheit und sichere Hook-Temp-Pfade.

=============== Compaction 24.09.2026 / 16:24 ================
## Objective
- Die GitHub-Actions-Abhängigkeiten `checkout` und `setup-python` sicher auf
  die gewünschten v7-Versionen aktualisieren und den Remote-Lauf verifizieren.

## Important Details
- **SHA-Pinning:** `actions/checkout` steht auf v7.0.1 mit Commit-SHA
  `3d3c42e5aac5ba805825da76410c181273ba90b1`; `actions/setup-python` auf
  v7.0.0 mit `5fda3b95a4ea91299a34e894583c3862153e4b97`. Dieselben exakten
  SHAs wurden der GitHub-Allowlist hinzugefügt; die SHA-Pflicht blieb aktiv.
- **Push-Zugang:** Der zuerst verwendete `GITHUB_TOKEN` hatte nicht den nötigen
  Workflow-Zugriff. Der erfolgreiche Push nutzte einmalig den vorhandenen
  `gh`-Credential-Helper, ohne gespeicherte Zugangsdaten oder Git-Konfiguration
  dauerhaft zu ändern.
- **Abnahme:** GitHub Actions liefen erfolgreich: CI `35978068448` und
  Pre-Review `35978068485`. Lokal bestanden 1.075 Tests, Registry-Validierung,
  Ruff, GGUF-Abgleich und der fokussierte mypy-Check.

## Work State
### Completed / Active / Blocked
- Completed: Commit `bc899e303f92109ec911986d29b6e26fc2056c6f`
  (`ci: upgrade GitHub Actions to v7 SHA pins`) ist auf `origin/main`.
- Completed: lokaler `main`-Branch und `origin/main` waren synchron; beide
  genannten GitHub-Läufe waren erfolgreich.
- Non-blocking: der globale mypy-Lauf meldete einen informativen Befund; zwei
  LM-Studio-Konfigurationen melden weiterhin `numParallelSessions` ungleich 4.
- Preserve: `AGENTS.md` hatte bei dieser Compaction bereits eine separate,
  uncommittete Nutzerkorrektur. Sie gehört nicht zum Actions-Upgrade und wird
  in diesem Commit ausgespart.

## Next Move
1. Bei der nächsten regulären Prüfung die zwei LM-Studio-Parallelitätsmeldungen
   fachlich einordnen.
2. Die pausierten Benchmark- und Backend-Kompatibilitätsarbeiten nach Priorität
   wieder aufnehmen.

## Relevant Files
- `.github/workflows/ci.yml`, `.github/workflows/review.yml`: aktualisierte
  Actions-Versionen und vollständige SHA-Verweise.
- `CHANGELOG.md`: Eintrag zum Upgrade mit Verweis auf diese Compaction.

=============== Compaction 24.09.2026 / 18:24 ================
## Objective
- Die in der letzten Chat-Antwort geplante Refaktorierung der Modellidentitaet,
  Pfad-/Artefaktaufloesung, Quantisierung, Parameterabbildung und
  Synchronisationsgrenzen stufenweise in den Phasen 0 bis 6 umsetzen und die
  Dokumentationsentscheidung fuer den llama.cpp-/Hugging-Face-Link aus Punkt 13
  abschliessen.

## Important Details
- **Phase 0/1 — Identity:** `resolve_registry_match()` liefert jetzt typed
  `UniqueMatch`, `AmbiguousMatch` oder `Unmatched`. Publisher-aware Exact-
  Matching kommt zuerst; publisherlose und Varianten-Fallbacks sind nur bei
  Eindeutigkeit zulaessig. `match_registry_key()` bleibt als kompatibler
  `key | None`-Adapter erhalten. Normalisierte exakte Kollisionen sind in
  `validate --ci` blockierend; eine publisherlose Qwen/ByteShape-Kollision
  bleibt als bewusst sichtbarer Hinweis bestehen.
- **Phase 2 — Inventory:** `InventorySnapshot` und `IdentityLink` in
  `src/inventory.py` bilden Registry, LM-Studio-Records, Configs und GGUF-
  Kandidaten als gemeinsamen Lauf-Snapshot ab. `registry_tool.py` behaelt den
  kompatiblen Laufzeitnamen `RegistryInventory`.
- **Phase 3 — Contracts:** `src/quantization.py` ist die gemeinsame
  Quantisierungsvokabel fuer Key-, Datei- und Config-Varianten.
  `src/parameter_bindings.py` beschreibt kanonische Registry-Felder und ihre
  LM-Studio-/llama.cpp-Namen; Provider-Adapter verwenden diese Tabelle.
- **Phase 4/5 — Artifacts and consumers:** `ArtifactResolver` in
  `src/artifact_resolver.py` zentralisiert GGUF-Discovery, Root-Prioritaet,
  Hub-Layout, Quantisierung und Ambiguitaetsbehandlung. Registry-Reader,
  Config-Sync, lokale Modellauflistung, Preset-/Runtime-Pfade und Display-
  Overrides verwenden unique-only Regeln; first-wins und fuzzy Runtime-
  Fallbacks wurden entfernt.
- **Phase 6 — Facade and documentation:** `registry_tool.py` bleibt als
  stabile CLI-Fassade bestehen; wiederverwendbare Grenzen liegen in fokussierten
  Modulen. `doc-git/Architecture, Flow & ChangeLog_en.md` verweist auf die
  offizielle [HuggingFace Model Card Metadata Interoperability
  Consideration](https://github.com/ggml-org/llama.cpp/wiki/HuggingFace-Model-Card-Metadata-Interoperability-Consideration).
  Die Entscheidung ist bewusst dort dokumentiert, weil der Link Metadaten-
  Interoperabilitaet beschreibt, nicht die vollstaendige Runtime-Parameter-
  Abbildung. `LOCAL-LLM-ENVIRONMENT.md` bleibt die zentrale Hardware-/Backend-
  Faktenquelle und wird nicht mit Projektarchitektur vermischt.
- **Data safety:** `doc-git/model_registry.yaml` und lokale LM-Studio-
  Artefakte wurden nicht automatisch umgeschrieben. Mehrdeutige Evidenz bleibt
  sichtbar und fail-closed.

## Verification
- `py -3.12 -m pytest -q`: **1.086 passed**.
- Fokussierte Identity-/Boundary-/Registry-Suite: **211 passed**.
- `py -3.12 -m ruff check .`: **passed**.
- `py -3.12 -m compileall -q src tests`: **passed**.
- `py -3.12 src\\registry_tool.py validate --ci`: **0 blocking problems,
  1 advisory publisherless ambiguity**.
- Isolierter MyPy-Check der neuen bzw. unmittelbar betroffenen Contract-
  Module: **passed**. Der projektweite `mypy src`-Lauf bleibt mit 110 bereits
  konzentrierten Legacy-/Bestandsfehlern in `custom_benchmark.py`,
  `run_benchmarks.py` und Teilen von `registry_tool.py` offen; dieser Turn
  erweitert diesen Befund nicht um Fehler in den neuen Contract-Modulen.
- Live-Tests mit LM Studio, llama-server/llama.cpp, echter GGUF-Ladung und
  externen Webquellen wurden wie vom Nutzer gewuenscht **nicht** ausgefuehrt.
- Kein Commit und kein Push.

## Work State
### Completed / Active / Blocked
- Completed: Phasen 0 bis 6, Regressionstests, Architektur-Dokumentation,
  offizieller Link, CHANGELOG-Eintrag und diese Compaction.
- Active: Arbeitsbaum enthaelt die fokussierten Refaktorierungs- und
  Dokumentationsaenderungen; vorhandene uncommittete Nutzerkorrekturen in
  `AGENTS.md` und der Architekturdatei bleiben erhalten.
- Deferred: Live-Backend-Tests sowie die nachgelagerte fachliche Klaerung des
  publisherlosen Qwen/ByteShape-Hinweises.

## Next Move
1. Live-Tests mit kontrollierten LM-Studio-/llama.cpp-Fixtures und echten
   Modellpfaden separat ausfuehren.
2. Den verbleibenden publisherlosen Qwen/ByteShape-Hinweis durch explizite
   Publisher-Identitaeten oder eine dokumentierte Aliasentscheidung bereinigen.
3. Erst danach Staging, Hooks, Commit und gegebenenfalls Push vorbereiten.

## Relevant Files
- `src/model_identity.py`, `src/artifact_resolver.py`, `src/inventory.py`:
  Identitaets-, Artefakt- und Lauf-Snapshot-Vertraege.
- `src/quantization.py`, `src/parameter_bindings.py`:
  zentrale Quant-/Parameter-Schnittstellen.
- `src/registry_tool.py`, `src/local_model_resolver.py`,
  `src/model_registry.py`, `src/run_benchmarks.py`:
  migrierte Consumers und CLI-Fassade.
- `docs/keystone/refactors/2026-09-24-model-identity-synchronization.md`:
  Phasenplan, Invarianten, Beweis- und Rollback-Regeln.
- `doc-git/Architecture, Flow & ChangeLog_en.md`, `CHANGELOG.md`:
  Architektur-/Interoperabilitaetsentscheidung und Aenderungsnachweis.

=============== Compaction 24.09.2026 / 19:41 ================
## Objective
- Den abgeschlossenen Identity-/Artifact-/Parameter-Refactor in einem
  nachvollziehbaren Commit sichern und nach erfolgreichem Pre-Push-Gate auf
  `origin/main` veroeffentlichen.

## Important Details
- **Commit scope:** `a1c34b17` (`refactor: harden model identity
  synchronization`) enthaelt die 24 fachlich zum Refactor gehoerenden Dateien,
  einschliesslich der neuen Contract-Module, Tests, Architektur-Dokumentation,
  CHANGELOG und der vorherigen Compaction.
- **Preserved user change:** Die bereits vor diesem Auftrag vorhandene,
  separate Korrektur in `AGENTS.md` bleibt bewusst uncommittet und wird nicht
  durch den Refactor-Commit vereinnahmt.
- **Pre-Commit:** Der Hook meldete alle staged Checks bestanden und fuehrte die
  fokussierte Registry-Suite mit 140 bestandenen Tests aus.
- **Next gate:** Der Push erfolgt ohne `--no-verify`; der konfigurierte
  `.githooks/pre-push`-Hook muss Review-Checks und den fokussierten MyPy-Scope
  erfolgreich abschliessen.

## Work State
### Completed / Active / Blocked
- Completed: Refactor-Commit erstellt und Pre-Commit-Gate bestanden.
- Active: Commit amendieren um diesen Checkpoint und anschliessend Push mit
  Pre-Push-Gate.
- Blocked: kein bekannter technischer Blocker.

## Next Move
1. Checkpoint-Dateien in den noch nicht veroeffentlichten Commit aufnehmen.
2. `git push` mit dem normalen Pre-Push-Hook ausfuehren.
3. Remote-Commit, Arbeitsbaum und den erhaltenen Hook-/Push-Status verifizieren.

## Relevant Files
- `CHANGELOG.md`: Verweis auf diesen Commit-/Push-Checkpoint.
- `COMPACTIONS.md`: Historischer Zustand unmittelbar vor dem Push.
- `AGENTS.md`: Bewusst erhaltene, nicht zum Refactor gehoerende lokale Aenderung.

=============== Compaction 24.09.2026 / 19:44 ================
## Objective
- Den abgeschlossenen Refactor einschliesslich Dokumentations- und
  Compaction-Nachweis veroeffentlichen.

## Important Details
- Commit `75820a10` (`refactor: harden model identity synchronization`) ist
  erfolgreich nach `origin/main` gepusht.
- Der verbindliche Pre-Push-Hook bestand mit der vollstaendigen isolierten
  Pytest-Suite (**1.086 passed**), `validate --ci` ohne Blocker, Ruff,
  GGUF-Abgleich mit 54 geprueften Eintraegen und fokussiertem MyPy fuer die
  relevanten Push-Dateien.
- Der Review-Gate meldete nur den bekannten publisherlosen
  Qwen/ByteShape-Hinweis sowie zwei nicht blockierende LM-Studio-Warnungen
  (`numParallelSessions=1` statt 4 bei Millie und Gemma).
- Die separate, bereits vor dem Auftrag vorhandene Korrektur in `AGENTS.md`
  bleibt lokal uncommittet und wurde nicht gepusht.

## Work State
### Completed / Active / Blocked
- Completed: Refactor, Commit, Pre-Commit, Pre-Push und Push nach `origin/main`.
- Active: kein weiterer Schritt aus dem aktuellen Auftrag.
- Blocked: kein technischer Blocker; Live-Backend-Tests bleiben bewusst vertagt.

## Next Move
1. In einem separaten Auftrag kontrollierte Live-Tests mit LM Studio und
   llama.cpp/`llama-server.exe` ausfuehren.
2. Den publisherlosen Qwen/ByteShape-Hinweis durch explizite Publisherwahl
   oder eine dokumentierte Aliasentscheidung bereinigen.
3. Die beiden LM-Studio-Parallelitaetswarnungen fachlich pruefen.

## Relevant Files
- `CHANGELOG.md`: Nachweis des erfolgreichen Pushes von `75820a10`.
- `COMPACTIONS.md`: dieser Nach-Push-Checkpoint.
- `AGENTS.md`: verbleibende lokale, nicht zum Auftrag gehoerende Aenderung.

=============== Compaction 24.09.2026 / 22:13 ================
## Objective
- Die Architektur-Dokumentation zur Modellidentitaet, lokalen GGUF-Evidenz,
  LM-Studio-JSON-Zuordnung und Bundle-Synchronisierung vervollstaendigen und
  den geprueften Arbeitsstand veroeffentlichen.

## Important Details
- **Datenvertrag:** `InventorySnapshot` ist der einmalige Read-Snapshot;
  `IdentityLink` verbindet Registry-Key, `ArtifactIdentityEvidence` und
  `RuntimeBinding`. LMS publisher/modelKey/selectedVariant bleiben transiente
  Join-Evidenz und werden nicht als redundante llama.cpp-Identitaet persistiert.
- **Abgleich:** Vollstaendiger GGUF-Pfad, Pfad-/Dateiname, Quantisierung und
  GGUF-Header bilden die physische Evidenz. `LLAMA_ARG_MODELS_DIR` hat die
  hoechste Root-Prioritaet. Null- oder Mehrfachtreffer, veraltete Pfade,
  wiederverwendete Configs und fehlende Companions bleiben fail-closed.
- **Bundles:** Integriertes MTP bleibt `type: mtp`/`mode: integrated`,
  separates MTP nutzt `companions.mtp`, vollwertige Draft-LLMs
  `companions.draft`; llama.cpp-Namen werden erst am Provider-Rand erzeugt.
- **Proof vor diesem Checkpoint:** Vollsuite `1117 passed`, Registry-CI ohne
  Blocker/Hinweise, Ruff fuer die geaenderten Produktionsmodule bestanden;
  fokussiertes MyPy fuer die neuen Contract-Grenzen bestanden. Die bekannten
  35 Legacy-Fehler in `registry_tool.py` bleiben dokumentierte technische
  Schuld und sind kein Grund fuer eine globale Typregel-Lockerung.

## Work State
### Completed / Active / Blocked
- Completed: Code-/Datenstruktur-Refactor, Architektur-Dokumentation,
  Changelog und diese Compaction.
- Active: staged Diff pruefen, Commit-Hook ausfuehren, danach Push-Hook und
  Remote-Stand verifizieren.
- Blocked: kein bekannter technischer Blocker; Live-Tests mit LM Studio und
  llama.cpp bleiben bewusst ausserhalb dieses Checkpoints.

## Next Move
1. Den vollstaendigen, fachlich zusammengehoerigen Arbeitsstand nach Diff-
   Pruefung committen.
2. Mit den normalen `.githooks/pre-push`-Pruefungen nach `origin/main` pushen.
3. Commit-SHA, Remote-SHA, Arbeitsbaum und Hook-Ergebnisse berichten.

## Relevant Files
- `doc-git/Architecture, Flow & ChangeLog_en.md`: erweiterter Daten- und
  Abgleichsvertrag.
- `src/inventory.py`, `src/registry_tool.py`, `src/model_identity.py`:
  Implementierung der Join-Grenzen.
- `CHANGELOG.md`: Verweis auf diesen Checkpoint.
- `COMPACTIONS.md`: dieser vor Commit/Push erzeugte Arbeitsstand.
