# Security-Fix-Report

Stand: 2026-08-20
Scan-ID: `c6fef5c3-f885-4cfb-afd0-b53a34cda5cf`

## Ergebnis

Die beiden mittel/high priorisierten Findings sind umgesetzt und durch die vollständige Testsuite sowie fokussierte Live-Smokes geprüft.

**Finding 1 ist taktisch mitigiert, aber noch nicht vollständig geschlossen:
**Die native Loader-API ist in der Code-Sandbox gesperrt und der Prozess wird unter Windows ressourcenbegrenzt ausgeführt;
** eine unabhängige OS-Sicherheitsgrenze mit separater Identität sowie expliziter Datei-/Netzwerkisolation ist in diesem Patch jedoch noch nicht etabliert.

| Finding                                       | Status                    | Umsetzung                                                                                     |
|-----------------------------------------------|---------------------------|-----------------------------------------------------------------------------------------------|
| Generated-code sandbox / native-loader APIs   | Mitigiert, offen für      | Import- und Attribut-Allowlist blockiert `ctypes`, `numpy.ctypeslib`, `scipy`-Callback-Loader |
|                                               |   vollständige Schließung |     und typische native Loader; Windows Job Object begrenzt Speicher, Prozesse und Laufzeit.  |
| LM-Eval proxy: unbounded resources            | Behoben                   | Loopback-Bindung, feste Routen, Größenlimits für Requests/Responses/SSE, Idle-Timeout und     |
|                                               |                           |     begrenzte Parallelität.                                                                   |
| Windows EvalPlus: memory enforcement disabled | Behoben                   | Positives Speicherlimit, Windows-Job-Object-Ausführung des EvalPlus-Subprozesses und          |
|                                               |                           |      Beibehaltung des EvalPlus-Schutzes ohne POSIX-Signalannahme.                             |

## Geänderte Kernbereiche

- `src/sandbox_worker.py`: native Loader und bekannte Loader-Attribute werden vor Ausführung abgewiesen.
- `src/windows_job_object.py`: begrenzter Windows-Subprozess-Runner mit Prozessbaum-Terminierung bei Timeout.
- `src/evalplus_subset_eval.py` und `src/run_benchmarks.py`: EvalPlus läuft mit einem positiven Speicherlimit
      und unter dem Windows-Job-Object.
- `src/tools/lmeval_proxy.py`: Netzwerk-, Größen-, Timeout- und Concurrency-Grenzen.
- `src/providers/lmstudio_provider.py` und `src/providers/unsloth_server_provider.py`: belastbare Readiness-Prüfung,
    explizite API-Fehlerbehandlung und Attach an einen bereits laufenden kompatiblen Unsloth-CLI-Server.
- `src/model_manager.py`: ein explizit gesetztes `LLM_API_BASE` überschreibt keine veraltete spezialisierte Provider-Variable mehr.

## Verifikation

- `py -3.12 -m pytest -q`: **905 passed**, 1 vorhandene `pynvml`-Deprecation-Warnung.
- Ruff für alle geänderten Source- und Testdateien: **All checks passed**.
- Python-Kompilationsprüfung der geänderten Source-Dateien: erfolgreich.
- Direkter Sandbox-Smoke: `numpy` funktioniert; `numpy.ctypeslib` wird mit `ImportError` und Hinweis auf die Sandbox-Allowlist abgewiesen.
- Job-Object-Runner: Erfolg/Capture und Timeout-Prozessbaum sind durch Tests abgedeckt.
- Proxy-Smokes: erlaubte Route/Weiterleitung, unbekannte Route,Loopback-Bindung und übergroßer Request sind abgedeckt.

## Live-Modell-Smokes

Die Prüfung wurde auf Provider-/OpenAI-kompatibler API-Ebene mit laufenden
lokalen Diensten durchgeführt; sie war kein vollständiger Benchmarklauf.

| Dienst                                                   | Ergebnis                                                                                                                                       |
|----------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| LM Studio/`llmster`, `127.0.0.1:1234`                    | Modell `f2llm-v2-1.7b` geladen, Readiness bestätigt, Chat-Antwort erhalten; anschließend wurden die Testinstanzen wieder entladen.             |
| Unsloth `llama-server` CLI, `127.0.0.1:8890`             | Bereits laufendes Modell erkannt, ohne zweiten Server zu starten angehängt, Readiness bestätigt, Chat-Antwort `unsloth-after-fix-ok` erhalten. |
| Unsloth Studio GUI, erwarteter Endpoint `127.0.0.1:8888` | Nicht verifizierbar: Zum Prüfzeitpunkt war kein Unsloth-Studio-GUI-Prozess sichtbar und der Endpoint nicht erreichbar.                         |
| LM Studio GUI-Prozess                                    | Nicht verifizierbar: Es lief der LM-Studio-Backenddienst; ein separater GUI-Prozess war zum Prüfzeitpunkt nicht sichtbar.                      |

Damit ist die Kompatibilität mit laufenden LM-Studio-/llmster- und Unsloth-CLI-Backends belegt.
Ein GUI-spezifischer Smoke bleibt offen, weil die zugehörigen GUIs in der Prüfkonfiguration nicht liefen.

## Verbleibendes Risiko und nächster Schritt

Für die vollständige Schließung von Finding 1 muss die Ausführung generierten Codes in einen separat berechtigten Worker mit expliziter
Datei-/Netzwerk-Isolation verlagert werden (z. B. Windows-AppContainer oder ein gleichwertiger isolierter Prozessdienst).
Die aktuelle Allowlist und das Job Object reduzieren den Angriffsweg deutlich, ersetzen diese OS-Grenze aber nicht.
