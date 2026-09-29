# Registry-, Runtime- und KV-Nachreview vom 29.09.2026

Basis sind die Befunde R01–R13 und der abgeschlossene Bericht
`Code-Review_registry_Fixes_2026-09-29.md`. Dieser Bericht ergänzt die späteren
Benutzerentscheidungen und den erneut geänderten Modellbestand. Neue GPU-Läufe,
Modellladeaufrufe und Generierungen wurden ausdrücklich ausgeschlossen.

## Ergebnis der Änderungen

- Der tatsächlich ausgeführte `py -3.12 src/registry_tool.py sync` führt nach elf
  Neuzugängen und acht archivierten Löschungen 61 Registry-Einträge. Dazu gehört
  die Löschung des jrell-Qwen3.8-Modells. Keine externe JSON wurde verschoben oder
  gelöscht; historische Registry-Einträge und Dateisicherungen bleiben lokal.
  Der abschließende frische Inventarabgleich archivierte außerdem den inzwischen
  gelöschten Intel-Qwen3.5 und Tiel-Coder. Physisch vorhandene Modelle mit
  abweichendem LMS-Index bleiben erhalten.
- Millie ist `llmsforall/millie-35b-a3b-11gb@q2_sym32k4`. Die gemeinsamen Resolver
  verlangen Publisher `llmsforall`, Dateityp 56 und tatsächliche Tensor-Typen 56.
  Der reale Header enthält außerdem Typ 55 und F32-Tensoren. Die mittlere
  Gewichtsdichte ist keine Standard-Q2-/Q3-Quantisierung. `fill-quant` korrigiert
  auch `@?`; ein folgender Sync/JSON-Import behält genau eine vollständige Identität.
  Millie benötigt weiterhin den Publisher-Fork; eine vollständige Registry-ID
  bestätigt keine Kompatibilität mit dem installierten Standardbackend.
- `speculative_policy: disabled` hält Byteshapes Qwen3.8 dauerhaft ohne Helper.
  `registry` erhält ausdrücklich ausgewählte Helfer trotz abweichender GUI-Werte;
  die bisherige Ableitung bleibt als Standard `lmstudio` erhalten. Gespeicherte
  JSON-Felder schalten alle fünf Algorithmen eindeutig um; der llama.cpp-Preset
  enthält für den deaktivierten Fall `spec-type = none`.
- Gemma REAP126 mit dem Unsloth-MTP-Q8_0 und Muse NVFP4 mit Anbeeld-Muse-DSpark
  sind an vorhandene erfolgreiche LM-Studio-Logabschnitte, genaue Dateipfade und
  aktuelle Header-Fingerprints gebunden. Draft-Tokens wurden in diesen historischen
  Läufen akzeptiert. Dateimodifikationszeiten liegen vor den Läufen. Die Logs
  enthalten keine damaligen Dateihashes; diese historische Einschränkung bleibt
  in den lokalen Evidenzdateien dokumentiert. Das bestätigt die dort beobachtete
  LM-Studio-Paarung, nicht einen neuen Test mit standalone llama.cpp.
- Muse verwendet `muse_reasoning_low`, ein Gesamtbudget von 8192 und ein
  Reasoning-Budget von 512 Tokens. Das tatsächliche GGUF-Template erwartet
  `reasoning_strength`; die abgeleitete Template-Datei ändert ausschließlich
  dessen Default von `high` auf `low`. Request-Kwargs, Blueprint-Systemprompt,
  JSON-Template, Reasoning-Parser und gespeicherte Budgets wurden überprüft.
  Explizite Blueprints überleben die Klassifikation über `blueprint_policy: registry`.
- Streaming verarbeitet reine Usage-Chunks mit `choices=[]`, verlangt
  `stream_options.include_usage`, zählt gemeldete Completion-Tokens einschließlich
  Reasoning genau einmal und besitzt eine absolute Deadline. Der bisherige
  Default von 120000 Sekunden ist auf 120 Sekunden korrigiert. Socket-Abbruch,
  Budgetüberschreitungen in Streaming/Nonstreaming/HTTP-Providern und die äußere
  Benchmark-Retry-Schleife teilen den terminalen Fehlervertrag. Budget-/Timeoutfehler
  starten keine weitere vollständige Generation. Ohne laufende Server-Usage oder
  Token-IDs lässt sich der genaue Abbruch beim 8192. Token clientseitig nicht beweisen.

Die Assembly hat zunächst 53 eindeutig gebundene JSON-Dateien gesichert,
geschrieben und ihre Systemprompts geprüft. Zwei während des Abschlusses neu
gespeicherte Configs wurden separat gesichert und mit denselben Resolvern
assembliert; der frische Endbestand enthält 54 geprüfte Systemprompts.
Die vollständig gebundenen gespeicherten Expertenwerte 18 für Byteshape
Qwen3-30B-A3B und 32 für FreedomAISVR GPT-OSS wurden übernommen und vom Benutzer
ausdrücklich bestätigt. Alle aktuellen Qwen3-30B-A3B-Profile verwenden 18,
alle GPT-OSS-Profile 32. Zwei fehlende GPT-OSS-Harmony-Templates wurden aus
der vorhandenen Blueprint-/Registry-Policy ergänzt und in den JSONs geprüft.
Für sieben Registry-Einträge existiert
keine eindeutige Config-Bindung; zwei davon sind ausgeschlossene F2LLM-Embedding-
Einträge. Die tatsächliche `$HOME/.config/llama.cpp/preset.ini` wurde mit
`preset --merge-existing` aktualisiert: 57 Modellabschnitte, erhaltene globale
und manuelle Abschnitte, vier explizit ausgelassene Profile. Lokale Registry,
Preset und JSONs bleiben maschinenbezogene, nicht veröffentlichte Dateien.

## KV-Cache-Evidenz

Der Vergleich betrifft den installierten LM-Studio-CUDA12-Backend 2.47.0
(llama.cpp b11235, CUDA 12.8) und standalone llama.cpp b11177 (CUDA 13.4).
Beide lokalen `ggml-cuda.dll` enthalten die Build-Matrix
`q4_0-q4_0,q8_0-q8_0,f16-f16,bf16-bf16`. Die fünf gemeldeten Kombinationen
`q5_1/q5_1`, `q5_1/q4_1`, `q5_1/q4_0`, `q5_0/q4_0`, `q8_0/q5_1` fehlen darin.
Vorhandene standalone-Logs enthalten dieselbe F16-Konvertierungswarnung.

Reproduzierbare Binärnachweise: standalone-DLL SHA-256
`4fa561a2b764a25e1a99b94335440d203631492123a6fec9d0e6a5503e56f3e5`,
LMS-CUDA12-DLL SHA-256
`c046cd33e5119575041019e26992a44ef16c5aa07836be1e5cdbb87cdab619d3`.
Der Matrix-String steht an den Byte-Offsets 12120168 beziehungsweise 14228848.
LMS weist seine Basis als `6c7a87f-dirty` aus: der Commit bezeichnet die
Upstreambasis und beschreibt nicht sämtliche lokalen Backend-Anpassungen.
Die Strings sind Build-Matrix-Indizien; ein tatsächlicher Kernel-Durchlauf
wurde nicht beobachtet.

Die [FA-Implementierung im LM-Studio-Upstream-Stand](https://github.com/ggml-org/llama.cpp/blob/6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17/ggml/src/ggml-cuda/fattn.cu)
und die [Build-Einstellungen des standalone-Stands](https://github.com/ggml-org/llama.cpp/blob/1ab7e5ad2d4e7295c94c3b966a3e0b70fa365865/ggml/CMakeLists.txt)
belegen die Typauswahl: CUDA-Version allein bestimmt sie nicht.
`GGML_CUDA_FA_QUANTS` ist eine Compile-Einstellung; ein Registry- oder
Umgebungsvariablenwechsel ergänzt keine bereits installierten Kernels.

`q8_0/q8_0` ist für beide Builds in dieser Matrix enthalten. Die vom Benutzer
beobachtete höhere Geschwindigkeit wurde hier mangels autorisiertem GPU-Test
nicht neu gemessen. `q4_nl` wird im Projekt zu `iq4_nl` normalisiert; dieser Typ
ist nicht in der Vector-FA-Matrix. Warnungsfreiheit bei `q5_1/iq4_nl` beweist
daher keinen nativen Vector-Kernel. Andere Ausführungspfade und die nur einmalige
Warnung pro Prozess müssen bei einer späteren Messung berücksichtigt werden.
Nur exakt gebundene vorhandene GUI-Cache-Werte wurden importiert; Kontext und
Offload wurden nicht pauschal vergrößert.

## Unabhängiger Code-Review

Reviewer: separater Agent `/root/aux_types`, 29.09.2026. Scope: die neuen
Identitäts-, Policy-, Assembly-, Template-, Budget- und Load-Verträge; frühere
R01–R13-Fixes besitzen ihren eigenen abgeschlossenen Review-Nachweis.

Der Review reproduzierte zwei zusätzliche P2-Lücken: Die ausdrückliche
Speculation-Policy erreichte die tatsächliche LM-Studio-Ladegrenze zunächst
nicht; außerdem konnten numerische Aliaswerte durch `False == 0` beziehungsweise
`True == 1` als Bool-Evidenz gelten. Beide sind korrigiert. Die Ladeprüfung
transportiert den erwarteten Vertrag intern, prüft Echo und exakt gebundene
Instanz-Konfiguration und lehnt widersprüchliche oder fehlende Effective-Evidenz
ab. Es werden keine undokumentierten REST-Load-Parameter erfunden.

Die [Native-REST-Load-Dokumentation](https://lmstudio.ai/docs/developer/rest/load)
belegt keine Speculation-Overrides. Fehlen im tatsächlichen Backend die
Effective-Felder, bleiben ausdrücklich vorgegebene Policies für Load/Reuse
blockiert. Gespeicherte Default-JSONs allein beweisen keinen bereits laufenden
Modellzustand. Das Standardverhalten ohne ausdrückliche Policy bleibt erhalten.

Abschluss-Nachreview: **PASS**, 107 fokussierte Offline-Tests bestanden,
einschließlich 36 LMS-Policy- und 15 Runtime-/Assembly-Tests; keine weiteren
belegten neuen P1-/P2-Codebefunde im Scope. Die lokale Einsatzfreigabe bleibt
gesondert offen: Bonsai/Qwen3.8-DSpark hat passende Struktur, aber keine belegte
konkrete Zielpaarung; das neue Gemma-31B-Profil besitzt keine freigegebene
Helper-Datei. Die vollständige lokale Validierung meldet zwei blockierende
Companion-Verträge und 19 Hinweise zu fünf fehlenden Configs und vierzehn
Kontextabweichungen. Expert-/Header-/Config-Paarungsfehler sind geschlossen.
Diese Datenverträge werden nicht für einen grünen
Commit-/CI-Status abgeschwächt.

Lokale Nachweise liegen unter `backups/`: Sync-, Validierungs-, Assembly- und
Preset-Protokolle, `user_profiles_reconciliation_20260929.json`,
`user_assembly_verification_20260929.json` sowie
`pairing_lms_user_updates_20260929/`. Das unveränderte vollständige Review-Gate
bestand mit 1501 Tests, Ruff, Vollbaum-mypy ohne Fehler und 56 überprüften
GGUF-Einträgen ohne Abweichung. Der Pre-Commit-Hook bestand mit 174 fokussierten
Tests. Die zusätzliche unabhängige Abschlussprüfung der Ownership-Regeln und
isolierten GPT-OSS-Fixtures bestand mit 178 Tests ohne neue P1-/P2-Befunde.
Die statische Registry-Prüfung meldet null Blocker; die zwei oben genannten
lokalen Companion-Blocker bleiben davon getrennt.

## Remote-CI und private Registry

Der erste Linux-CI-Lauf für Implementierungscommit `85741533` bestand Lint
und Typecheck, meldete aber sieben Testfehler: vier Reasoning-Tests und ein
Gemma-Template-Test lasen implizit die private Registry; der Ownership-Test
öffnete sie zwingend; der Sync-Reihenfolgetest setzte ihre Existenz voraus.
Die inzwischen ignorierte maschinenbezogene Registry ist auf GitHub abwesend.

Diese Tests verwenden jetzt eigene Registry-/Template-Fixtures und prüfen
weiterhin die echten Resolver und ursprünglichen Assertions. Eine versionierte
Ownership-Fixture prüft alle aktuellen Top-Level-Felder; lokal werden vorhandene
private Zusatzfelder weiterhin geprüft. Produktionsregeln und Testausschlüsse
wurden nicht verändert. Die sieben betroffenen Tests wurden nicht übersprungen.
20 fokussierte Tests bestanden. Ein separater Git-Quellcode-Snapshot ohne
private Registry bestand mit 1497 Tests und vier bestehenden Skips. Der
anschließende Push wiederholt alle Hooks und wird auf GitHub erneut geprüft.
Unabhängiger Nachreview `/root/aux_types`: PASS, keine neuen P1-/P2-Befunde;
die 20 fokussierten Tests wurden sowohl im Arbeitsbaum als auch im Snapshot
ohne private Registry unabhängig bestanden.

Der folgende Linux-CI-Lauf und CodeQL für `ad36df87` bestanden. Der Windows-
Testjob meldete ausschließlich die Cache-Refresh-Fixture: zwei sofortige
gleich große GGUF-Schreibvorgänge können denselben Änderungszeitstempel liefern.
Der Cache-Vertrag verwendet Pfad, Größe und `mtime_ns`. Die Fixture setzt und
prüft nun explizit einen geänderten Zeitstempel und behält die ursprünglichen
True-/False-Assertions bei. Kein Sleep, Cache-Reset oder Produktionswechsel.
34 Header-/Runtime-Tests bestanden; unabhängiger Nachreview: PASS, Einzeltest
ebenfalls bestanden. Abschließende Remote-Prüfung folgt für diesen Fix.
