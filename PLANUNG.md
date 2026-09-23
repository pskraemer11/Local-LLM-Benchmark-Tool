# Planung: Prozessisolation, direkte llama.cpp-Migration und Benchmark-Abnahme

Status: 2026-09-23. Prioritaet: reproduzierbare Backend-Abnahme und Score-Kompatibilitaet.

## Aktueller Gesamtstatus

Die direkte llama.cpp-Integration ist technisch weitgehend umgesetzt und mit
lokalen Server-Smokes, vier Pipeline-Smokes und einem sequenziellen
Mehrmodelllauf geprüft. Die fachliche Abnahme ist noch nicht abgeschlossen.
Insbesondere stehen der LM-Studio-/llama.cpp-Kompatibilitaetsvergleich, der
separate GLM-Streamingvergleich, die Qualitaetsauswertung und die offenen
Worker-/Manifest-Vergleiche noch aus.

- `[x]` Produktives lokales Backend: `C:\Program Files\llama.cpp\llama-server.exe`.
- `[x]` Registry als fachliche Quelle; `config.ini` und `preset.ini` als
  Runtime-/Exportebenen getrennt.
- `[x]` Direkter Provider- und Runnerpfad einschliesslich Lifecycle und
  `SampleSize`-abhaengiger Parallelitaetsregel.
- `[~]` Kompatibilitaet, Modell-Templates, Warnungen und fachliche Scores sind
  noch nicht vollstaendig abgenommen.
- `[~]` Der fruehere LM-Studio-SampleSize-5-Lauf ist gesichert bzw. pausiert;
  er wird erst nach der direkten Backend-Abnahme fortgesetzt oder neu geplant.
- `[x]` Gemma APEX ist mit dem live getesteten Wert `experts: 36` und dem
  Registry-Schluessel `mudler/gemma-4-26b-a4b-it-apex@mini` erfasst;
  `registry_tool.py validate --ci` meldete danach 0 Blocker und 0 Hinweise.

## Naechste Schritte

Die folgenden Punkte sind die noch ausstehenden Arbeiten. Die ersten fuenf
bilden die Abnahme des direkten llama.cpp-Backends; erst danach soll der grosse
Benchmarklauf beginnen.

1. LM Studio und llama.cpp mit gleichen Modellen, Aufgaben und Einstellungen
   vergleichen und technische Unterschiede festhalten.
2. GLM-4.7 zusaetzlich im Streamingbetrieb testen und pruefen, ob Antwort,
   Reasoning und Abschlussstatus vollstaendig ankommen.
3. Fehler und Warnungen aus Runner, Benchmark-Pipelines und llama.cpp-Logs
   einzeln untersuchen und ihre Bedeutung fuer die Ergebnisse dokumentieren.
4. Feste Aufgabenlisten fuer die Code-Benchmarks erstellen und die isolierten
   Worker mit genau denselben Aufgaben gegenpruefen.
5. Die Antwortqualitaet mehrerer geeigneter Modelle fuer Coding, Mathematik
   und agentische Aufgaben auswerten; kurze Funktionstests reichen dafuer nicht.
6. Nach erfolgreicher Abnahme den pausierten Lauf mit `SampleSize=5` direkt
   ueber llama.cpp fortsetzen oder als neuen, dokumentierten Lauf planen.
7. Danach Ergebnisse, Vergleichbarkeit und Qualitaetsbaseline festhalten.

Weitere, nicht blockierende Pflegepunkte sind die Qwen3.8-/Modellpflege, die
vollstaendige Pruefung der Registry-Feldregeln, wiederholbare Exporttests fuer
Modellfamilien, llama.cpp-Updatechecks und die Bereinigung des strengen mypy-
Bestands. Details und Verifikationskriterien stehen in den jeweiligen
Abschnitten weiter unten.

### Registry-Synchronisierung vereinfachen

Die Neugestaltung erfolgt bewusst in drei getrennten Phasen, damit Datenregeln,
Schreibverhalten und Bedienung nicht gleichzeitig veraendert werden:

1. [x] Verbindliche Feld- und Quellenmatrix in der Architektur-Dokumentation
   festlegen und von der README aus verlinken.
2. [x] Einen gemeinsamen Inventurbericht und daraus nachvollziehbare,
   feldweise Aenderungsvorschlaege einfuehren; die sieben zuvor festgehaltenen
   Architektur- und Sicherheitsbefunde schrittweise darin beheben:
   - Registry, LM-Studio-Liste und Config-Dateien werden pro Lauf einmal
     gelesen; der grosse GGUF-Dateibaum wird nur bei Bedarf einmal gescannt.
   - Abweichungen werden feldweise mit Quelle, Ist-Wert, Vorschlag oder
     Konflikt ausgewiesen; unklare Identitaeten und widerspruechliche Configs
     werden nie automatisch gewaehlt.
   - Config-Import bleibt standardmaessig ein Bericht; Schreiben benoetigt
     `--import-lms-settings` bzw. den dokumentierten Spezialbefehl.
   - Importierte Kontext- und Expertenwerte duerfen die GGUF-Obergrenzen nicht
     ueberschreiten.
   - `file_size_bytes` stammt ausschliesslich von der Haupt-GGUF-Datei, nicht
     aus der groben LM-Studio-Groessenanzeige.
   - `quarantine-missing` ist standardmaessig Vorschau; `--apply` plant Moves,
     sichert Registry-Daten und rollt bei Schreibfehlern soweit moeglich zurueck.
   - Sampling-Websuche ist nur explizit moeglich; Template-Sync nutzt aktive,
     eindeutig zugeordnete Configs; Preset-Export ersetzt alte generierte
     Abschnitte, behaelt aber globale und manuelle INI-Bloecke.
3. [x] Nach stabilen Tests die sichtbaren Registry-Befehle auf
   `status`, `sync`, `full`, `validate`, `preset` und `quarantine-missing`
   vereinfachen. Spezialisierte und bisherige direkte Befehle bleiben als
   Kompatibilitaetsschnittstelle unter `advanced` bzw. mit ihren alten Namen
   erreichbar.

Abschluss des Arbeitspakets am 23.09.2026: Die aktuellen LM-Studio-Configs
wurden inventarisiert und als Feldvorschlaege geprueft. 23 eindeutige,
unterstuetzte Runtime-Werte wurden explizit in die Registry importiert; ein
neues Qwen3.8-APEX-Modell wurde mit unbekannter Quantisierung (`@?`) erfasst.
Drei mehrdeutige Config-Identitaeten bleiben bewusst ohne Import, bis ihre
Registry-Zuordnung eindeutig ist: FreedomAISVR Gemma QAT NVFP4, GGUF-org Muse
Glimmer und Qwen3.5-9B. Der abschliessende Sync meldete keine weiteren
Feldvorschlaege. `validate --ci` meldete 0 Blocker und 0 Hinweise.

Das bestehende llama.cpp `preset.ini` wurde aus der Registry aktualisiert:
66 lokale Modellsektionen, einschliesslich modell-/architekturspezifischer
Experts-Overrides; drei Registry-Eintraege ohne lokale GGUF-Datei wurden
uebersprungen und gemeldet. Die globalen Defaults und der manuelle
`[gpt-oss-20b]`-Abschnitt blieben erhalten. Der Zieldatei-Abgleich gegen den
vorher gesicherten Stand wurde vor dem Schreiben geprueft. Die gezielte Suite
`test_registry_tool.py`, `test_registry_pipeline.py` und
`test_assemble_blueprint.py` bestand mit 229 Tests; Ruff und die Registry-CI-
Validierung bestanden ebenfalls.

In dieser Datei bedeutet `[x]` abgeschlossen, `[~]` teilweise erledigt,
bewusst zurueckgestellt oder noch mit einer offenen Teilabnahme und `[ ]`
offen.

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
- [x] Konfigurierbaren GGUF-Modellroot mit primaerer neuer Quelle und kompatiblem altem Fallback umsetzen; Junction-Unterstuetzung bleibt erhalten.
- [x] Die llama.cpp-HF-Cache-Struktur mit `snapshots\\<revision>\\*.gguf`
  aufloesen; die GUI-Sichtbarkeit ist fuer den Benchmarkpfad nicht
  erforderlich.
- [x] Den Millie-Vision-Projektor mit `mmproj-`-Namenskonvention aus der
  LLM-Inventur und Registry-Zuordnung herausfiltern; der Hauptlauf bleibt ein
  `qwen35moe`-Modell mit getrennt dokumentiertem Projektor.
- [~] Qwen-Nachlauf und Top-Candidates-Neuauflage mit aktuellem Setup, vollstaendiger Modellabdeckung und korrekter Konsolidierung abschliessen.
- [x] Den live getesteten Laufzeitwert `experts: 36` und die Quantisierung
  `@mini` fuer `mudler/gemma-4-26b-a4b-it-apex` in die Registry uebernehmen;
  die anschliessende Registry-Validierung meldete keine Blocker oder Hinweise.

### Provider-Architektur und Backend-Migration

#### Neue Backend-Migrationsplanung: direkter llama.cpp-Runner

Status: 2026-09-22. Ziel: Das produktive Benchmark-Backend wird der direkt
gestartete llama.cpp-Server. LM Studio bleibt ein experimentelles Werkzeug fuer
Parameter-, VRAM- und Kompatibilitaetstests. Unsloth Studio/API ist kein
Bestandteil des produktiven Benchmarkpfads.

##### Leitentscheidung

Die Benchmarks verwenden künftig:

```text
run_benchmarks.py
    -> llama-server.exe
        -> OpenAI-kompatible lokale API (/v1/chat/completions)
```

Der Server wird pro Modell direkt als eigener Prozess gestartet und nach dem
Modelllauf wieder beendet. `lms.exe`, LM-Studio-REST-Lifecycle-Aufrufe und ein
Unsloth-Studio-Lifecycle werden im direkten Backend nicht benötigt.

##### Architekturentscheidung: Registry als fachliche Quelle, llama.cpp als Runtime-Ziel

Die llama.cpp-Preset-INI ersetzt `model_registry.yaml` nicht vollständig.
Beide Formate haben unterschiedliche Verantwortungen:

| Verantwortungsbereich | Verbindliche Quelle | Begründung |
| --- | --- | --- |
| Modellidentität `publisher/model@quant` | `model_registry.yaml` | Die Identität ist providerübergreifend und wird für Ergebnisse, Matching und Konsolidierung benötigt. |
| GGUF-Datei, Architektur, Quantisierung, native Grenzen | GGUF-Header, Dateiname und Registry | Diese Informationen sind technische Fakten und keine bloßen Startargumente. |
| Modelltyp, Blacklist, Vision-/Embedding-/OCR-Abgrenzung | Registry | llama.cpp-Presets beschreiben keine Benchmark-Auswahlregeln. |
| Blueprint, Jinja, Prompt- und Reasoning-Policy | `blueprint_definitions.yaml` und Templates | Diese Regeln gelten vor dem Backend und dürfen nicht an eine INI-Syntax gekoppelt werden. |
| Sampling je Kategorie | Registry plus API-Request | Coding, Math, Agentic und Knowledge können unterschiedliche Werte benötigen. Eine statische Modellsektion reicht dafür nicht aus. |
| Provenienz, Quellen, Validierungsstatus | Registry | Diese Informationen gehören nicht in die ausführbare llama.cpp-Konfiguration. |
| llama.cpp-Lade- und Serverparameter | generiertes Preset oder Argumentmanifest | `ctx-size`, KV-Typen, Batch, GPU-Layer, Flash Attention, Parallelität und ähnliche Werte sind backendabhängig. |
| Aufgabenspezifische API-Parameter | `run_benchmarks.py`/Provider-Request | Structured Output, Seed, Stop-Verhalten und Kategorie-Sampling können pro Request variieren. |

Die Zielrichtung lautet daher:

```text
model_registry.yaml + GGUF-Metadaten + Blueprint
        │
        ├─ registry_tool.py validate / import / export
        │       ├─ llama.cpp-Argumentmanifest pro Modell
        │       └─ optional: preset.ini für Router-/Mehrmodellbetrieb
        │
        └─ run_benchmarks.py
                └─ llama_cpp_provider.py
                        ├─ deterministischer Serverstart pro Modell
                        └─ OpenAI-kompatible Requests
```

`registry_tool.py` soll deshalb nicht durch einen INI-Editor ersetzt werden.
Stattdessen erhält es einen expliziten Exportpfad, beispielsweise
`preset` (mit dem Kompatibilitätsalias `export-llama-preset`) oder
`export-llama-args`. Der Export ist reproduzierbar, prüfbar und darf keine
stillen Rückschreibungen in die Registry auslösen.

Für den zunächst geplanten Einzelprozess pro Modell werden modellabhängige
Startargumente beziehungsweise ein Ein-Modell-Argumentmanifest bevorzugt.
`--models-preset` wird als Router-Option separat getestet. Ein globales
llama.cpp-`config.ini` darf nur gemeinsame Defaults enthalten; es ist keine
verlässliche Ablage für beliebige benannte Modellsektionen.

Für Windows gilt dabei eine wichtige Trennung: `config.ini` wird von llama.cpp
automatisch als globale Vorgabe aus dem System-/Benutzer-Konfigurationspfad
geladen; CLI-Argumente und `LLAMA_ARG_*`-Umgebungsvariablen überschreiben diese
Vorgaben. Die portable Router-Datei unter
`C:\Users\pskra\.config\llama.cpp\preset.ini` wird dagegen explizit über
`LLAMA_ARG_MODELS_PRESET` beziehungsweise `--models-preset` ausgewählt. Sie
enthält `[*]` für gemeinsame Router-Defaults und benannte Modellsektionen.
Die Benutzer-Variable muss auf die Datei selbst, nicht nur auf ihren Ordner,
zeigen. Der aktuelle CUDA-Server akzeptiert `mmap` nicht als Preset-Schlüssel;
dieser Eintrag wurde aus der bestehenden Datei entfernt, damit der Router
startet. MMap bleibt bei Bedarf ein explizites CLI-/Runtime-Argument.

##### llama.cpp-Installations- und PATH-Policy

Am 21.09.2026 wurden drei `llama.exe`-Fundstellen aufgelöst:

| Pfad | Status | Nachweis/Rolle |
| --- | --- | --- |
| `C:\Program Files\llama.cpp` | bevorzugter Produktionspfad | Build 10964; enthält `ggml-cuda.dll`, `llama-server.exe`, `llama-cli.exe` und Hilfsprogramme. |
| `C:\Users\pskra\AppData\Local\Microsoft\WindowsApps\llama.exe` | entfernt | Vom Benutzer gelöscht; nicht Bestandteil der Migration und nicht als Produktionspfad vorgesehen. |
| `C:\Users\pskra\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe` | entfernt | WinGet-Paket `ggml.llamacpp`, Installer `llama-b11046-bin-win-vulkan-x64.zip`, enthielt `ggml-vulkan.dll`. |

Die Vulkan-Variante wurde über den zuständigen Paketmanager entfernt:

```powershell
winget uninstall --id ggml.llamacpp --exact --silent
```

Die Benchmarksoftware verwendet keine PATH-Reihenfolge, sondern den expliziten
Pfad `LLAMA_CPP_SERVER_EXE` beziehungsweise die Provider-Konfiguration.

Technisch ist Vulkan nicht grundsätzlich unfähig, eine NVIDIA-GPU zu nutzen;
es verwendet jedoch nicht den CUDA-Backendpfad, der für dieses Projekt als
Referenz und für die gewünschte NVIDIA-Optimierung maßgeblich ist. Deshalb
bleibt der CUDA-Build unter `C:\Program Files\llama.cpp` die verbindliche
Produktionsinstallation.

Die frühere WindowsApps-Installation wurde aus dem System entfernt. Ihre
unklare GUI-/Router-Rolle bleibt damit bewusst außerhalb der Migration.

##### GGUF-Ablagen und GUI-Erkennung

Die llama-GUI und ihr Router sind keine verlässliche Inventarquelle für den
Benchmark. Sie können den eigenen Hugging-Face-Cache anzeigen, während
normale Publisher-/Modellordner oder bereits vorhandene lokale GGUF-Dateien
nicht in der Web-UI erscheinen.

Der direkte Provider umgeht diese Kataloggrenze und übergibt immer eine
konkrete lokale Datei an `llama-server.exe`. Der gemeinsame
`LocalModelResolver` scannt deshalb rekursiv beide Standardroots und erkennt:

```text
<root>\<publisher>\<model-folder>\<file>.gguf
<root>\models--<publisher>--<model>\snapshots\<revision>\<file>.gguf
<root>\hub\models--<publisher>--<model>\snapshots\<revision>\<file>.gguf
```

Aus dem im Screenshot gezeigten Cache wird beispielsweise
`models--ggml-org--gpt-oss-20b-GGUF\snapshots\<revision>\gpt-oss-20b-MXFP4.gguf`
als `ggml-org/gpt-oss-20b-GGUF@mxfp4` erkannt. Die Datei muss nicht in der
llama-GUI sichtbar sein. Für einen produktiven Benchmark sind der konkrete
Pfad, der GGUF-Header und die Registry-Zuordnung maßgeblich; GUI-/Router-
Kataloge und automatische Hugging-Face-Auflösung bleiben außerhalb des
Benchmarkpfads.

##### Detaillierter Migrationsablauf

**Phase A – Bestand und Registry stabilisieren**

1. [~] Alle bisher gelaufenen LM-Studio-Ergebnisse, Backups und Serverlogs
   gesichert und inventarisiert halten; die fachliche Auswertung der
   gesicherten Resultate ist noch offen.
2. [~] Den abgebrochenen SampleSize-5-Lauf bewusst pausiert lassen. Nach der
   direkten Backend-Abnahme nur die noch nicht gelaufenen Modelle gezielt mit
   llama.cpp fortsetzen oder einen vollständig dokumentierten neuen Lauf
   starten; bereits gesicherte Modelle nicht blind wiederholen.
3. [~] GLM-4.7-Flash wurde im direkten, nicht gestreamten API-Pfad mit den
   Reasoning-Formaten geprüft. Der LM-Studio-Vergleich, die REAP-Abgrenzung
   und der separate Streamingtest bleiben Teil der offenen Abnahme.
4. [ ] Für alle verwendeten Code-Benchmarks ein Task-Manifest erzeugen und die
   Worker-Kompatibilität mit identischen Aufgaben prüfen.
5. [x] Die Gemma-Registrykorrektur ist uebernommen. Der letzte Pre-Commit-
   Prueflauf meldete `registry_tool.py validate --ci`: 0 Blocker, 0 Hinweise;
   die fokussierte Registry-Suite bestand mit 112 Tests. Eine weitergehende
   Blueprint-/Gesamtvalidierung bleibt nur dann erforderlich, wenn sich die
   betreffenden Daten oder Codepfade erneut aendern.

**Phase B – llama.cpp-Parametervertrag definieren**

1. [x] Eine explizite Zuordnung Registryfeld → llama.cpp-Argument festlegen.
2. [x] Für jedes Feld definieren, ob es statisch pro Modell, pro Serverstart oder
   pro API-Request gilt.
3. [x] Nicht abbildbare Werte nicht stillschweigend verwerfen, sondern als
   Warnung oder blockierenden Exportfehler ausweisen.
4. [~] `--reasoning-format` für GLM, GPT-OSS und weitere Reasoning-Familien als
   Providerprofil testen; die nicht gestreamten GLM-Varianten sind geprüft,
   der Streamingvergleich und die abschliessende Profilentscheidung bleiben
   offen. LM-Studio-Parserwerte werden nicht automatisch kopiert.
5. [~] JSON-Schema/Grammar, Jinja-Aktivierung, Stop-Verhalten und
   multimodale Eingaben als eigene Capability-Gates behandeln. Die relevanten
   Pfade sind getrennt, aber die Modellfamilien- und Streamingabnahme ist noch
   nicht vollständig.

**Phase C – Export statt Doppelpflege**

1. [x] `registry_tool.py` um einen report-only Export für llama.cpp erweitern.
2. [x] Ein Argumentmanifest mit Modellpfad, Build-Anforderung, Startargumenten,
   Request-Defaults und Registry-Schlüssel erzeugen.
3. [x] Ein `preset.ini` für den llama.cpp-Router erzeugen; dieses gilt
   als generiertes Artefakt und nicht als zweite editierbare Quelle. Der
   öffentliche Aufruf ist `py -3.12 src/registry_tool.py preset [PATH]`;
   `export-llama-preset` bleibt ein Kompatibilitätsalias.
4. [x] Exportierte Artefakte mit Registry-Hash, llama.cpp-Version und Zeitstempel
   versehen.
5. [~] Export-Tests für GLM-4.7, GPT-OSS, Gemma und ein normales Instruct-
   Modell sind vorhanden; explizite Golden-Files für alle vier Modellfamilien
   bleiben als reproduzierbare Exportregression offen.

**Phase D – Direkten Provider implementieren**

1. [x] `src/providers/llama_cpp_provider.py` für Start, Readiness, Modelle,
   Current-Model und Stop anlegen.
2. [x] Fremde Serverprozesse nur beenden, wenn ihre PID und Startparameter dem
   eigenen Providerlauf zugeordnet werden können.
3. [x] `run_benchmarks.py` erhält einen expliziten Provider-/Client-Kontext.
4. [x] Custom, EvalPlus, LM-Eval und Agentic verwenden dieselbe Providergrenze,
   soweit ihre API-Capabilities dies erlauben.
5. [x] Globale URL- und Parallelitätsannahmen aus `run_benchmarks.py` entfernen;
   die Legacy-Symbole bleiben nur als rückwärtskompatible Test-/Integrations-
   Fassade bestehen.

**Phase E – Verifikation und Rollout**

1. [x] Mit `llama-bench.exe` Laden, VRAM-Fit und Token-Erzeugung vorprüfen.
2. [x] Einen Server-Smoke mit einem lokalen GGUF und archiviertem stdout/stderr/
   Serverlog ausführen.
3. [~] Für GLM die Reasoning-Formate `auto`, `none`, `deepseek` und
   `deepseek-legacy` im nicht gestreamten direkten API-Pfad vergleichen.
   Der separate Streaming-Vergleich bleibt offen, weil der Benchmarkpfad für
   GLM bewusst nicht streamt.
4. [x] Pro Pipeline einen SampleSize-1-Lauf ausführen.
5. [x] Einen sequenziellen Mehrmodelllauf mit Modellauswahl, Seed, Sampling,
   Kontext, Version, GGUF-Pfad und Logs archivieren.
6. [ ] Einen systematischen LM-Studio-/llama.cpp-Kompatibilitätsvergleich mit
   identischem Modell, Template, Sampling und Request durchführen und
   Unterschiede bei Stop, Reasoning, Structured Output und Tokenisierung
   getrennt ausweisen.
7. [ ] Die Warnungen und Fehler getrennt nach Launcher, Pipeline,
   llama.cpp-Server, Modellarchitektur und Chat-Template klassifizieren und
   eine Entscheidung zu verbleibenden Tokenizerwarnungen dokumentieren.
8. [ ] Erst nach bestandener technischer und fachlicher Verifikation den
   direkten SampleSize-5- beziehungsweise vollständigen Modelllauf starten.

**Abnahmekriterien**

- Kein Benchmark verwendet implizit die Vulkan-Installation.
- Jeder Lauf weist die exakte llama.cpp-Binary, Version, Build, GGUF-Datei,
  Quantisierung und die effektiven Start-/Request-Parameter aus.
- Registry-Policy und generierte Backend-Artefakte sind reproduzierbar.
- Ein INI-/Exportfehler wird vor dem Serverstart sichtbar.
- Start, Readiness, API-Aufruf, Fehlerbehandlung und Stop funktionieren für
  mindestens zwei Modelle hintereinander.
- GLM-Reasoning liefert einen unterscheidbaren finalen Inhalt und korrekt
  zuordenbare Reasoning-Metadaten.
- Alle vier Benchmark-Pipelines bestehen den SampleSize-1-Smoke.

Die technischen Kriterien sind damit weitgehend erfüllt. Die fachliche
Abnahme bleibt offen, solange der LM-Studio-Vergleich, der GLM-Streamingtest,
die Warnungsanalyse, die Worker-/Manifest-Vergleiche und eine mehrmodellige
Qualitätsauswertung fehlen.

Die derzeit geprüfte llama.cpp-Installation ist:

```text
C:\Program Files\llama.cpp\llama-server.exe
Version: 0.4.1-dev, build 11081, commit 161755f29
```

Der Pfad muss über `LLAMA_CPP_SERVER_EXE` überschreibbar sein. Der Standard-
API-Port des direkten Providers ist `http://127.0.0.1:8080/v1`; auch dieser
Wert muss konfigurierbar bleiben.

##### Verifikationsergebnisse 22.09.2026

- Der Structured-Output-Fix trennt LM Studio (`json_schema`) von llama.cpp.
  Beim direkten Provider wird generisch kein JSON erzwungen; ein explizites
  Profil verwendet `json_object`; bei `reasoning-format=none` wird die
  Grammatik deaktiviert.
- GLM-4.7-Flash Q3_K_S lief mit `auto`, `none`, `deepseek` und
  `deepseek-legacy` ohne Grammar-/Samplerfehler. Die Taskstatus waren
  `json_ok`, `fenced`, `json_ok`, `json_ok`; der einzelne DS1000-Test blieb
  bei 0 %, daher ist dies eine Infrastrukturverifikation und keine
  Qualitätsaussage.
- Der sequenzielle Mehrmodelllauf verwendete auf einem Port hintereinander
  `thebloke/em_german_leo_mistral@q4_k_m`,
  `unsloth/glm-4.7-flash@q3_k_s` und `qwen/qwen3-14b@q6_k`. Jeder Modellwechsel
  wurde im Runner sichtbar entladen; pro Modell entstand ein eigener
  Serverlog. Runner-stderr blieb leer, die Serverlogs enthielten keine
  Grammar-/Sampler-/Fehlermeldung.
- Der Preset-Export erzeugte 63 lokale Modellsektionen und meldete vier
  Registryeinträge ohne lokale GGUF-Datei. Die Datei ist ein abgeleitetes
  Artefakt unter `ergebnisse/llama-cpp-generated/preset.ini`, nicht die
  Quelle der Registry. Ein Router-Smoke mit `llama-server.exe
  --models-preset` akzeptierte alle 63 Sektionen und listete sie über
  `/v1/models`; es wurde dabei kein Modell geladen.
- Die bestehende Router-Datei wurde gesichert und mit den 63 Registry-basierten
  lokalen Modellsektionen zusammengeführt. Der env-only-Smoke über
  `C:\Program Files\llama.cpp\llama-server.exe` listete danach 65 Modelle,
  darunter die benutzerdefinierte `gpt-oss-20b`-Sektion und
  `unsloth/glm-4.7-flash@q3_k_s`. `llama.exe server` ist dafür nicht der
  freigegebene Produktionspfad; der direkte Provider verwendet ausdrücklich
  `llama-server.exe`.
- Die llama.cpp-HF-Cache-Prüfung wurde um Projektoren erweitert: Dateien und
  Einträge mit `mmproj` in Pfad, Dateiname oder Modell-ID werden als
  multimodale Hilfsartefakte behandelt. Für Millie ist der Hauptschlüssel
  `llmsforall/millie-35b-a3b-11gb@?` mit `experts: 64` und `max_experts: 256`
  dokumentiert; der Projektor bleibt separat.
- Ein frueherer fokussierter Testlauf mit 233 bestandenen Tests ist als
  historischer Zwischenstand zu verstehen. Beim letzten Commit-Check bestanden
  die fokussierten Registry-Tests mit 112 Tests; `validate --ci` meldete
  0 Blocker und 0 Hinweise. Gemma APEX ist mit `experts: 36` und `@mini`
  eingetragen. Die LM-Studio-/llama.cpp-Abnahme bleibt davon unabhaengig offen.

##### Ausgeschlossene WindowsApps-Installation

Die frühere `C:\Users\pskra\AppData\Local\Microsoft\WindowsApps\llama.exe`
war eine separate GUI-/Router-Installation mit ungeklärter Modell- und
Lifecycle-Verantwortung. Sie wurde vor Beginn dieser Migration gelöscht und
ist damit kein Backend, kein Fallback und kein Testziel. Produktiv bleibt
ausschließlich `C:\Program Files\llama.cpp\llama-server.exe`.

##### Verantwortungsgrenzen und Datenhoheit

| Bereich | Verbindliche Quelle | Rolle im neuen Workflow |
| --- | --- | --- |
| Modell-Datei | lokales GGUF unter dem gemeinsamen GGUF-Root | `llama-server.exe --model` erhält den konkreten lokalen Pfad |
| Modellbeschaffung | explizit bereitgestellte lokale GGUF-Datei | Kein automatischer Hugging-Face-Download und kein impliziter GUI-Cache im Benchmarkpfad |
| Architektur, Quant, native Grenzen | GGUF-Header und Dateiname | read-only technische Fakten für Registry und Resolver |
| Benchmark-Policy | `doc-git/model_registry.yaml` | Runtimewerte, Sampling, Reasoning und Modellidentität |
| Prompt-/Template-Policy | `blueprint_definitions.yaml` und Template-Dateien | providerneutrale Prompt- und Stop-Policy |
| Parameterexperimente | LM-Studio-GUI und LM-Studio-Config-JSONs | Mess- und Tuning-Arbeitsplatz, nicht dauerhafte Runtime-Quelle |
| Benchmark-Inferenz | direkter llama.cpp-Server | einziges produktives lokales Backend |
| Ergebnisse und Logs | `ergebnisse/` | Laufdaten, stdout/stderr, Serverlogs und Auswertung |

LM-Studio-JSONs bleiben Runtime-Artefakte. Ihre Werte dürfen nur über einen
expliziten und überprüfbaren `registry_tool.py`-Schreibpfad in die Registry
übernommen werden. Ein normaler Registry-Sync darf keine stillen Rückschreibungen
oder Überschreibungen auslösen.

##### Zielworkflow für Modellparameter

1. GGUF-Datei im gemeinsamen Modellroot bereitstellen und mit `registry_tool.py`
   entdecken, technisch prüfen und unter `publisher/model@quant` einordnen.
2. Dasselbe GGUF bei Bedarf in LM Studio laden, um `context_length`, K-/V-KV-
   Quantisierung, Unified KV Cache, GPU-Offload, Parallelität und VRAM-Verbrauch
   praktisch zu testen.
3. Einen stabilen Parameterstand mit einem kleinen reproduzierbaren Test prüfen;
   GUI-Werte und LM-Studio-Config-JSON dabei nur als Beobachtung bzw. Quelle
   für einen ausdrücklich angeforderten Import verwenden.
4. Die bestätigten Werte mit dem passenden expliziten `registry_tool.py`-Pfad
   in `model_registry.yaml` übernehmen und anschließend `validate --ci` sowie
   die fokussierten Registry-Tests ausführen.
5. `run_benchmarks.py` liest danach ausschließlich die lokale Registry-Policy
   und übersetzt sie in llama.cpp-Start- und Request-Parameter.

Der Workflow trennt damit experimentelles Tuning von reproduzierbarer
Benchmarkausführung. Ein späteres Update der llama.cpp-Binary ändert nicht
automatisch die Registrywerte; die Parameter müssen nach einem Backend-Update
gezielt erneut validiert werden.

##### Umsetzungsphasen

1. **Direkten Provider definieren**

   - [x] Die unabhängige Binary unter `C:\Program Files\llama.cpp` und ihre
     CUDA-Erkennung mit `--version` und `--help` prüfen.
   - [x] Die WindowsApps-CLI wurde aus dem Scope entfernt; ein Test gegen
     Hugging-Face-/Router-Pfade ist nicht Teil der Migration.
   - [x] Version, Build, Commit, Modellpfad, Port und Logpfad des verbindlichen
     CUDA-Backends werden für jeden direkten Lauf reproduzierbar erfasst.
   - [x] `src/providers/llama_cpp_provider.py` als klar benannten Provider
     anlegen; `unsloth_server_provider.py` nicht als neue Zielarchitektur
     weiterführen, sondern nur für Kompatibilität oder Migration erhalten.
   - [x] Provider-Konfiguration für `LLAMA_CPP_SERVER_EXE`, `LLAMA_CPP_API_BASE`,
     `LLAMA_CPP_MODEL_ROOT` und einen eigenen Logpfad festlegen.
   - [x] Start, Readiness, Current-Model, Stop und Fehlerzustände im
     Provider-Lifecycle kapseln. Ein fremder Serverprozess darf nicht ohne
     ausdrückliche Konfiguration beendet werden.

2. **Registry-Runtime in llama.cpp-Argumente übersetzen**

   - [x] `context_length` auf `--ctx-size` abbilden und native GGUF-Grenzen
     weiterhin fail-closed prüfen.
   - [x] `k_cache` und `v_cache` auf `--cache-type-k` und `--cache-type-v`
     abbilden; `useUnifiedKvCache` nur übernehmen, wenn die aktuelle Binary
     die dafür vorgesehene llama.cpp-Option unterstützt.
   - [x] Registry-Sampling und Reasoning-Policy in Request- bzw. Template-
     Parameter überführen; keine zufälligen GUI-Defaults des Servers verwenden.
   - [~] Für direkte llama.cpp-Aufrufe `--reasoning-format` als explizite
     Provider-Option modellieren. `none`, `deepseek` und `deepseek-legacy`
     sind für GLM-4.7 im Nicht-Streamingpfad verglichen; der separate
     Streamingvergleich und die abschliessende Auswahl bleiben offen. Die
     Auswahl darf nicht stillschweigend aus dem LM-Studio-Reasoning-Parser
     übernommen werden.
   - [x] Prüfen, ob `llama-server.exe` dieselbe Reasoning-Format-Option wie
     `llama-cli.exe` anbietet und wie sie in der OpenAI-kompatiblen API die
     Felder `message.content` und `message.reasoning_content` beeinflusst.
   - [x] Provider-Optionen wie GPU-Layer, Flash Attention, Jinja, Parallelität,
     Batch- und Offload-Regeln als expliziten Vertrag abbilden und durch den
     `llama-server.exe --help`-Vertrag prüfen; sie werden nicht aus bloßen
     Modellnamen abgeleitet.

3. **Runner auf expliziten Provider-/Client-Kontext umstellen**

   - [x] `run_benchmarks.py` erhält einen konkreten Client-Kontext statt einer
     global importierten `API_BASE`.
   - [x] Alle Pipelines (Custom, EvalPlus, LM-Eval und Agentic) beziehen ihre
     Base-URL und Authentifizierung aus diesem Kontext.
   - [x] `model_manager.py` bleibt Factory und Kompatibilitätsfassade, ist aber
     nicht mehr die versteckte Quelle für providerabhängige URL-Annahmen.
   - [x] Chat- und Text-Completions bleiben capability-gesteuert; ein Provider
     darf nicht stillschweigend so behandelt werden, als unterstütze er beide.
   - [x] `num_parallel` wird durch Provider-Capabilities und optional einen
     Registry-Wert begrenzt. Die aktuelle Policy wünscht bei
     `SampleSize <= 5` genau 1 und sonst 4 parallele Anfragen; die
     Provider-Capability darf diesen Wert weiter reduzieren.

4. **Registry- und LM-Studio-Workflow entkoppeln**

   - [x] Modellauflistung und GGUF-Auflösung für den direkten Provider über den
     gemeinsamen `LocalModelResolver` führen; die Benchmarkauswahl darf nicht
     von einer aktuellen LM-Studio-Serverliste abhängen.
   - [~] `registry_tool.py` so erweitern oder präzisieren, dass der Import von
      LM-Studio-Testwerten für `context_length`, K-/V-Quantisierung, UKV und
      MoE-`experts` explizit, nachvollziehbar und feldweise kontrolliert
      erfolgt. Kontext- und Expertenwerte können bereits gezielt importiert
      werden; die Gesamtpruefung der Feldhoheit fuer K-/V-Quantisierung, UKV
      und providerabhaengige Werte steht noch aus. Die Gemma-Daten sind geklaert.
   - [~] Providerneutrale Registry-Felder von reinem LM-Studio-Runtimezustand
     trennen. Die Grundgrenze ist dokumentiert, die vollständige Feldmatrix
     für llama.cpp, LM Studio und künftige Provider bleibt zu prüfen. Nicht
     jeder GUI-Wert darf als llama.cpp-Policy gespeichert werden.
   - [x] Hilfe und Dokumentation auf den neuen Ablauf umstellen: LM Studio
     optimiert, `registry_tool.py` schreibt nach Review, llama.cpp benchmarked.

5. **Verifikation und Vergleichbarkeit**

   - [x] Mit `llama-bench.exe` einen technischen Preflight für
     `thebloke/em_german_leo_mistral@q4_k_m` ausführen. Build 11081 meldet
     CUDA und die RTX 5060 Ti mit 16 283 MiB; stdout, stderr, Version und
     Geräteliste liegen unter `ergebnisse/llama-cpp-pipeline-smoke-20260921/`.
   - [x] Einen direkten llama.cpp SampleSize-1-Smoke für Custom/DS1000,
     EvalPlus/HumanEval+, LM-Eval/ARC-Challenge und Agentic mit festem Modell,
     Seed 42, Kontext-/Sampling-Registrywerten und getrennten Logs ausführen.
     Alle vier Pipelines beendeten den Lauf; DS1000 und HumanEval+ erzielten
     im Einzelfall 0 %, ARC-Challenge 0 und Agentic 0. Der Lauf ist damit ein
     Lifecycle-/API-Smoke, kein Qualitätsbaseline.
   - [ ] Einen LM-Studio/llama.cpp-Vergleich nur als Backend-Kompatibilitäts-
     test durchführen; Unterschiede bei Template, Stop-Parsing, Reasoning,
     Structured Output, Tokenisierung und Serverversion separat ausweisen.
   - [~] Für GLM-4.7 einen nicht gestreamten A/B-Test mit `--reasoning-format auto`,
     `deepseek`, `deepseek-legacy` und `none` durchführen und jeweils
     finales JSON bzw. Code sowie Reasoning-Metadaten prüfen; dieser Teil ist
     abgeschlossen, ein separater Streaming-Test bleibt bewusst offen.
   - [x] Danach den technischen Mehrmodelllauf sequenziell über `llama-server.exe`
     ausführen. Für jedes Modell werden Startargumente, Serverversion, GGUF-
     Pfad, Registry-Schlüssel, stdout, stderr und Serverlog archiviert.
   - [ ] Fehler und Warnungen getrennt nach Launcher, Pipeline, llama.cpp-
     Server, Modellarchitektur und Chat-Template analysieren; dabei die
     `special_eot_id`-/`special_eom_id`-Warnungen fachlich einordnen.

6. **Abnahme und laufende Pflege**

   - [x] Provider-, Registry- und Runner-Tests mit einer Fake-`llama-server`
     bzw. HTTP-Testdoppelung ohne echte VRAM-Last ausführen.
   - [x] Einen echten lokalen Server-Smoke mit der installierten Binary und
     einem lokalen GGUF durchführen. Der vollständige Einmodell-Pipeline-Smoke
     und der technische sequenzielle Mehrmodelllauf sind abgeschlossen.
   - [ ] Nach jedem llama.cpp-Update `--version`, `--help`, `llama-bench`,
     einen Modell-Smoke und die Registry-/Template-Tests wiederholen.
   - [x] Die Zielarchitektur in `doc-git/Architecture, Flow & ChangeLog_en.md`
     und README um den direkten Provider und die beiden GGUF-Ablagen ergänzen.

##### Bewusste Nichtziele

- Unsloth Studio wird nicht als zusätzlicher Lifecycle- oder Inferenz-Proxy
  in den Runner eingebaut.
- LM Studio wird nicht zur produktiven Benchmark-Quelle für aktuelle
  Modellzustände erklärt.
- `llama-bench.exe` ersetzt keine fachlichen Coding-, Math- oder Agentic-
  Benchmarks.
- Ein Binary-Update wird nicht automatisch als Beweis für identische Scores,
  Templates oder Runtimeparameter behandelt.
- API-, GUI- und Serverparameter werden nicht ungeprüft vermischt; jede
  dauerhafte Übernahme erfolgt über die Registry und die bestehenden Gates.
- Der LM-Studio-Menüpunkt „llama.cpp Arguments Override“ ist ein lokales
  Diagnose- und Tuningwerkzeug. Seine Werte sind weder automatisch
  Registrywerte noch ein Beleg dafür, dass die direkte llama.cpp-Binary
  dieselben Defaults verwendet.

### Benchmark- und Qualitaetsverifikation

- [ ] Task-Manifeste fuer die tatsaechlich verwendeten Code-Benchmark-Datensaetze erzeugen und auffaellige Aufgaben vor dem naechsten Referenzlauf bewerten.
- [ ] SampleSize-1-Smoke der Workerpfade ausfuehren; der bereits erfolgreiche
  direkte llama.cpp-Pipeline-Smoke ersetzt diese Worker-Abnahme nicht.
- [ ] Gepaarte Kompatibilitaetslaeufe vor/nach der Import-Blockaden-Entfernung mit identischem Manifest ausfuehren.
- [ ] Manifest- und Worker-Funktionen mit Ruff, Python-3.12-Syntaxcheck und fokussierten Pytest-Tests verifizieren.
- [ ] Die fachliche Qualitaet ueber mehrere geeignete Modelle und die
  Kategorien Coding, Math und Agentic mit festgelegten Sampling- und
  Reasoningprofilen auswerten; technische Smoke-Scores nicht als
  Qualitaetsbaseline verwenden.
- [ ] Den strengen mypy-Bestand systematisch bereinigen. Die zuletzt bekannte
  Groesse lag bei 105 Meldungen; vor dem Abbau den aktuellen Scope neu
  erfassen und die Fehler in fokussierten Gruppen beheben.
- [ ] Nach Abschluss die Ergebnisse, die Entscheidung zur Score-Neutralitaet
  und die Abgrenzung zum pausierten SampleSize-5-Lauf in `ergebnisse/`
  dokumentieren.

### Abgeschlossener Plan: konfigurierbarer GGUF-Modellroot

Ziel war eine reproduzierbare Modell-Dateiaufloesung, die den neuen
dedizierten Modellroot bevorzugt, bestehende Installationen mit dem alten
LM-Studio-Pfad weiterfindet und Windows-Junctions nicht doppelt bewertet.

Umsetzung:

1. `src/model_paths.py` definiert die zentrale Root-Reihenfolge. Standardmaessig
   gilt `D:\LLM-Modelle\models` vor `~\.lmstudio\models`.
2. `GGUF_MODEL_ROOT` ist der provider-neutrale Einzelroot-Override;
   `UNSLOTH_MODEL_ROOT` und `LMSTUDIO_MODELS_DIR` bleiben kompatibel.
3. `LocalModelResolver`, `registry_tool.py`, `run_benchmarks.py` und der
   Unsloth-Provider verwenden dieselbe Aufloesung. Bei identischer Modell-ID
   gewinnt der erste Root; kanonische Pfade deduplizieren Junction-Treffer.
4. Der bestehende `MODELS_CACHE`-Anker bleibt fuer isolierte Registry-Tests
   erhalten, waehrend die Standardpfade automatisch mehrroot-faehig sind.
5. README und Architektur-Dokumentation beschreiben Prioritaet, Override,
   Fallback und Junction-Verhalten.

Verifikation: fokussierte Resolver-Tests, Python-3.12-Syntaxpruefung, Ruff
und anschliessend die Registry-/Gesamttests werden nach der Dokumentations-
und Integrationsaenderung erneut ausgefuehrt.

## Verifikation vor Commit

```powershell
py -3.12 -m pytest tests\test_task_manifest.py tests\test_sandbox_worker.py tests\test_custom_benchmark_io.py -q --basetemp=.pytest-temp
py -3.12 -m ruff check src\task_manifest.py src\prepare_task_manifests.py src\sandbox_worker.py tests\test_task_manifest.py tests\test_sandbox_worker.py
py -3.12 -m py_compile src\task_manifest.py src\prepare_task_manifests.py src\sandbox_worker.py
py -3.12 src\registry_tool.py validate --ci
```

Bei Backendänderungen folgt ein SampleSize-1-Smoke mit dem produktiven
`llama-server.exe`; LM Studio wird nur für den separaten
Kompatibilitätsvergleich gestartet. Der grössere direkte SampleSize-5-Lauf
bleibt bis zur fachlichen Abnahme pausiert.
