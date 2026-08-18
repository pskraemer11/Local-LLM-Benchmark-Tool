# HowTo: Review mit dem Review-Gate (intern)

Stand: 2026-08-18 · Zielgruppe: Single-Entwickler (lokale Benchmarks + GitHub)

Dieses Dokument beschreibt den Ablauf eines Code-Reviews mit dem aktuellen
(Pre-)Review-Gate. Es ist die praktische Ergänzung zu `PLANUNG.md`
und ersetzt die bisherige manuelle Checkliste für den Review-Ablauf.

---

## 1. Überblick: Das Review-Gate (3 Säulen)

1. **CHANGELOG.md** (Projekt-Root) — jede Änderung wird dokumentiert.

2. **Review-Gate** — `pre_review_checks.ps1` wird vor Review, Commit oder Push
   direkt aufgerufen. Ein automatischer Aufruf bei `git push` erfolgt nur,
   wenn im konfigurierten Git-Hook-Pfad ausdrücklich ein entsprechender Hook
   eingerichtet wurde; dieser Hook ist nicht Bestandteil dieses Dokuments.

3. **Transparenz-Artefakte** — `doc-git/Review-Artifacts/` werden bei jedem
   Gate-Lauf neu erzeugt und committet (reproduzierbarer Nachweis).

**Regeln, die dabei immer gelten:**

- **Single Source of Truth (SSOT) für die LLM-Architektur sind primär die GGUF-Dateien**
  (unveränderlich) und **sekundär für Laufzeit-Parameter** die `model_registry.yaml` (editierbar).
  Die vom Anbieter mitgelieferte Hub-`model.yaml` (LM Studio) wird **nie** angefasst.

- Die Mistral-Regelliste (aus früheren Reviews) ist nur ein **Vorschlag**;
  bei Unklarheiten wird im Review nachgefragt, nicht geraten.

- `mypy` ist nur **informativ** und nicht blockierend.

- Qwen 3.5/3.6-Modelle sind **Dual-Mode**: Thinking per Toggle steuerbar,
  Default = Thinking (`enableThinking.defaultValue: true`).

---

## 2. Voraussetzungen

- Python 3.12 + Projekt-Dependencies (siehe `pyproject.toml`, dev-Deps)
- Tools: `ruff`, `mypy`, `pytest` (via venv)
- PowerShell 7+ (`pwsh`)
- Optional: ein eigener Git-Hook kann das Gate automatisch aufrufen. Die
  Installation und Pflege dieses Hooks ist nicht Teil des Benchmarks-Projekts.

---

## 3. Phase 1: Automatisches Gate

Das Skript liegt im Projekt-Root und wird direkt aufgerufen. Ein automatischer
Aufruf bei `git push` ist nur aktiv, wenn im konfigurierten Hook-Pfad ein
eigener Hook eingerichtet ist.

```powershell
# Direktaufruf (empfohlen vor dem Review, optional mit Log-Datei):
.\pre_review_checks.ps1
.\pre_review_checks.ps1 -NoTranscript        # ohne Transkript-Datei
```

Exit-Code: **0 = alle blockierenden Checks grün** · **1 = Gate rot**.

Die 6 Checks im Überblick:

|No.| Check                     | Blockierend       | Artefakt                                   | Hinweis                                                       |
|---|---------------------------|-------------------|--------------------------------------------|---------------------------------------------------------------|
| 1 | Registry-Validierung (`validate --repro`) | **Ja** | `repro_issues.md` | Registry-, GGUF- und Provider-Runtime-Prüfungen |
| 2 | `ruff check . --no-fix` | **Ja** | `lint_issues.md` | Lint-Fehler blockieren |
| 3 | `mypy .` | Nein (informativ) | — | Legacy-Typfehler werden nur berichtet |
| 4 | `pytest -q` | **Ja** | — | Vollsuite; zuletzt 893 Tests bestanden |
| 5 | GGUF-Header-Check | Nein (informativ) | `gguf_issues.md` | Architektur-Fakten gegen GGUF-Header |
| 6 | CHANGELOG + LM-Studio-Runtime-Konfiguration | Nein (advisory) | — | Prüft CHANGELOG-Hinweis und `numParallelSessions` |

> **Praktisch:** Das Gate im Hintergrund starten (`Start-Process` / zweites Terminal),
> während du mit Phase 2 beginnst.
> Vor einem Push sollte das Gate erneut ausgeführt werden. Ein Push wird nur
> automatisch blockiert, wenn ein entsprechender Git-Hook eingerichtet ist.

---

## 4. Phase 2: Artefakte sichten & gezielt nachprüfen

Nach dem Gate-Lauf:

1. **`repro_issues.md` lesen** — Abschnitt „Hub-Abweichungen" muss leer sein („Keine Abweichungen").
   Sind welche da:
   - GGUF-Fakten prüfen (z. B. `validate --verbose`), dann Registry-Eintrag
     korrigieren oder Abweichung begründen (mit Beleg im Review dokumentieren).

2. **`gguf_issues.md` lesen** — 0 Abweichungen ist der Normalzustand.

3. **`lint_issues.md`** — muss leer sein (ruff 0).

4. **Stichproben mit dem Tool** (wenn Zweifel an einzelnen Einträgen):

```powershell
python .\src\registry_tool.py validate --verbose          # alle Einzelprobleme
python .\src\registry_tool.py validate --verbose --repro  # Artefakt neu schreiben
```

5. **Neu aufgenommene Modelle** doppelt prüfen (GGUF-Header + Hub-`model.yaml`
   + Hersteller-Model-Card). Bekannte Fallstricke:
   - **Embedding-Modelle** gehören auf die BLACKLIST (`src/benchmark_config.py`),
     auch wenn sie groß sind (z. B. F2LLM-v2-14B) oder LM Studio sie als
     „Reasoning" anzeigt (Qwen3-Backbone + Chat-Template ⇒ automatische
     Klassifikation).
   - **Qwen 3.5/3.6**: immer `reasoning: thinking` + `max_context_length` aus
     der Hub-`model.yaml` (z. B. 262144 für qwen3.5-9b).

---

## 5. Phase 3: Review im Chat (Prompt-Vorlage)

Einen neuen Chat/Agenten starten und folgende Vorlage einfügen (anpassen:
Datum, Commit-Hash):

````text
Du bist der Review-Agent für das lokale LLM-Benchmark-Projekt
(C:\Users\pskra\Python-Projekte\Benchmarks).
Führe einen Code-Review der Änderungen seit <COMMIT-HASH> durch (git log / git diff).

Vorgehen:
1. Phase 1 (Gate) läuft bereits separat — du musst pre_review_checks.ps1
   NICHT ausführen. Lies aber die aktuellen Artefakte:
   - doc-git/Review-Artifacts/repro_issues.md
   - doc-git/Review-Artifacts/lint_issues.md
   - doc-git/Review-Artifacts/gguf_issues.md
2. Prüfe die Änderungen (git status, git diff, git log) auf:
   - Korrektheit der Registry-Einträge (model_registry.yaml) gegen GGUF-Header
     und Hub-model.yaml — Source of Truth sind die GGUF-Dateien; die
     Registry ist editierbar; Hub-Dateien werden nie angefasst.
   - Logik/Regressionen im geänderten Code (src/, tests/).
   - Dokumentations-Änderungen (doc-git/, CHANGELOG.md).
3. Regeln:
   - Die Mistral-Regelliste ist nur ein Vorschlag. Bei Unklarheiten frag
     nach, statt zu raten.
    - mypy-Fehler sind informativ und nicht blockierend.
    - Qwen 3.5/3.6 = Dual-Mode, Thinking-Toggle, Default Thinking.
   - Embedding-Modelle (auch große wie F2LLM-v2-14B) gehören auf die
     BLACKLIST, auch wenn LM Studio sie als Reasoning anzeigt.
4. Ausgabeformat (English, gemäß `.opencode/agents/review.md`):
   - Zusammenfassung (1-2 Sätze)
   - Befunde nach Schweregrad: [KRITISCH] / [WICHTIG] / [MINOR] / [NITPICK]
   - Zu jedem Befund: Datei:Zeile, Problem, konkreter Fix-Vorschlag
   - KEINE Änderungen selbst vornehmen — erst nach Freigabe durch mich.
````

---

## 6. Abschluss

- Alle Befunde abgearbeitet: fixen (Code) oder begründet verwerfen
  (im Review-Text dokumentieren).
- **CHANGELOG.md** um die Änderung ergänzen (neue Zeile, Commit-Hash
  nach dem Commit eintragen; Commit-Stil: `fix:` / `feat:` / `docs:`).
- `PLANUNG.md` aktualisieren (erledigte Punkte `[x]`).
- Committen + pushen; vor dem Push das Gate erneut ausführen oder einen
  ausdrücklich eingerichteten Pre-Push-Hook verwenden.
