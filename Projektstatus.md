# Projektstatus Benchmarks

Stand: 2026-10-27 · Commit: `13f75c65`

## Context Survey brief

Question: Welche Struktur, Regeln, Datenflüsse und Veröffentlichungsrisiken hat das Benchmarks-Projekt, und welchen aktuellen Stand hat die Überarbeitung von Privatsphäre-, Testpfad-, Hook-, README- und Review-Gate-Ausgaben?

### Evidence inspected

- `$HOME\Python-Projekte\Benchmarks\README.md`, `AGENTS.md`, `pyproject.toml`, `PLANUNG.md`, `CHANGELOG.md`, `COMPACTIONS.md` und `REVIEW-GATE.md`: Projektzweck, SSOT-Regeln, Testpfade, Review- und Commit-Ablauf.
- `$HOME\Python-Projekte\Benchmarks\.github\workflows\ci.yml` und `review.yml`: CI-Jobs, Python-/Ruff-/mypy-Scopes, Privacy-Gate und Registry-Validierung.
- `$HOME\Python-Projekte\Benchmarks\.githooks\` und `pre_review_checks.ps1`: Pre-Commit-, Commit-Message-, Pre-Push- und manuelle Gate-Varianten.
- `$HOME\Python-Projekte\Benchmarks\src\` per Struktur-/AST-Inventar: Registry- und Benchmark-Einstiege, Provider-Grenzen, Sampling-, Template- und Runtime-Policy.
- `$HOME\Python-Projekte\Benchmarks\tests\`, `pytest/`, `docs/`, `data/blueprint_definitions.yaml` und die Review-Artefakte: Test-, Dokumentations- und Datenlage.
- Direkte lokale Prüfungen: `git status/log/diff`, `ruff check`, `pytest`, fokussierter mypy-Scope, `registry_tool.py validate --ci`, Review-Gate sowie Privacy-/Secret-Scans über getrackte und gestagte Dateien.

Source-Quality: Die Projektdateien, Konfigurationen, Hooks, Tests und erzeugten Gate-Artefakte sind primäre lokale Belege mit hoher Aussagekraft.
`PLANUNG.md`, `CHANGELOG.md` und `COMPACTIONS.md` sind selbst dokumentierte Statusquellen und teilweise historisch. Externe Recherche war für den aktuellen Änderungsumfang nicht erforderlich.

### Findings

- Fact: Das Projekt hat zwei Haupt-Einstiege, `src/registry_tool.py` für Registry-/Prompt-Pflege und `src/run_benchmarks.py` für Ausführung;
    vier Pipelines laufen über einen Provider-/Lifecycle-Boundary und schreiben Ergebnisse nach `ergebnisse/`.
- Fact: `data/model_registry.yaml` bleibt eine maschinenlokale, ignorierte SSOT mit lokalen Pfaden. Sie wurde für den lokalen Gate-Zweck direkt um `experts: 36` ergänzt und
    ist durch ein lokal ignoriertes Backup geschützt; `validate --ci` meldet jetzt 0 Blocker und 4 Hinweise.
- Fact: Der Sync-Defekt ist offen dokumentiert: LM Studio und die JSON-Config enthalten `numExperts=36`, aber der dokumentierte `sync-from-configs`-/`sync --import-lms-settings`-Pfad
    übernimmt den Wert nicht zuverlässig. Der Punkt steht in `PLANUNG.md`.
- Fact: Konkrete Windows-Profilpfade wurden in 15 getrackten Textdateien durch `$HOME` ersetzt; nicht-pfadbezogene Beispielkontaktdaten wurden durch synthetische Platzhalter ersetzt.
    Der Post-Commit-Scan über 231 getrackte Dateien meldet 0 Profilpfade, 0 verbotene E-Mail-Domains, 0 Secret-Muster und 0 rohe Vorkommen des lokalen Benutzernamens.
- Fact: `README.md` nennt `D:\LLM-Modelle\Llama-GGUF` als primären GGUF-Root. `pyproject.toml` sammelt `tests/` und `pytest/`, schließt `pytest/artifacts/` aus der Rekursion aus;
    die bestehende Suite bleibt in `tests/`, neue Testquellen liegen unter `pytest/`.
- Fact: Hook- und Review-Gate-Dokumentation beschreibt nun den tatsächlichen Pre-Push-Ablauf: vollständige pytest-Suite, danach `pre_review_checks.ps1` mit `-SkipPytest`, `-NoArtifacts`,
    `-NoTranscript` und anschließendem fokussiertem mypy-Scope.
- Fact: Die Review-Artefakte wurden am 27.10.2026 neu erzeugt. Der vollständige Gate ist grün: 1.685 Tests bestanden, 6 übersprungen; Ruff 0 Probleme;
    GGUF-Abgleich 0 Abweichungen; fokussierter mypy-Scope 0 Probleme. Vollbaum-mypy bleibt mit 41 Fehlern informativ.
- Fact: Der Pre-Commit-Hook lief vor `13f75c65` erfolgreich und führte 192 fokussierte Registry-Tests aus. Es wurde kein Push ausgeführt.
- Fact: Die beiden ungetrackten Artificial-Analysis-Snapshots sind `data/arificial-analysis-models_20261003.json` (200 Datensätze, Free-Tier, Index v4.3) und
    `data/artificial-analysis-free-snapshot-20261010.json` (697 Datensätze, Abruf-Metadaten vom 10.10.2026).
- Interpretation: Der stärkste lokale Schutz ist die Kombination aus Privacy-Gate, vollständigem Review-Gate, unabhängigem CI und dem fokussierten mypy-Scope.
    `--no-verify` bleibt nur ein dokumentierter Notfallweg.

### Assumptions / unknowns

- Ungetrackte neue Dateien wurden gemäß der Klärung nicht in `13f75c65` aufgenommen; dazu gehören die neuen `pytest/`-Quellen, neue `src/`-Module, neue Docs, Chat-Template-Cache und JSON-Snapshots.
    Sie benötigen bei gewünschter Veröffentlichung einen separaten, erneut geprüften Commit.
- Das rohe `data/model_registry.yaml` bleibt lokal und unveröffentlicht, weil es absolute lokale Bindungen enthält.
    Für eine spätere Veröffentlichung wäre ein portable/local-Split oder eine bereinigte CI-Fassung sicherer als ein roher Commit.
- Der MoE-Sync-Fehler ist nicht behoben, nur durch den lokalen Registry-Wert und die Planungsnotiz überbrückt.
- Remote-CI nach `13f75c65` wurde nicht abgefragt; der lokale Hook und das lokale Gate sind die bisherigen Nachweise.
- Die beratenden LM-Studio-`numParallelSessions`-Warnungen und die vier publisherlosen Registry-Hinweise bleiben offen, blockieren den aktuellen Gate aber nicht.

### Options or implications

- Lint-Scope: Empfohlen ist, die CI-/Hook-Override-Flags `--select E,F --ignore E501,F401,E402` zu entfernen und überall `pyproject.toml` als gemeinsame Quelle zu nutzen;
    der volle Ruff-Scope ist nach der Skriptbereinigung grün. Alternative: Scopes weiter trennen, dann aber ausdrücklich als bewusste lokale/CI-Unterschiede dokumentieren.
- Registry-Veröffentlichung: Aktuelle und empfohlene Variante ist „ignoriert und lokal“. Für echte CI-Daten wäre eine getrennte, bereinigte portable Registry-Fassung mit lokalem Overlay vorzuziehen;
    das rohe Registry-File nicht direkt publizieren.
- Hook-Varianten: manuelles Voll-Gate vor Review liefert persistente Artefakte, ist aber langsam; Pre-Commit ist schnell, aber nur staged/teilweise;
    Pre-Push kombiniert vollständige pytest-, Gate- und mypy-Prüfungen und ist der stärkste lokale Blocker; CI ist unabhängig, aber ohne lokale GGUF-/LM-Studio-Bindungen;
    `--no-verify` umgeht Schutzebenen und ist nur für dokumentierte Notfälle geeignet.
- Offene Sync-Arbeit: Zuerst die Config-/Inventur-Zuordnung und den Importpfad für MoE-`numExperts` untersuchen, bevor erneut automatisierte Registry-Synchronisation verwendet wird.

### Confidence

High für Struktur, Konfiguration, Hook-/CI-Abläufe, Privacy-Scans und aktuelle lokale Gate-Ergebnisse, weil sie direkt aus Dateien, Git und ausführbaren lokalen Prüfungen stammen.
Medium für die Selbstdokumentation in Planungs-/Chronikdateien und für das noch nicht ausgeführte Remote-CI-Verhalten nach dem Commit.

### Recommended next step

none für diesen Context-Survey.
Für später getrennt: `implementation` für den MoE-Sync-Fehler oder `project-audit`/`change-review`, wenn der Lint-Scope oder die Registry-Veröffentlichungspolitik festgelegt werden soll.

### Registry und Planung
- Der lokale, ignorierte data/model_registry.yaml enthält nun für den betroffenen MoE-Eintrag experts: 36.
- Ein lokales, ignoriertes Backup wurde vor der Änderung erzeugt.
- validate --ci ist danach ohne Blocker.
- Der Sync-Defekt ist als aktuell offener Punkt in $HOME\Python-Projekte\Benchmarks\PLANUNG.md dokumentiert:
    Die JSON-Config enthält den Wert, aber der dokumentierte Import-/Sync-Pfad übernimmt ihn nicht zuverlässig.

## Projektstatus
Der angeforderte Context-Survey-Brief mit dem aktuellen Stand der Überarbeitungen steht in:

`$HOME\Python-Projekte\Benchmarks\Projektstatus.md`

Die Datei ist lokal und bewusst noch ungetrackt.
**Ebenfalls ungetrackt bleiben die neuen pytest/-Testquellen, neuen src/-Module, neuen Docs, Chat-Template-Dateien und JSON-Snapshots, entsprechend dem vereinbarten Commit-Umfang „getrackt, aber nicht committet“.

Die Lint-Scope-Empfehlung und die Hook-Varianten als Entscheidungsvorlage sind in Projektstatus.md enthalten; der CI-/Hook-Override wurde nicht stillschweigend verändert.


### Checkpoint

Keystone checkpoint: context-survey -> none
Completed: Änderungen umgesetzt; Registry lokal ergänzt; Review-Artefakte aktualisiert; vollständiges Gate und Pre-Commit bestanden; Commit `13f75c65` erstellt; Privacy-/Secret-Scans ohne Befund.
Blocked by: none
Next check: none
Action: stop
Todo tail: Next / upcoming task: none — sequence complete


---

## Update 2026-11-11: lms-Auflösung, np=3, No-Op-Push-Fix

Der Abschnitt oben ist der Context-Survey zum Stand `13f75c65` (27.10.2026) und bleibt unverändert. Aktueller Stand:

- **Commit (in Vorbereitung):** `src/registry_tool.py` löst `lms.exe` explizit auf (App-CLI, `$HOME\.lmstudio\bin`, llmster-Bundles, PATH zuletzt) statt über den PATH; Benchmark-Parallelität bei SampleSize > 5 ist 3 statt 4 Worker (vierter Slot für den permission-guard-Reviewer, `_NP_POLICY` bleibt 4); `src/privacy_gate.py` blockiert bei leerem pre-push-stdin (No-Op-Push) nicht mehr; Tests und np-Erwartungen (`src/field_owner.py`, `pre_review_checks.ps1`, `docs/Developer-Docs/LM-Studio-API-References.md`) auf 3 angepasst; neu `tests/test_lms_resolution.py` (3 Tests).
- **VERIFY:** `ruff check . --no-fix` 0 Befunde; `python -m pytest -q` 1686 bestanden, 8 übersprungen.
- **Offen:** `.gitignore` (M) und `.gitattributes` (untracked) bleiben uncommitted; das .gitignore-Diff nimmt `data/model_registry.yaml` aus der Ignore-Liste (die Registry bleibt trotzdem uncommitted; Policy-Entscheidung offen). Die 4 Hinweise `publisherless_identity_ambiguity` und der fehlende Linux-Job in der CI-Matrix bleiben bewusst offen.
- **Nachbarprojekt:** Die llama.cpp-Serie (b12242) in Inspect-Evals ist fertig (8 Modelle, 0 Fehler); `mathvista` läuft nur bei Modellen mit mmproj, deshalb haben rnj-1 und Falcon3-10B je 7 Tasks. Konsolidierung folgt.
