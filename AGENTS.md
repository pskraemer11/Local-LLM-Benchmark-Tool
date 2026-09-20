# AGENTS.md - Kontext für Agenten – Benchmarks-Projekt

**Cover what matters**
 - Project overview
 - Build and test commands
 - Code style guidelines
 - Testing instructions
 - Security considerations

## Umgebung
**Betriebssystem:** Windows 11 Home (win32). Kein POSIX/UNIX.
**Hardware und lokale LLM-Backends:** siehe zentrale Referenz
`C:\Users\pskra\Python-Projekte\LOCAL-LLM-ENVIRONMENT.md`.

**Shell:** PowerShell 7+ (`pwsh`). Nicht bash.
**Python:** Python 3.12.
-  Der Launcher (`run_benchmarks.py`) startet Benchmarks in einem Subprozess mit `sys.executable`.
-  lint, test, und typecheck aktualisierte Dateien.
-  Systemweites Python hat inspect-ai ebenfalls installiert (OpenStack-oslo-Stack wurde dafür entfernt), ist aber nicht erste Wahl.

**Windows-Kompatibilität ist Pflicht:**
  Vor Einsatz einer neuen Bibliothek oder Standard-Funktionalität prüfen, ob sie auf Windows in der aktuellen Version verfügbar ist.
  Bekannte Fallen (alle schon real aufgetreten):
  - `signal.alarm()` / `signal.SIGALRM` existieren auf Windows NICHT. Betroffen waren
    u.a. lm-eval `minerva_math500` (gefixt 15.07. via eigenem Task) und
    `evalplus.gen.util.openai_request.make_auto_request` (gefixt 14.08. via
    `_WindowsSignalShim`). Bei neuen Abhängigkeiten/Codepfaden diese Stelle prüfen.
  - `os.fork`, POSIX-Signale, `/dev/...` etc. sind nicht verfügbar.

**Tests:** Bei neuen/geänderten Abhängigkeiten oder Codepfaden Kompatibilität mit Windows und python 3.12 testen (import + Smoke-Test),
  nicht nur logisch prüfen.

## Repo-Struktur (Auszug)
- `src/` – Hauptcode (`run_benchmarks.py`, `custom_benchmark.py`, `registry_tool.py`, `assemble_blueprint.py`, `model_registry.py`, `local_model_resolver.py`, `src/providers/`, `evalplus_subset_eval.py`, …)
- `tests/` – Pytest-Suite
- `doc-git/` – Architektur-Doku, model_registry.yaml, blueprint_definitions.yaml, Jinja-Chat-Templates/, Model Specific Hints/, Developer-Docs/
- `PLANUNG.md` – zentrale Workflow- und Architekturplanung im Projektroot
- lokale `run.*.yaml`-Run-Specs – Benchmark-Läufe außerhalb des versionierten Quellcodes
- `ergebnisse/`, `Doku-intern/` – gitignored (Lauf-Ergebnisse, Terminal-Logs, Chatverlauf-Compactions)

## Wichtige Pfade (Windows, lokal)
**Benchmarks-Projektordner:** `C:\Users\pskra\Python-Projekte\Benchmarks`
**LM Studio Modelle (GGUF):** `C:\Users\pskra\.lmstudio\models\`
**LM Studio Hub-Index (Hub):** `C:\Users\pskra\.lmstudio\hub\models\` (inkl. `model.yaml`, Hub-Jinja-Overrides, `manifest.json` der Modelle)
**LM Studio Server-Logs:** `C:\Users\pskra\.lmstudio\server-logs\` (ggf. leer; echte Server-Ausgaben auch via `lms server start --log <datei>`)

**LM Studio JSON-Configs (LM-Studio-lokale Runtime-Artefakte für `numParallelSessions`, `useUnifiedKvCache`, KV-Cache-Quant, SystemPrompt, promptTemplate):**
  `C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\`
**Wichtig:** Diese JSON-Config-Felder sind NICHT die globale Benchmark-Quelle der Wahrheit.
  `doc-git/model_registry.yaml` ist die Single Source of Truth für Benchmark-Policy und provider-neutrale Runtime-Werte;
  `registry_tool.py pipeline full`/`assemble` schreibt LM-Studio-Artefakte daraus, während andere Provider direkt aus Registry/GGUF ableiten.

## LM Studio Doku / Links
- Übersicht Developer Docs: https://lmstudio.ai/docs/developer
- REST API (v1): https://lmstudio.ai/docs/developer/rest – Load-Model: https://lmstudio.ai/docs/developer/rest/load
- OpenAI-kompatible API: https://lmstudio.ai/docs/developer/openai-compat/chat-completions
- SDKs: TypeScript https://lmstudio.ai/docs/typescript/api-reference/llm-load-model-config , Python https://lmstudio.ai/docs/python/api-reference
- Blog: https://lmstudio.ai/blog
- Lokale Referenz mit Parametertabellen: `doc-git/Developer-Docs/LM-Studio-API-References.md`
- Hugging Face Modelle: https://huggingface.co/models (Zugriff via HF-MCP-Tool `hf-mcp-server`, authenticated user `pskraemer11`)

**Alternative Frameworks:**
- Unsloth Studio**:  For the complete documentation index, see [llms.txt](https://unsloth.ai/docs/llms.txt).
    This page is also available as [Markdown](https://unsloth.ai/docs/de/neu/studio.md).
    Unsloth Server Cache: `C:\Users\pskra\.lmstudio\models\hub\` (Unsloth-Studio-Bestände und GGUF-Cache; nicht mit `~\.lmstudio\hub` verwechseln)
- `TabbyAPI` (frontend), nur zusammen mit Python-venv in `exllamv3` (backend), siehe: `C:\Users\pskra\Python-Projekte\tabbyAPI` und `C:\Users\pskra\Python-Projekte\exllamav3`

## Konventionen
- Compaction: Blöcke **IMMER** hinten in `C:\Users\pskra\Python-Projekte\Inspect-Evals\COMPACTIONS.md` anhängen
  (Dateiname großgeschrieben, analog CHANGELOG.md; kein Unterordner).
  CHANGELOG = „was", Compaction = „warum/next". Nur per Write/Edit-Tool schreiben.

- Lint/Typecheck: `ruff check` (config: `pyproject.toml`; ANN-Regeln aktiv).
- Vor Commit: Ruff-Cleanliness für geänderte `src/`-Dateien sicherstellen.
- `utils/` ist fremder Code und bleibt untracked.
- Review: verwende `engineering:code-review` und das zentrale Review-Gate
  `C:\Users\pskra\.agents\references\gates\review.md`. Die verbindliche
  projektspezifische Anwendung ist in `REVIEW-GATE.md` beschrieben.

## Git-Hooks und Sicherheitsgate
- Der versionierte Hook-Pfad ist `.githooks/`; im lokalen Clone muss `git config core.hooksPath .githooks` gesetzt sein.
- `pre-commit` prüft staged Dateien: Diff-Whitespace, sensible Dateitypen, hochwahrscheinliche Secret-Muster,
    Ruff, Python-Syntax, YAML/JSON und bei Registry-Änderungen `registry_tool.py validate --ci` sowie fokussierte Tests.
- `commit-msg` verlangt eine nichtleere Conventional-Commit-Subject-Zeile (maximal 72 Zeichen);
    Merge-/Revert-Nachrichten bleiben erlaubt.
- `pre-push` führt `pre_review_checks.ps1` ohne Skip-Schalter und anschließend den fokussierten blockierenden mypy-Scope aus;
    die dabei erzeugten Artefakte bleiben temporär, weil der Commit beim Pre-Push bereits erstellt ist.
- `--no-verify` ist nur für dokumentierte Notfälle zulässig; die übersprungenen Prüfungen müssen vor dem Push manuell nachgeholt werden.
- Die vollständige lokale Suite und GitHub Actions bleiben unabhängige zweite und dritte Schutzebenen;
    ein lokaler Hook ersetzt keine CI-Prüfung.

## Gemeinsame Agenten-Skills

- Zentrale, agentenagnostische Skills liegen unter `C:\Users\pskra\.agents\skills\`.
- Für lokale Modell- und Backend-Aufgaben zuerst `local-llm-runner` lesen; relevante Backends sind LM Studio CUDA 12.8, llama.cpp CUDA 13.3 und experimentell Transformers/torch/vLLM über WSL2.
- Für technische Benchmarkdaten `data-analytics:validate-data`, `data-analytics:analyze-data-quality`, `data-analytics:visualize-data`, `data-analytics:jupyter-notebooks`, `data-analytics:metric-diagnostics` und `mcp__stats_compass` verwenden.
- Für Reviews und Änderungen `engineering:code-review`, `engineering:debug`, `engineering:testing-strategy`, `codex-engineering-guardrails:code-verification` und `codex-security:security-diff-scan` berücksichtigen.
- Die Hardware-/Backend-Fakten stehen zentral in `C:\Users\pskra\Python-Projekte\LOCAL-LLM-ENVIRONMENT.md`; nicht in weiteren Projektdateien duplizieren.
