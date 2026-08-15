# AGENTS.md – Projekt-Kontext für Agenten

## Umgebung (wichtig – immer beachten)
- **Betriebssystem:** Windows 11 Home (win32). Kein POSIX/UNIX.
- **Hardware**
    Gerätename	HP_Omen_16L
    Prozessor	AMD Ryzen 7 8700F 8-Core Processor (4.10 GHz)
    Installierter RAM	32,0 GB (31,6 GB verwendbar)
    Grafikkarte	NVIDIA GeForce RTX 5060 Ti (16 GB)
    Systemtyp	64-Bit-Betriebssystem, x64-basierter Prozessor

- **Shell:** PowerShell 7+ (`pwsh`). Nicht bash.
- **Python:** Mehrere Versionen im Einsatz, aktuell Python 3.12. 
  Der Launcher (`run_benchmarks.py`) startet Benchmarks in einem Subprozess mit `sys.executable`.
  Parallel gibt es ein volles Env unter Python 3.14. 
  Bei Abhängigkeits-Fehlern zuerst prüfen, in welcher Python-Version das Paket fehlt/installiert werden muss.
  Im Konfiktfall Python 3.12 favorisieren.
  
- **Windows-Kompatibilität ist Pflicht:** Vor dem Einsatz jeder Bibliothek/Standard-
  Funktionalität prüfen, ob sie auf Windows verfügbar ist.
  Bekannte Fallen (alle schon real aufgetreten):
  - `signal.alarm()` / `signal.SIGALRM` existieren auf Windows NICHT. Betroffen waren
    u.a. lm-eval `minerva_math500` (gefixt 15.07. via eigenem Task) und
    `evalplus.gen.util.openai_request.make_auto_request` (gefixt 14.08. via
    `_WindowsSignalShim`). Bei neuen Abhängigkeiten/Codepfaden diese Stelle prüfen.
  - `os.fork`, POSIX-Signale, `/dev/...` etc. sind nicht verfügbar.
  
- **Tests:** Wenn neue/geänderte Abhängigkeiten oder Codepfade eingebaut werden,
  Kompatibilität mit Windows testen (import + Smoke-Test), nicht nur logisch prüfen.

## Repo-Struktur (Auszug)
- `src/` – Hauptcode (`run_benchmarks.py`, `custom_benchmark.py`, `registry_tool.py`, `assemble_blueprint.py`, `evalplus_subset_eval.py`, …)
- `tests/` – Pytest-Suite
- `doc-git/` – Architektur-Doku, Planung.md, model_registry.yaml, blueprint_definitions.yaml, Jinja-Chat-Templates/, Model Specific Hints/, Developer-Docs/
- `run.verify-fixes.yaml` u.ä. – YAML-Run-Specs für Benchmark-Läufe
- `ergebnisse/`, `Doku-intern/` – gitignored (Lauf-Ergebnisse, Terminal-Logs, Chatverlauf-Compactions)

## Wichtige Pfade (Windows, lokal)
- **Benchmark-Projektordner:** `C:\Users\pskra\Python-Projekte\Benchmarks`
- **LM Studio Modell-Index (Hub):** `C:\Users\pskra\.lmstudio\hub\models\` (inkl. `model-index-cache.json`, Hub-Jinja-Overrides, `manifest.json` der Modelle)
- **LM Studio Server-Logs:** `C:\Users\pskra\.lmstudio\server-logs\` (ggf. leer; echte Server-Ausgaben auch via `lms server start --log <datei>`)
- **LM Studio Modelle (GGUF/Configs):** `C:\Users\pskra\.lmstudio\models\`
- **Per-Modell-JSON-Configs (autoritativ für `numParallelSessions`, `useUnifiedKvCache`, KV-Cache-Quant, SystemPrompt, promptTemplate):** `C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\`
- **Wichtig:** Diese JSON-Config-Felder sind NICHT über die REST/OpenAI-API setzbar – sie müssen vor dem Modell-Load in der Config stehen; `model_registry.yaml` ist die Single Source of Truth, `pipeline full`/`assemble` schreibt sie in die Configs.

## LM Studio Doku / Links
- Übersicht Developer Docs: https://lmstudio.ai/docs/developer
- REST API (v1): https://lmstudio.ai/docs/developer/rest – Load-Model: https://lmstudio.ai/docs/developer/rest/load
- OpenAI-kompatible API: https://lmstudio.ai/docs/developer/openai-compat/chat-completions
- SDKs: TypeScript https://lmstudio.ai/docs/typescript/api-reference/llm-load-model-config , Python https://lmstudio.ai/docs/python/api-reference
- Blog: https://lmstudio.ai/blog
- Lokale Referenz mit Parametertabellen: `doc-git/Developer-Docs/LM-Studio-API-References.md`
- Hugging Face Modelle: https://huggingface.co/models (Zugriff via HF-MCP-Tool `hf-mcp-server`, authenticated user `pskraemer11`)

## Konventionen
- Lint/Typecheck: `ruff check` (pyproject.toml; ANN-Regeln aktiv).
- Vor Commit: Ruff-Cleanliness für geänderte `src/`-Dateien sicherstellen.
- `utils/` ist fremder Code und bleibt untracked.