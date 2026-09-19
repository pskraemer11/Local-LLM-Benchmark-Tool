# Planung: pragmatische, score-kompatible Prozessisolation

Status: 2026-08-28. Prioritaet: Score-Kompatibilitaet vor zusaetzlicher Sicherheitskomplexitaet.

## Leitentscheidung

Die lokale Benchmark-Suite verwendet kein Docker- oder Podman-Pflichtsetup und keine vollstaendige Mock-Tool-Welt. Die Modelle sollen fuer gueltige Benchmark-Aufgaben dieselben Bibliotheken und Python-Funktionen nutzen koennen wie bisher.

Die Schutzschicht besteht aus:

1. einmalig nach dem Download geprueften Benchmark-Inputs;
2. einem separaten Python-Worker-Prozess;
3. einem Windows Job Object mit Ressourcenlimits;
4. Timeout, begrenzter Ausgabe und bereinigter Umgebung.

Die Prozessgrenze ist eine pragmatische Begrenzung gegen Fehlverhalten und Ressourcenprobleme, keine vollstaendige Sicherheits-Sandbox. Eine harte Import-Allowlist, Dunder-Blockade oder aggressive Dateipfad-Sperre gehoert nicht in den Standardpfad, weil sie gueltigen Code blockieren und Scores verfaelschen kann.

## Abgeschlossene erste Umsetzung

- [x] Bestehende Planung vor der Umstellung gesichert: `PLANUNG.md.backup-20260828-1130.md`.
- [x] JSON-Worker und Windows Job Object fuer Custom-Benchmarks vorhanden.
- [x] EvalPlus-Auswertung laeuft ebenfalls ueber `run_bounded_subprocess()` und Windows Job Object.
- [x] Import-Allowlist und harte Dunder-/Native-Loader-Pruefungen aus dem normalen Workerpfad entfernt. Bibliotheks- und Standardbibliotheksimporte bleiben score-kompatibel.
- [x] Einmaliges Manifest-Werkzeug in `src/task_manifest.py` und `src/prepare_task_manifests.py` angelegt.
- [x] Das Manifest speichert nur Quelle, SHA-256, Anzahl sowie bestehende Aufgaben-IDs/Positionen und offensichtliche Warnungen. Es gibt keine separate Datenbank und keine laufende Pflegeinstanz.
- [x] Warnungen beschraenken sich auf offensichtliche Prompt-Injection-Muster, insbesondere das Ignorieren vorheriger Benchmark-Regeln und den Zugriff auf Secrets.

## Inputs einmalig pruefen

Nach jedem neuen Download wird einmalig ausgefuehrt:

```powershell
py -3.12 src\prepare_task_manifests.py `
  --input DS1000=simple_evals\data_science.jsonl `
  --input CoderEval=simple_evals\codereval_selfcontained.jsonl `
  --output ergebnisse\task_manifest.json
```

Bei Warnungen beendet das Werkzeug den Lauf mit einem Warnstatus. Die verantwortliche Person muss die Aufgabe pruefen und den Vorgang mit `--allow-warnings` bewusst freigeben. Das Manifest wird anschliessend als Ergebnisartefakt archiviert und nicht bei jedem Modelllauf neu erzeugt.

Geprueft werden nur Textfelder und nur diese offensichtlichen Muster:

- `ignore previous instructions/rules`;
- `ignore the benchmark rules/instructions`;
- Aufforderungen, Secrets, Tokens, Passwoerter, Credentials oder API-Keys zu lesen, auszugeben oder zu uebertragen;
- Aufforderungen, den System-Prompt offenzulegen.

Das Werkzeug interpretiert keine Aufgabe um, entfernt keinen Inhalt und veraendert keine Benchmarkdaten.

## Prozessausfuehrung

### Standardablauf

1. Der Benchmark erzeugt den Modellcode wie bisher.
2. Der Parent-Prozess startet pro Auswertung einen Worker mit JSON ueber stdin.
3. Der Worker fuehrt Code und Tests in derselben Python-Umgebung aus, damit die wissenschaftlichen Bibliotheken kompatibel bleiben.
4. Der Worker schreibt genau ein begrenztes JSON-Ergebnis ueber stdout.
5. Der Parent-Prozess beendet, bewertet und raeumt den Worker anschliessend auf.

### Ressourcenlimits

Die bestehenden Limits werden zentral und benchmarkfreundlich weiterverwendet:

- Wall-clock-Timeout pro Auswertung;
- Speicherlimit im Windows Job Object;
- maximale Zahl aktiver Prozesse im Job;
- Beenden des gesamten Prozessbaums bei Timeout oder Fehler;
- begrenzte stdout-/stderr-Ausgabe;
- temporaeres Arbeitsverzeichnis und bereinigte Umgebung.

Die Limits muessen gross genug fuer Matplotlib, NumPy, Pandas, SciPy und scikit-learn sein. Ein Limit darf nicht wegen eines einzelnen langsamen Modells so klein gewaehlt werden, dass gueltige Aufgaben als Sicherheitsfehler erscheinen.

### Code-Benchmarks

- [x] DS1000 und CoderEval verwenden den vorhandenen JSON-Worker mit Job Object.
- [x] HumanEval+ und MBPP+ verwenden die bestehende separate EvalPlus-Auswertung mit Job Object.
- [ ] Nach der Worker-Aenderung je Benchmark einen kleinen Kompatibilitaetstest mit SampleSize 1 ausfuehren.
- [ ] Danach gepaarte Vorher-/Nachher-Laeufe auf exakt demselben gespeicherten Task-Satz ausfuehren.

## Vergleichbarkeit und Abnahme

Ein Kompatibilitaetsvergleich verwendet:

- dasselbe Modell und dieselbe Quantisierung;
- dieselben Sampling-Parameter;
- denselben Seed;
- dasselbe einmalig erzeugte Manifest;
- dieselbe Aufgabenreihenfolge;
- dieselben Test- und Ressourcenlimits.

Ausgewiesen werden Score, bestandene/fehlgeschlagene Aufgaben, Worker-Fehler, Timeouts, Laufzeit und Ressourcenverbrauch. Ein Scoreverlust gilt erst dann als Härtungsregression, wenn der gepaarte Vergleich denselben Task-Satz verwendet und die Ursache nicht durch Modell-, Daten- oder Laufzeitunterschiede erklaert werden kann.

## Nicht Bestandteil dieser Planung

- kein Docker- oder Podman-Zwang;
- kein vollstaendiges Mocking aller denkbaren Agent-Tools;
- keine laufende Datenbank fuer Aufgabenmarker;
- keine harte Import-Allowlist im Standardlauf;
- keine zusaetzliche optionale Hochsicherheitsvariante.

Agentic-Benchmarks bleiben vorerst bei den vorhandenen Inspect-AI-Tools und dem pragmatischen Prozessmodell. Echte Datei-, Shell- oder Netzwerkaktionen werden nicht durch eine universelle Attrappenwelt ersetzt.

## Offene Punkte aus der bisherigen Planung

### Modell- und Registry-Arbeiten

- [ ] Qwen3.8-Unsloth-Empfehlungen und neue Modelle in Blueprint/Assembly integrieren. Qwen3.6-Kompatibilitaet und die kanonische Identitaet `publisher/model@quant` erhalten.
- [ ] Konfigurierbaren GGUF-Modellroot mit primaerer neuer Quelle und kompatiblem altem Fallback umsetzen; Junction-Unterstuetzung bleibt erhalten.
- [~] Qwen-Nachlauf und Top-Candidates-Neuauflage mit aktuellem Setup, vollstaendiger Modellabdeckung und korrekter Konsolidierung abschliessen.

### Provider-Architektur

- [ ] Phase 6 abschliessen: Runner vollstaendig ueber Provider-/Client-Kontext fuehren, API-Basis aus dem InferenceClient beziehen, OpenAI-kompatible Inferenzpfade vereinheitlichen und Parallelitaet nur aus Provider-Capabilities/Registry ableiten.
- [ ] Offene echte Server-Smoke-Tests und Lifecycle-Verifikation fuer die jeweils betroffenen Provider nachziehen.

### Benchmark- und Qualitaetsverifikation

- [ ] Task-Manifeste fuer die tatsaechlich verwendeten Code-Benchmark-Datensaetze erzeugen und auffaellige Aufgaben vor dem naechsten Referenzlauf bewerten.
- [ ] SampleSize-1-Smoke der Workerpfade ausfuehren.
- [ ] Gepaarte Kompatibilitaetslaeufe vor/nach der Import-Blockaden-Entfernung mit identischem Manifest ausfuehren.
- [ ] Manifest- und Worker-Funktionen mit Ruff, Python-3.12-Syntaxcheck und fokussierten Pytest-Tests verifizieren.
- [ ] Nach Abschluss die Ergebnisse und die Entscheidung zur Score-Neutralitaet in `ergebnisse/` dokumentieren.

## Verifikation vor Commit

```powershell
py -3.12 -m pytest tests\test_task_manifest.py tests\test_sandbox_worker.py tests\test_custom_benchmark_io.py -q --basetemp=.pytest-temp
ruff check src\task_manifest.py src\prepare_task_manifests.py src\sandbox_worker.py tests\test_task_manifest.py tests\test_sandbox_worker.py
py -3.12 -m py_compile src\task_manifest.py src\prepare_task_manifests.py src\sandbox_worker.py
```

Anschliessend folgt ein SampleSize-1-Smoke mit laufendem LM-Studio-Server. Erst danach wird ein groesserer gepaarter Benchmark-Lauf gestartet.
