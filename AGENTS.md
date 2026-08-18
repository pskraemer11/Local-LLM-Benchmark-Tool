# AGENTS.md – Projekt-Kontext für Agenten

## Umgebung
- **Betriebssystem:** Windows 11 Home (win32). Kein POSIX/UNIX.
- **Hardware**
    Gerätename	HP_Omen_16L
    Prozessor	AMD Ryzen 7 8700F 8-Core Processor (4.10 GHz)
    Installierter RAM	32,0 GB (31,6 GB verwendbar)
    Grafikkarte	NVIDIA GeForce RTX 5060 Ti (16 GB)
    Systemtyp	64-Bit-Betriebssystem, x64-basierter Prozessor

- **Shell:** PowerShell 7+ (`pwsh`). Nicht bash.
- **Python:** vorrangig Python 3.12.
  Der Launcher (`run_benchmarks.py`) startet Benchmarks in einem Subprozess mit `sys.executable`.
  Parallel gibt es eine Installation von Python 3.14.
  Bei Abhängigkeits-Fehlern zuerst prüfen, in welcher Python-Version das Paket fehlt/installiert werden muss.
  Im Konfiktfall Python 3.12 favorisieren.
  
- **Windows-Kompatibilität ist Pflicht:**
  Vor dem Einsatz jeder Bibliothek/Standard-Funktionalität prüfen, ob sie auf Windows verfügbar ist.
  Bekannte Fallen (alle schon real aufgetreten):
  - `signal.alarm()` / `signal.SIGALRM` existieren auf Windows NICHT. Betroffen waren
    u.a. lm-eval `minerva_math500` (gefixt 15.07. via eigenem Task) und
    `evalplus.gen.util.openai_request.make_auto_request` (gefixt 14.08. via
    `_WindowsSignalShim`). Bei neuen Abhängigkeiten/Codepfaden diese Stelle prüfen.
  - `os.fork`, POSIX-Signale, `/dev/...` etc. sind nicht verfügbar.
  
- **Tests:** Bei neuen/geänderten Abhängigkeiten oder Codepfaden Kompatibilität mit Windows testen (import + Smoke-Test),
  nicht nur logisch prüfen.

## Repo-Struktur (Auszug)
- `src/` – Hauptcode (`run_benchmarks.py`, `custom_benchmark.py`, `registry_tool.py`, `assemble_blueprint.py`, `model_registry.py`, `local_model_resolver.py`, `src/providers/`, `evalplus_subset_eval.py`, …)
- `tests/` – Pytest-Suite
- `doc-git/` – Architektur-Doku, model_registry.yaml, blueprint_definitions.yaml, Jinja-Chat-Templates/, Model Specific Hints/, Developer-Docs/
- `PLANUNG.md` – zentrale Workflow- und Architekturplanung im Projektroot
- `run.verify-fixes.yaml` u.ä. – YAML-Run-Specs für Benchmark-Läufe
- `ergebnisse/`, `Doku-intern/` – gitignored (Lauf-Ergebnisse, Terminal-Logs, Chatverlauf-Compactions)

## Wichtige Pfade (Windows, lokal)
- **Benchmark-Projektordner:** `C:\Users\pskra\Python-Projekte\Benchmarks`
- **LM Studio Modelle (GGUF):** `C:\Users\pskra\.lmstudio\models\`
- **LM Studio Hub-Index (Hub):** `C:\Users\pskra\.lmstudio\hub\models\` (inkl. `model.yaml`, Hub-Jinja-Overrides, `manifest.json` der Modelle)
- **LM Studio Server-Logs:** `C:\Users\pskra\.lmstudio\server-logs\` (ggf. leer; echte Server-Ausgaben auch via `lms server start --log <datei>`)

- **LM Studio JSON-Configs (LM-Studio-lokale Runtime-Artefakte für `numParallelSessions`, `useUnifiedKvCache`, KV-Cache-Quant, SystemPrompt, promptTemplate):** `C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\`
- **Wichtig:** Diese JSON-Config-Felder sind NICHT die globale Benchmark-Quelle der Wahrheit. `doc-git/model_registry.yaml` ist die Single Source of Truth für Benchmark-Policy und provider-neutrale Runtime-Werte; `registry_tool.py pipeline full`/`assemble` schreibt LM-Studio-Artefakte daraus, während andere Provider direkt aus Registry/GGUF ableiten.

## LM Studio Doku / Links
- Übersicht Developer Docs: https://lmstudio.ai/docs/developer
- REST API (v1): https://lmstudio.ai/docs/developer/rest – Load-Model: https://lmstudio.ai/docs/developer/rest/load
- OpenAI-kompatible API: https://lmstudio.ai/docs/developer/openai-compat/chat-completions
- SDKs: TypeScript https://lmstudio.ai/docs/typescript/api-reference/llm-load-model-config , Python https://lmstudio.ai/docs/python/api-reference
- Blog: https://lmstudio.ai/blog
- Lokale Referenz mit Parametertabellen: `doc-git/Developer-Docs/LM-Studio-API-References.md`
- Hugging Face Modelle: https://huggingface.co/models (Zugriff via HF-MCP-Tool `hf-mcp-server`, authenticated user `pskraemer11`)

- Alternative Frameworks: **Unsloth Studio**:  For the complete documentation index, see [llms.txt](https://unsloth.ai/docs/llms.txt).
    This page is also available as [Markdown](https://unsloth.ai/docs/de/neu/studio.md).
- **Unsloth Server Cache:** `C:\Users\pskra\.lmstudio\models\hub\` (Unsloth-Studio-Bestände und GGUF-Cache; nicht mit `~\.lmstudio\hub` verwechseln)
- dito: `TabbyAPI` zusammen mit venv in `exllamv3`, siehe: `C:\Users\pskra\Python-Projekte\tabbyAPI` und `C:\Users\pskra\Python-Projekte\exllamav3`

## Konventionen
- Lint/Typecheck: `ruff check` (pyproject.toml; ANN-Regeln aktiv).
- Vor Commit: Ruff-Cleanliness für geänderte `src/`-Dateien sicherstellen.
- `utils/` ist fremder Code und bleibt untracked.
- Review: beachte Skill review.md
