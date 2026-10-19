# Review: Local-LLM-Benchmark-Tool (Stand 12.10.2026) durch Sonnet 5.5 (mittel) in Claude

## Grundlage und Umfang

Geprüft habe ich `README.md`, `AGENTS.md`, `PLANUNG.md` und `COMPACTIONS.md` (bis 09.10.2026). Code, Tests und Ergebnis-CSVs habe ich nicht gesehen, und ich habe nichts ausgeführt. Alle Testzahlen (z. B. 1.662 bestanden) sind Selbstangaben aus den Compactions. Das Review bewertet daher Architektur, Prozess und Dokumentation, nicht die Code-Korrektheit.

## Stärken (belegt durch die Dokumente)

- **Klare Datenhoheit:** GGUF-Header sind die technische Quelle, die Registry die Benchmark-Policy, LM-Studio-JSONs nur Runtime-Artefakte. Preset und Argumentmanifest sind abgeleitet. Das ist die richtige Trennung.
- **Fail-closed-Haltung** bei Modellidentität, Quantisierung und Companion-Dateien (MTP, DSpark). Der Fehler mit der falschen Quantisierung (Q4_K_XL statt Q8_0) wurde als Klasse behoben, nicht nur als Einzelfall.
- **Ehrliche Abnahmegrenzen:** SampleSize-1-Scores werden ausdrücklich nicht als Qualität gewertet, und offene Punkte stehen als offen da.
- **Prozess:** Hooks ohne `--no-verify`, unabhängige Reviews mit Blockern und die Lehre aus dem CI-Fehler (Tests hingen an der ignorierten lokalen Registry).
- **Sandbox-Threat-Model** ist ehrlich benannt: Job Object plus Worker sind Defense-in-depth, keine Sicherheitsgrenze.

## Befunde

**P1 – Methodik und Aussagekraft**
1. **Statistische Trennschärfe:** Die Beispielrangliste zeigt 67/66/65/64/63 % bei SampleSize 20. Die Math-Werte (40, 55, 50, 45 %) sind Vielfache von 5 %, also n=20. Diese Abstände liegen mit hoher Wahrscheinlichkeit im Rauschen. Ohne Konfidenzintervalle in der README-Tabelle ist das Ranking irreführend.
2. **CoderEval hat lokal nur 12 Aufgaben**, trägt aber 25 % des Coding-Anteils (35 % Gesamtgewicht). Bei `--sample-size 30` ist das ein stilles Cap und eine statistisch sehr schwache Komponente.
3. **Score und Reasoning-Budget vermischt:** Der Qwen-DS1000-Fall (reasoning-only bei 8192 Token → Score 0) zeigt, dass Nullen Budgetpolitik statt Modellqualität messen können. Das ist laut Planung noch nicht isoliert.
4. **Historische Vergleichbarkeit:** Backend-Wechsel (LM Studio → llama.cpp), die neue KV-Policy (nur q4_0/q4_0 oder q8_0/q8_0), neue Reasoning-Formate und Sampling-Evidenz verändern Scores. Die 30-Modelle-Rangliste aus dem August ist damit nicht mehr mit neuen Läufen vergleichbar. Ein Re-Baseline ist nötig, und jede Ergebniszeile sollte Registry-Hash, Build und Runtime-Argumente tragen.

**P1 – Reproduzierbarkeit**
5. **Die Registry ist gitignored**, aber als Single Source of Truth deklariert. Externe können Ergebnisse nicht nachvollziehen, und `validate --ci` (headless) beweist nichts über die lokalen Daten. Die lokale Validierung meldete zuletzt wiederholt Blocker, während alle Gates grün waren. Das ist dokumentiert, aber strukturell riskant.
6. **Tests hängen an der Nutzerumgebung:** Der persistente Wert `LLM_PROVIDER=<Dateipfad>` zwingt Tests zu prozesslokalen Overrides. Wiederholte `WinError 5`-Fixes (19.09 mehrfach, 20.09, 23.09) deuten auf fragile Test-Infrastruktur. Tests sollten die Umgebung per Fixture isolieren.

**P2 – Dokumentations-Drift** (konkret nachweisbar)
- README nennt Python 3.13+, AGENTS.md bevorzugt 3.12, und die Läufe nutzen `py -3.12`.
- README verweist auf `doc-git/model_registry.yaml` und „520+ Tests"; real liegt die Registry in `data/` und es sind über 1.600 Tests.
- README installiert `nvidia-ml-py3`, der Code wurde aber auf `nvidia-ml-py` migriert.
- Der llama.cpp-Provider fehlt in der README-Architektur, die Version steht noch auf v13.0.5 (Doku-Stand 18.08.).
- `PLANUNG.md` führt „mypy-Bestand bereinigen" (105 Meldungen) offen, während die Compactions grüne Typechecks melden. Weitere Statusmarker widersprechen sich.
- `COMPACTIONS.md` ist nicht durchgängig chronologisch (27.09. steht vor 26.09.) und dupliziert Inhalte aus dem CHANGELOG.

**P2 – Sicherheit und Betrieb**
- Die Planung entfernt die Import-Allowlist im Standardpfad (Score-Kompatibilität), während der Security-Scan sie als Maßnahme führte. Das Restrisiko (Host-Python mit Nutzerrechten, kein Datei- und Netzwerkschutz) sollte im README stehen. Bei feindlichem Modell-Output bleiben separates Konto plus Firewall die einzige belastbare Option.
- Aus dem 20.08. ist offen, ob der im Screenshot sichtbare `UNSLOTH_API_KEY` rotiert wurde. Das ist in den Dokumenten nirgends bestätigt.

## Unsicherheiten und Gegenargumente

- **Scope-Drift (Inferenz, nicht belegt):** Seit August fließt der Aufwand überwiegend in Registry, Identität, Sampling-Crawler und Companion-Bundles. Der große SampleSize-5-Lauf ist seit dem 22.09. pausiert. Gegenargument: Die fail-closed-Infrastruktur verhindert genau die Fehlmessungen, die Rangfolgen entwerten. Ob das Verhältnis stimmt, kann nur der Projektinhaber beurteilen.
- Die Reviews sind teils LLM-gestützt. Das ist nützlich, ersetzt aber keine Prüfung durch eine unabhängige menschliche Instanz bei den Daten- und Identitätsverträgen.

## Relevante Quellen

Für die Statistik: lm-evaluation-harness-Dokumentation zu Standardfehlern und Bootstrap sowie die Evalplus-Veröffentlichungen. Für Backend-Parameter: llama.cpp `tools/server/README.md` und die Release-Notes, in denen Reasoning-Format und KV-Optionen versioniert sind. Verlässlichkeit: Primärquellen (Repos, Herstellerkarten) hoch, Community-Empfehlungen zu Sampling nur mit Evidenzstatus, wie es die Registry bereits führt.

## Fazit

Die Engineering-Disziplin ist überdurchschnittlich: Identität, Datenhoheit, Gates. Die größte Schwäche liegt nicht im Code, sondern in der **Aussagekraft der Ergebnisse** (kleine Stichproben, 12er-CoderEval, Budget-Artefakte, nicht vergleichbare Altläufe). Empfohlene Reihenfolge:

1. Konfidenzintervalle in alle Ranglisten und keine Rangaussage bei überlappenden CIs.
2. Re-Baseline nach der Backend-Abnahme, mit Registry-Hash und Build je Ergebniszeile.
3. DS1000-Reasoning-Budget isolieren.
4. Test-Umgebungsisolation, dann README, AGENTS.md und PLANUNG.md auf den Ist-Stand bringen.

Soll ich das Review als Markdown-Datei (z. B. für `docs/Reviews/`) im Format Ihrer bisherigen ISO/IEC-9126-Berichte ausarbeiten?