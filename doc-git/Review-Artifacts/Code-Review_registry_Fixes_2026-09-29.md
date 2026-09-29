# Folgereview: Registry, Namespace-Auswertung und lokale Abnahme

Stand: 29.09.2026. Referenz ist der Fix-/Review-Bericht vom 28.09.2026
`Code-Review_registry_Fixes_2026-09-28.md`. Geprüft wurde der aktuelle Arbeitsbaum
auf `main`, Basis `5fe026bfa8a022676043d664a4d57442bf09d34d`, einschließlich der
begonnenen R01–R12-Fixes. Der Arbeitsbaum enthält außerdem erhaltene fremde
Dokumentänderungen und Löschungen. Kein Commit und kein Push wurden ausgeführt.

## Ergebnis

R13 ist behoben. Der Vollbaum-Typecheck fällt von 119 Fehlern auf null
(`python -m mypy .`, 51 Quelldateien). Die erneute unabhängige Code-Review hat
zusätzliche Identitäts-/Companion-Lücken aufgedeckt; diese sind korrigiert und
durch Regressionen abgesichert. Für die überprüften Code-Verträge bestehen
keine offenen P1-/P2-Befunde. Die lokale Freigabe einzelner Modelle bleibt
wegen der unten aufgeführten Datei-, Identitäts- und Backend-Fälle offen.

## Plan und Umsetzung

| Schritt | Änderung und Abnahmekriterium | Ergebnis |
| --- | --- | --- |
| 1 | Aktuelle Inventare prüfen, Registry sichern, vorhandene Modelle synchronisieren und gelöschte Einträge mit Policy archivieren | Umgesetzt; 58 aktive Registry-Einträge |
| 2 | R13 korrigieren; richtige und falsche Namespace-Ausgaben einschließlich Setup-Mutation im tatsächlichen Windows-Worker prüfen | Umgesetzt; 43 zusätzliche Regressionen |
| 3 | 119 Vollbaum-Typecheck-Fehler mit präzisen Typen, Rückgabeverträgen und Guards korrigieren | Umgesetzt; null Fehler, keine gelockerten Typregeln |
| 4 | Identitäts- und Companion-Verträge unabhängig nachprüfen, neue Fehler korrigieren, aktuelle Paarungen real testen | Code korrigiert; vier Pairings bestanden, zwei Backend-Ladefehler |
| 5 | Gesamtsuite, statische Registry, Ruff, Git-Diff und echte lokale Hooks prüfen | Bestanden: 1.414 Tests, Pre-Commit, Commit-Message und Pre-Push |

## Code-Verträge und Regressionen

### R13: Namespace-Fallback

`src/custom_benchmark.py` übergibt `should_capture_state` an den Sandbox-Builder.
`src/sandbox_worker.py` erfasst den Setup-Zustand im selben Prozess unmittelbar
vor dem Referenz-/Kandidatencode. Der Vergleich schließt echte Setup-Werte aus,
ohne anschließend erzeugte Ergebnisse versehentlich auszuschließen; Änderungen
an Setup-Werten bleiben erkennbar.

Begrenzte Textvorschauen dienen nur der Diagnose. Gleichheit verwendet vollständige
typisierte Zustands-Hashes: Python-Container, NumPy-Arrays sowie Pandas-Tabellen,
Series und Indizes einschließlich ihrer Struktur und Metadaten. Lange gemeinsame
Präfixe oder abgekürzte wissenschaftliche Darstellungen können keine falschen
Ausgaben bestätigen. Nicht unterstützte oder zyklische Werte bleiben geschlossen.
43 zusätzliche Fälle prüfen positive Ergebnisse, fehlende/falsche Ausgaben,
Setup-Mutation, versteckte Array-/DataFrame-Unterschiede und unprüfbare Werte.

### Zusätzliche Befunde der unabhängigen Review

- **Identitätsverlust in `fill-quant`:** Publisherlose Heuristiken konnten eine
  bestehende Registry-Policy auf ein fremdes Modell übertragen. Die Migration
  benötigt jetzt die eindeutige physische Publisher-/Modell-/Quant-Identität
  über den vorhandenen Resolver und `IdentityLink`; LMS-only-Quantisierung ohne
  GGUF-Evidenz, Mehrdeutigkeit und Kollisionen bewirken keine Migration.
- **Verlust frischer Pairing-Evidenz beim Sync:** Der Sync erhält ein erfolgreiches
  Pairing nur bei unveränderten Typ-/Methoden-/Modus-/Dateibindungen und frischen
  Fingerprints. Veränderte Dateien oder Profile können keinen alten Nachweis erben.
- **Ungeprüftes integriertes MTP:** Ein gesetztes Profil genügt nicht. Die aktuelle
  Hauptdatei muss eine ausführbare GGUF mit gültigem NextN-Layer-Vertrag und den
  tatsächlich benötigten Projektions-/Norm-Tensoren enthalten.
- **Unklassifizierte Helper-Profile:** Nichtleere Profile ohne Typ und unvalidierte
  direkte Draft-Pfade blockieren. Ein leerer optionaler Provider-Block bleibt erlaubt.
- **DFlash-/DSpark-Layergrenze:** Zielindizes müssen innerhalb der Decoder-Layer
  liegen; angehängte NextN-Layer zählen nicht als Ziel-Decoder. Ungültige Zahlen
  und boolesche Werte werden abgewiesen. Acht zusätzliche Fälle sichern dies ab.
- **Scope gespeicherter Inventare:** Eine geprüfte GGUF-Liste begrenzt den Scan
  auf ihre verifizierten Roots. Fehlende Dateien, neue nicht aufgeführte Dateien,
  fremde Roots, Duplikate und ungültige Snapshot-Strukturen blockieren frühzeitig.

Die neuen Snapshot-CLI-Flags werden in `--help` erklärt und durch 14 Tests
geprüft. Neun zusätzliche Sync-/Identity-Tests verwenden echte kleine GGUF-Fixtures
und dateigebundene Pairing-Nachweise.

### Typechecks und Testisolation

Die Typkorrekturen betreffen Registry-CLI, Launcher, Assembly, Custom-Benchmark
und den lokalen ignorierten Embedding-Runner. Rückgabewerte und JSON-/YAML-Daten
werden vor Gebrauch eingegrenzt; Subprozess-Streams und Ergebnisobjekte besitzen
passende Verträge. Der Embedding-Runner bleibt unveröffentlicht. Seine optionalen
Backend-Pakete wurden nicht installiert oder als real ausgeführt behauptet.

Die CLI-Fallback-Tests in `tests/test_model_manager.py` mocken außerdem die Native-API.
Ein parallel vom Benutzer betriebenes LM Studio beeinflusst diese Unit-Tests nicht.
Der Pre-Commit-Hook verwendet `python -m ruff` und damit denselben Interpreter
wie Syntax-/Formatdatei-Prüfungen. Es wurden keine Gate-Regeln abgeschwächt.

## Aktualisierte lokale Registry

Verwendete Quellen sind die ausdrücklich bereitgestellten Dateien
`$Models/model-list.json` (69 LMS-Datensätze) und `$Models/gguf-liste.txt`
(98 GGUF-Dateien), gegen den aktuellen Datenträger geprüft.
Die Liste enthält auch nicht für Textbenchmarks geeignete Dateien und Helper;
die Zahlen sind deshalb keine Anzahl freigegebener Benchmarkmodelle.

Vor dem Sync wurde die aktuelle Registry gesichert. SHA-256 des Backups:
`f628834b073fa219035a4d53948c6c6ef0d2af61cc9c0a34e6a6c1b21babfd95`.
Die ursprünglich vorgefundenen 71 Einträge wurden durch Sync auf 72 ergänzt;
neu ist `unsloth/qwen3.6-27b-mtp@q3_k_s`. Sechs eindeutig gebundene aktuelle
LMS-Werte für Kontext/KV-Cache wurden übernommen. Nach Archivierung von 14
tatsächlich gelöschten Modellen verbleiben **58 aktive Einträge**.

Zwei ungültige JSON-Bindungen wurden einschließlich Scope und Fehlerevidenz
archiviert. Modell-Dateibindung und provider-neutrale Policy bleiben erhalten.
Externe LMS-JSON-Dateien wurden weder verschoben noch gelöscht. Die Archivierung
der gelöschten Modelle erhielt jeweils die vollständige vorherige Registry-Policy.
Sampling-Werte wurden in dieser Folgerunde nicht pauschal neu recherchiert.

## Reale Companion-Prüfungen

Backend: installiertes Windows-x86_64 llama.cpp, `0.5.0-dev`, Build 11177,
Commit `1ab7e5ad2`, Clang 20.1.8. Die sechs Prüfungen liefen seriell als isolierte
Serverprozesse mit tatsächlichen lokalen GGUF-Dateien. Kontext 512, eine Session,
Batch/Microbatch 64, GPU-Offload 99, acht CPU-Threads; Prompt
`Write a Python function that adds two integers.`, Seed 17, Temperatur 0,
32 Ausgabetokens, kein Prompt-Cache. Verwendete Konfiguration und Antworten
stehen in den lokalen Run-JSONs. Das sind Funktions-Smokes, keine Qualitäts-
oder Durchsatz-Benchmarks; Peak-VRAM wurde nicht als Messwert erhoben.

| Vollständige Hauptmodell-ID | Methode | Draft-Tokens / akzeptiert | Ergebnis |
| --- | --- | --- | --- |
| `freedomaisvr/gemma-4-12b-it-qat@nvfp4` | MTP | 28 / 24 | Erfolgreiche Ausgabe, frischer Pairing-Nachweis verknüpft |
| `unsloth/gemma-4-26b-a4b-it@iq3_xxs` | MTP | 47 / 19 | Erfolgreiche Ausgabe, frischer Pairing-Nachweis verknüpft |
| `unsloth/lfm2.5-8b-a1b@mxfp4` | DSpark | 60 / 15 | Erfolgreiche Ausgabe, frischer Pairing-Nachweis verknüpft |
| `liquidai/lfm2.5-8b-a1b@q6_k` | DSpark | 32 / 22 | Erfolgreiche Ausgabe, frischer Pairing-Nachweis verknüpft |
| `byteshape/qwen3.8-27b@iq4_xs` | DSpark | Keine Generation | Helper-Laden endet mit `invalid vector subscript`, Exit 1 |
| `techhermit/gemma-4-26b-a4b-it-reap126@iq4_nl` | MTP | Keine Generation | Helper-Laden endet mit `invalid vector subscript`, Exit 1 |

Bei Qwen liegen die aktuellen Helper-Ziellayer innerhalb der tatsächlichen
64 Decoder-Layer; die korrigierte Layergrenze erklärt diesen Backend-Abbruch
nicht. Beim REAP-Modell unterscheiden sich Expertenzahl und Experten-Tensorformen
vom ungeprunten Modell. Eine dadurch verursachte Inkompatibilität ist eine
Hypothese, kein nachgewiesener Befund. Für die beiden fehlgeschlagenen Läufe wurde
kein gültiger Pairing-Nachweis erzeugt. LM-Studio- und TabbyAPI-Freigabe sowie
volle Benchmark-Kontexte sind durch diese sechs Tests nicht abgenommen.

## Verbleibende lokale Blocker

Die vollständige lokale Validierung nach dem Abgleich meldet **fünf Blocker**
und elf Hinweise. `validate --ci` prüft die statischen Regeln und meldet null
Blocker/null Hinweise; lokale Dateien und das installierte Backend gehören
zu einer gesonderten Freigabe.

| Modell-ID | Offener Vertrag | Erforderlicher nächster Schritt |
| --- | --- | --- |
| `llmsforall/millie-35b-a3b-11gb@?` | Vollständige Quant-/JSON-Identität unbelegt | Das spezifische Format und Backend prüfen; keine Standardquantisierung erfinden |
| `byteshape/qwen3.8-27b@iq4_xs` | DSpark-Profil ohne freigegebenen Helper-Pfad | Backend-Ladefehler klären oder das aktive Helper-Profil ausdrücklich archivieren |
| `techhermit/gemma-4-26b-a4b-it-reap126@iq4_nl` | MTP-Profil ohne freigegebenen Helper-Pfad | Erfolgreiche konkrete Paarung belegen oder Helper-Profil archivieren |
| `gguf-org/muse-glimmer-30b@nvfp4` | DFlash-Profil referenzierte gelöschte Datei | Neues konkretes kompatibles Artefakt belegen oder Altprofil archivieren |
| `prism-ml/ternary-bonsai-27b@q2_g64` | Frühere DSpark-Datei gelöscht | Neue zielgebundene Paarung belegen oder Altprofil archivieren |

Millies tatsächlicher Header enthält `general.file_type=56`; die installierte
GGUF-Bibliothek kennt dafür keine Standardquantisierung. Die
[Publisher-Model-Card](https://huggingface.co/llmsforall/Millie-35B-A3B-11GB/blob/main/README.md)
verlangt ausdrücklich den eigenen llama.cpp-Fork. Dessen
[Runtime-Dokumentation](https://github.com/llmsforall/llama.cpp)
beschreibt die zusätzlichen Millie-Gewichtsformate und getrennte Runtime-Bundles.
Ein vorhandener Modellname allein rechtfertigt weder einen Quant-Namen noch
eine Freigabe für das hier installierte Standardbackend.

Die offenen aktiven Helper-Profile wurden nicht allein zur Beseitigung roter
Validierungsmeldungen entfernt. Die Rückfrage zur Archivierung ist noch offen.

## Prüfungen und Nachweise

- Aktueller Vollbaum-Typecheck: null Fehler in 51 Quelldateien.
- Aktuelles `python -m ruff check . --no-fix`: bestanden.
- Unabhängige Nachreview der Korrekturen: keine verbleibenden reproduzierten
  P1-/P2-Code-Befunde. Auch die letzten Layer-/Testisolation-Änderungen wurden
  unabhängig geprüft: 121 zusätzliche fokussierte Testausführungen bestanden,
  Ruff und strenges mypy für `artifact_bundle.py` ebenfalls.
- `.githooks/pre_push.ps1`: Exit 0. Vollsuite **1.414 Tests bestanden in 44,47 s**;
  statische Registry, Ruff, Vollbaum-mypy, fokussierter mypy-Scope und GGUF-Abgleich
  bestanden. Der GGUF-Abgleich prüfte 48 Einträge und meldete keine Abweichungen.
- `.githooks/pre_commit.ps1`: Exit 0 mit separatem temporärem Index über alle
  nicht ignorierten Arbeitsbaumänderungen. Whitespace-/Secret-/Dateiformat-/Ruff-/
  Syntax-Prüfungen und 174 fokussierte Registry-Tests bestanden. Bei dieser
  Vorbereitung wurden Whitespace-Fehler im älteren ungetrackten Backend-Bericht
  korrigiert. Der SHA-256 des tatsächlichen Git-Index blieb unverändert.
- `.githooks/commit_msg.ps1`: Exit 0 für den vorbereiteten Conventional-Commit-
  Betreff. Der reale Index enthält weiterhin keine neu gestagten Änderungen.
- Versionierte Transparenz-Artefakte wurden anschließend mit
  `pre_review_checks.ps1 -NoTranscript -SkipPytest` erneuert. Die Suite war bereits
  vollständig im echten Pre-Push-Hook gelaufen; hier wurden nur ihre erneute
  Ausführung vermieden und die übrigen Checks/Artefakte aktualisiert. Exit 0.
- Ein früherer Lauf mit parallel geänderten Test-/Modulständen und nicht
  isolierter Native-API ist kein Abschlussnachweis. Die oben aufgeführte finale
  Vollsuite prüfte den abgeschlossenen Codezustand.

Die Hook-Prüfung belegt die lokale Git-Qualitätsschranke. Es wurde keine Remote-
Authentifizierung, kein tatsächlicher Push und kein GitHub-Actions-Lauf behauptet.

Maschinenbezogene Nachweise bleiben ignoriert unter `backups/`: ursprüngliches
Registry-Backup, `registry_reconciliation_20260929.json`,
`registry_validation_after_reconcile_20260929.log`, `pairing_20260929/summary.json`,
sechs Run-JSONs und Serverlogs, vier frische Pairing-Dateien sowie die finalen
Hook-Logs. Root-`utils/`, Modelle, Benutzerpfade und externe Runtime-Dateien
werden nicht zur Veröffentlichung hinzugefügt. Vorhandene fremde Änderungen
und Löschungen bleiben erhalten.
