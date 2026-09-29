# Registry-Fixes und erneute Review vom 28.09.2026

Basis: Arbeitsbaum auf `main`, HEAD `5fe026bfa8a022676043d664a4d57442bf09d34d`.
Referenz ist `Code-Review_registry_2026-09-28.md` mit sechs P1- und sechs
P2-Befunden. Die Umsetzung erfolgte in der vom Benutzer vorgegebenen Reihenfolge.
Commit und Push wurden nicht durchgeführt.

**Ergebnis:** R01–R12 sind im Code korrigiert und durch Regressionen geprüft.
Die erneute Bestandsreview enthält einen zusätzlichen, bereits vorher bestehenden
P2-Befund im Namespace-Fallback der Codebewertung. Die lokale Registry besitzt
weiterhin blockierte Datei-/Config-/Helper-Bindungen; erfolgreiche Offline-Tests
sind keine Freigabe dieser konkreten lokalen Kombinationen.

## Korrekturen und Abnahme

| Befund | Umsetzung | Verifikation |
| --- | --- | --- |
| R01 / P1 | Konkrete Quantisierung beschränkt alle Matcher-Stufen. Vollständige Publisher-/Modell-/Quant-Anfragen wechseln weder Publisher noch Training-/Finetune-Variante. | Zentrale Matcher-, Registry-, LocalResolver- und Custom-Auswahl-Negativtests. |
| R02 / P1 | Sync, Fill und Drift verwenden die vollständigen `IdentityLink`-Artefakte. Verpackungstokens werden nur mit belegter Quantisierung entfernt; QAT und andere Varianten bleiben erhalten. | Echte Mini-GGUFs mit zwei Quants, fremdem Publisher, falschem Quant und mehreren Dateien derselben Identität. |
| R03 / P1 | Alle aktiven JSONs werden inventarisiert. Generations-Extras brauchen eine eindeutige, aktuelle GGUF-/JSON-Bindung zur vollständigen Registry-Identität. | Fremde, wiederverwendete, stale und falsch deklarierte Modell-/Quant-Bindungen liefern keine Extras. |
| R11 / P1 | Native Load-Identität und geladene Instanz werden gegen das konkrete Registry-Ziel geprüft; eine Serving-Alias-Zeichenfolge genügt nicht. | Native HTTP-Fixtures mit falschem Publisher, anderer Variante/Quantisierung und fehlender Identität; Launcher-Reload-/Postload-Prüfung. |
| R10 / P1 | Der Pipeline-Endstatus nutzt sämtliche blockierenden Validierungsfehler. `--ignore-drift` ignoriert ausschließlich explizite Drift-Kategorien. | 19 parametrisierte Fälle einschließlich unbekannter zukünftiger Fehlerkategorie und rein beratender Hinweise. |
| R04 / P2 | Explizites Registry-Reasoning gewinnt vor Namens-/Architekturdefaults. Reasoning-Controls stammen aus dem tatsächlich ausgewählten Datei-/GGUF-Template oder einer bekannten Architektur. | Neutrale Modellnamen, explizites Instruct und unterstützte/nicht unterstützte Templates bis zu Custom-HTTP-Body und LM-Eval-Gen-Kwargs. |
| R05 / P2 | Ein gemeinsamer Kontextresolver begrenzt den Benchmark-Kontext technisch. LM Studio erhält `context_length`; die geladene Instanz muss diesen Kontext nachweisen. | Native Load-Requests, Response-Echos, `instance.config`, fehlender/abweichender Kontext und Kontextbegrenzung. |
| R08 / P2 | `explicit_file` hat in Assembly, Konfiguration und Provider dieselbe Priorität vor Blueprint-Map/-Template. | Tatsächlich geschriebener Template-Inhalt und konsistente Resolver-Ausgabe. |
| R06 / P2 | Gewöhnliche kleinere Drafter benötigen passende Token-Tabellen/-Einstellungen und eigenständig lauffähige Tensorstruktur; gleiche Hidden-Dimension oder bestimmte Dateinamen werden nicht verlangt. | Unterschiedliche Dimensionen und Dateinamen sowie fehlende/einseitige Tokenizer-Metadaten. |
| R07 / P2 | DFlash, DSpark und separates MTP besitzen eigene Header-/Projektions-/Zielverträge. DSpark verlangt beide Markov-Tensoren. Unbekannte Modi/Methoden und überschreibende Runtime-Bundle-Felder blockieren. | Echte GGUF-Tensorbeschreibungen, falscher Algorithmus, Zielprojektion, fehlende/stale/manipulierte Pairing-Evidenz und Provider-Override-Negativtests. |
| R09 / P1 | Web-Startpunkte kommen aus dem eindeutig belegten Artefakt im `IdentityLink`, einschließlich HF-Cache-Layouts. Suchtreffer bestätigen keine fremden Repositories; nur explizite Quantisierungsabstammung erlaubt Sampling-Vererbung. | Unverwandte Suchtreffer, Finetunes/Merges/Adapter, fremde Modellabschnitte und Unterabschnitte sowie widersprechende Artefakt-Publisher/Quants. |
| R12 / P2 | `fill-reasoning` ergänzt ausschließlich fehlende, durch Template-Evidenz belegte Klassifikation. Fehlendes/leer gebliebenes Template liefert `None`. | Persistiertes Fill-Ergebnis, vorhandene Policy bleibt erhalten; fehlende Template-Evidenz und spät angeordnete MoE-Metadaten. |

Der neue gemeinsame GGUF-Reader liest Metadaten und Tensorverzeichnis innerhalb
fester Grenzen, ohne Gewichte zu mappen. Header-/Tensor-Digest, Dateigröße und
Änderungszeit bilden den Pairing-Fingerprint. Ein geteiltes, untypisiertes
`general.base_model` allein belegt nicht die Zielbindung eines spezialisierten
Helpers. Dies gilt auch dann, wenn ein Finetune seine Eigenschaft im Header
nicht ausdrücklich als `general.finetune` markiert.

Die unabhängigen Zwischenreviews der Identitäts-/Runtime- und Companion-Pfade
fanden weitere Umgehungen innerhalb R01–R12. Korrigiert wurden insbesondere
persistierte Q4-als-Q6-Bindungen, publisherloser Custom-Fallback, fehlendes
Template als falsches Instruct, Metadaten-Reihenfolge, nachträglicher Austausch
validierter Helfer und einseitig fehlende Tokenizer-Einstellungen. Die abschließende
Web-/Quellenprüfung ergänzte verschachtelte fremde Modellabschnitte und HF-Cache-
Repository-Evidenz. Alle genannten Regressionen sind grün.

## Aktuelle Registry und Schreibzuständigkeit

Die Grundlage ist die aktuelle Registry nach dem vom Benutzer während der
Bearbeitung abgeschlossenen `sync --import-lms-settings --refresh-sampling`.
Frühere Registry-Inhalte wurden nicht zurückgespielt. Vor eigener Änderung
wurde ein vollständiges Backup erstellt.

- Ausgangsbestand: 71 Registry-Einträge, 41 numerische Sampling-Profile.
- Gezielt recherchiert: 36 Profile; 17 erneut `confirmed`, 16 `unresolved`,
  drei `conflict`. 35 nicht ausgewählte Einträge blieben beim Refresh unverändert.
- Nach Verschärfung der Abschnittsprüfung wurden die 17 bestätigten Profile
  erneut aus ihren Quellen geprüft: keine zusätzliche Änderung erforderlich.
- Der anschließende Header-Sync korrigierte vier Felder in drei Einträgen:
  `techhermit/gemma-4-26b-a4b-it-reap126@iq4_nl` erhält `arch: moe` und
  `max_experts: 126`; beide LFM2.5-8B-A1B-Varianten erhalten `max_experts: 32`.
  Die ausgewählte Runtime-Expertenzahl wurde nicht mit der technischen Obergrenze
  gleichgesetzt oder überschrieben.

Sampling-Auswahl, alte/neue Werte und konkrete Quellen sind in
[Sampling-Identity-Refresh_2026-09-28.md](Sampling-Identity-Refresh_2026-09-28.md)
dokumentiert. Registry und Backups bleiben maschinenlokal und gitignoriert.
Der R09-Refresh und der abschließende Header-Sync schrieben keine LMS-JSONs.

| Stand | SHA256 |
| --- | --- |
| Benutzer-Sync / Backup vor R09 | `02072357fc8682a137c0a616fb46b76f7568e4103e0d7e891d0ac9332970fec4` |
| Nach gezieltem R09-Refresh | `659670592c105617f8a6a2fca127454474d7119ab26fe81c8825b07c1158f140` |
| Nach abschließendem Header-Sync | `5a6aa5d4dd1d90b271ab55829e2576891ff2ec076b0572bed3f46e701e50c378` |

Backups: `backups/model_registry_before_R09_20260928_134721.yaml` und
`backups/model_registry_before_final_header_sync_20260928.yaml`.
Die unveränderten Felder und Einträge wurden nach dem Schreiben erneut gelesen
und semantisch gegen die jeweilige Baseline geprüft.

## Tests und Gate

- Windows / vorhandenes Python 3.12.10, prozesslokales `LLM_PROVIDER=lmstudio`.
- Finale vollständige Pytest-Suite: **1323 bestanden**.
- `ruff check . --no-fix`: **grün**.
- Blockierender mypy-Scope `benchmark_config.py` / `csv_writer.py`: **grün**;
  zusätzlicher fokussierter mypy über elf Identity-/Runtime-/Provider-/Sampling-
  Quelldateien ebenfalls **grün**.
- `pre_review_checks.ps1 -NoTranscript -NoArtifacts`: **grün**. CI-/statische
  Registry-Prüfung und Header-Abgleich ohne Drift. Der informative Vollbaum-
  Typecheck meldet 119 Fehler; er ist gemäß Projekt-Gate nicht blockierend.
- Der Gate-Lauf zeigt zwei bestehende Hinweise für LMS-Configs mit
  `numParallelSessions=1`. Diese Provider-Artefakte wurden nicht umgeschrieben.
- Neue/sauber formatierte kleine Module wurden mit Ruff-Format geprüft.
  Großdateien, deren HEAD bereits Formatabweichungen besitzt, wurden nicht
  vollständig umformatiert. PowerShell-Parserprüfung und Whitespace-Prüfung
  des bearbeiteten Scopes sind grün.
- Sampling-Tests verwenden feste Fixtures. Ein Refresh der gitignorierten
  Maschinen-Registry verändert die Unit-Test-Erwartungen nicht mehr.

Lokale Logs und maschinenbezogene Einzelprüfungen liegen unter `backups/`,
insbesondere `registry_review_gate_final_20260928.log`,
`registry_final_pytest_20260928.log`, `registry_final_bundle_audit_20260928.json`
und `registry_local_validation_final_20260928.log`.
Vorhandene fremde Änderungen an `AGENTS.md`, Dokumenten und gelöschten alten
Artefakten wurden erhalten. Root-`utils/` bleibt untracked/gitignoriert und
ist vom mypy-Vollbaum ausgeschlossen; `src/utils/` gehört weiterhin zum Code.

## Offene lokale Daten- und Backend-Abnahmen

Die vollständige lokale Validierung ist bewusst strenger als `validate --ci`.
CI prüft keine lokalen Modell-/Config-Dateien. Die finale Vollvalidierung endet
mit Exit 1: **27 blockierende Probleme** (zehn Config-/Identitätsbindungen,
17 Companion-Meldungen) und 16 beratende Hinweise. Header-Drift, Reasoning-
Policy und Sampling-Schema besitzen dabei keine Blocker. Im abschließenden Bundle-Audit
sind **15 separate Profile nicht freigegeben**: fehlende Haupt-/Helper-Dateien,
fehlender konkreter Helper-Pfad oder unbelegte spezialisierte Zielidentität.
Das ist keine Aussage, dass vorhandene Helper rechnerisch inkompatibel sind.
Eine passende Tensorform und ein gemeinsames Base-Modell belegen die vollständige
Zielbindung noch nicht.

Die folgenden Profile benötigen belegte Zielbindung bzw. aktuelle Pairing-Evidenz:

- `byteshape/qwen3.6-35b-a3b@iq3_s`
- `unsloth/qwen3.6-27b-mtp@iq3_xxs`
- `bytkim/qwen3.6-27b-mtp-pi-tune@q3_k_s`
- `techhermit/gemma-4-26b-a4b-it-reap126@iq4_nl`
- `freedomaisvr/gemma-4-12b-it-qat@nvfp4`
- `mudler/gemma-4-26b-a4b-it-apex@mini`
- `unsloth/gemma-4-26b-a4b-it@iq3_xxs`
- `unsloth/qwen3.6-35b-a3b-mtp@iq2_m`
- `unsloth/lfm2.5-8b-a1b@mxfp4`
- `liquidai/lfm2.5-8b-a1b@q6_k`
- `prism-ml/ternary-bonsai-27b@q2_g64`

Fehlende Haupt-/Helper-Dateien betreffen außerdem `unsloth/gemma-4-12b-it@q6_k`,
`mradermacher/muse-glimmer-30b-heretic-abliterated-i1@iq3_m` und
`kookiesxy/muse-glimmer-30b-ternary-quants@iq1_s`. Bei
`gguf-org/muse-glimmer-30b@nvfp4` fehlt der konkrete Helper-Pfad.
Weitere lokale Config-Bindungen sind stale oder belegen die vollständige
Identität nicht; die Vollvalidierung meldet sie blockierend.

Ein ausdrücklich nachgewiesenes erfolgreiches Pairing wird im Profil so referenziert:

```yaml
pairing:
  evidence_path: <machine-local-json-path>
  evidence_sha256: <64-hex-sha256>
```

Die JSON-Datei enthält `method`, `main_path`, `companion_path`,
`main_fingerprint`, `companion_fingerprint` sowie
`validation: {status: passed, check: speculative_pairing, provider: llama_cpp|lmstudio, source: <evidence-reference>}`.
Ein frei gesetztes `validated: true`, ein beliebiger alter Smoke oder ein
veralteter Dateifingerprint genügt nicht. Es wurde kein erfolgreicher GPU-Smoke
erfunden. Reale Pairing-Smokes und die vollständige TabbyAPI-Identitätsabnahme
bleiben gesonderte Backend-Abnahmen; unbewiesene Tabby-Aliase bleiben blockiert.

## Zusätzlicher Befund der erneuten Bestandsreview

### R13 — P2: Namespace-Fallback ruft den Sandbox-Builder falsch auf

Fundstelle: `src/custom_benchmark.py:1685`, zweiter Aufruf bei Zeile 1693.
Wenn `evaluate_code()` ohne direkte Tests/Harness mit `reference_code` und
`setup_code` aufgerufen wird, reicht es `capture_state=True` weiter. Der Builder
deklariert jedoch `should_capture_state`. Ein deterministischer Aufruf mit
`generated_code='answer = 2'`, `reference_code='answer = 1'`,
`setup_code='initial = 0'`, leerem Entry-Point und leerer Testliste endet mit
`TypeError`, bevor der Sandbox-Subprozess startet.

Dieser Fehler ist bereits in HEAD vorhanden und liegt außerhalb R01–R12.
Er wurde beim angefragten erneuten Review reproduziert und nicht im Registry-Fix
verändert. Korrektur: Aufrufvertrag angleichen und den vollständigen
Namespace-Vergleich mit richtigen/falschen generierten Ausgaben prüfen. Dabei
muss `setup_keys` aus dem Setup-Zustand stammen: die aktuelle Zuweisung aus dem
gesamten Referenzzustand schließt auch die zu vergleichenden Ausgaben aus.

Die Registry-Fixes sind damit abgenommen; der übrige Arbeitsbaum hat diesen
zusätzlichen offenen Funktionsbefund und die dokumentierten lokalen Datenblocker.

## Technische Referenzen

Die Native-Kontext-/Instanzverträge wurden gegen die offiziellen
[LM-Studio-Load-](https://lmstudio.ai/docs/developer/rest/load) und
[List-API-Dokumente](https://lmstudio.ai/docs/developer/rest/list) geprüft.
Companion-Typen und Projektionen beziehen sich auf die
[llama.cpp-Speculative-Dokumentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md),
die [DFlash-/DSpark-Implementierung](https://github.com/ggml-org/llama.cpp/blob/master/src/models/dflash.cpp)
und die [Speculative-Runtime](https://github.com/ggml-org/llama.cpp/blob/master/common/speculative.cpp).
Die konkreten Webquellen des Sampling-Refreshs stehen direkt beim betroffenen
Modell im verlinkten Quellenbericht.
