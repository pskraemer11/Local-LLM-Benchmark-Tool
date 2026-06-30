# GitHub-Upload: Schritt-fuer-Schritt-Anleitung

## Vorbereitung (einmalig)

### 1. GitHub-Account erstellen
- Gehe zu https://github.com
- Klicke "Sign up" und folge dem Prozess
- **Empfehlung:** Nutze eine E-Mail-Adresse, auf die du Zugriff hast

### 2. Git installieren (bereits erledigt)
- Git ist installiert: `git version 2.54.0.windows.1`
- Git muss sich beim ersten Mal per Konsole beim Account authentifizieren

### 3. Git-Konfiguration (einmalig)
Oeffne PowerShell und fuehre aus:
```
git config --global user.name "Dein Name"
git config --global user.email "deine-email@beispiel.de"
```

---

## Repository auf GitHub erstellen

### 4. Neues Repository anlegen
1. Auf GitHub oben rechts auf "+" klicken -> "New repository"
2. Einstellungen:
   - **Repository name:** `llm-benchmark-tool` (oder aehnlich)
   - **Description:** "Benchmark-System fuer lokale LLMs uber LM Studio (10 Benchmarks, 4 Pipelines)"
   - **Visibility:** Private (empfohlen, da lokale System-Infos enthalten sein koennten)
   - **Initialize:** NICHTS ankreuzen (wir haben bereits Dateien)
3. "Create repository" klicken
4. **Merke dir die URL:** `https://github.com/DEIN-NAME/llm-benchmark-tool.git`

---

## Projekt vorbereiten

### 5. .gitignore (bereits erstellt)
Die Datei `.gitignore` schliesst automatisch aus:
- `simple_evals/` (66 MB Benchmark-Daten)
- `ergebnisse/` (28 MB Ergebnisse)
- `Archiv/` (5 MB alte Skripte)
- `logs/`, `runs/`, `__pycache__/`
- `ds1000_official/`, `human-eval/` (Drittanbieter)
- System-spezifische Dateien

### 6. Repository initialisieren
Im Projektordner PowerShell oeffnen:
```powershell
cd C:\Users\pskra\Python-Projekte\Benchmarks
git init
```

### 7. Dateien zum Staging hinzufuegen
```powershell
# Alles hinzufuegen (gitignore beachtet automatisch die Ausnahmen)
git add .

# Pruefen was hinzugefuegt wird
git status
```

**WICHTIG:** Pruefe `git status` genau! Dort duerfen KEINE Dateien stehen:
- `simple_evals/`
- `ergebnisse/`
- `Archiv/`
- `*.json` mit localen Daten
- `logs/`

Falls doch: Datei in `.gitignore` nachtragen, dann `git rm --cached <datei>`

### 8. Ersten Commit erstellen
```powershell
git commit -m "Initial commit: LLM Benchmark-System v11

- 10 Benchmarks (DS1000, CoderEval, HumanEval+, MBPP+, MathQA,
  ARC-Challenge, HellaSwag, TruthfulQA, MMLU-Pro, Agentic)
- 4 Pipelines (Custom, EvalPlus, LM-Eval, Agentic)
- Zentrale Konfiguration (benchmark_config.py)
- Einheitlicher CSV-Output (csv_writer.py)
- Konsolidierung mit Ranglisten (consolidate_results_v11.py)
- 15 pytest-Tests"
```

---

## Auf GitHub hochladen

### 9. Remote-URL setzen
```powershell
git remote add origin https://github.com/DEIN-NAME/llm-benchmark-tool.git
```

### 10. Hochladen
```powershell
git branch -M main
git push -u origin main
```

**Beim ersten Push** fragt Git nach Anmeldedaten:
- **Option A (empfohlen):** GitHub Personal Access Token
  1. Auf GitHub: Settings -> Developer settings -> Personal access tokens -> Tokens (classic)
  2. "Generate new token" -> Scope: `repo` auswaehlen
  3. Token kopieren und als Passwort eingeben
- **Option B:** GitHub Desktop oder SSH-Key (aufwaendiger)

---

## mükemakter Befehl (alles zusammen)

```powershell
cd C:\Users\pskra\Python-Projekte\Benchmarks
git init
git add .
git status
git commit -m "Initial commit: LLM Benchmark-System v11"
git remote add origin https://github.com/DEIN-NAME/llm-benchmark-tool.git
git branch -M main
git push -u origin main
```

---

## Wichtige Hinweise

### Was NICHT ins Repo gehoert
| Datei/Ordner | Grund | Loesung |
|-------------|-------|---------|
| `simple_evals/` | 66 MB Benchmark-Daten | `.gitignore` |
| `ergebnisse/` | 28 MB Ergebnisse | `.gitignore` |
| `Archiv/` | 5 MB alte Skripte | `.gitignore` |
| `opencode.json` | Konfiguration | `.gitignore` |
| `lmstudio_model-list*.json` | Localer System-Zustand | `.gitignore` |

### Was ins Repo gehoert
| Datei | Zweck |
|-------|-------|
| `*.py` (Hauptskripte) | Code |
| `tests/` | Tests |
| `Doku+Install/` | Dokumentation |
| `.gitignore` | Ausschluss-Liste |
| `README.md` | Projektbeschreibung (optional) |

### Groesse beachten
GitHub hat ein Limit von **100 MB pro Datei** und **empfiehlt < 1 GB pro Repo**.
Dein Repo (ohne ausgeschlossene Dateien) wird ca. **2-3 MB** sein – kein Problem.

### .gitignore nachtraegen
Falls du merkst, dass eine Datei versehentlich im Repo landet:
```powershell
# Datei aus dem Tracking entfernen (Datei bleibt lokal)
git rm --cached <datei>
git commit -m "Entferne <datei> aus Tracking"
git push
```

### Aenderungen hochladen (spaeter)
```powershell
git add .
git commit -m "Beschreibung der Aenderung"
git push
```

### Status pruefen
```powershell
git status          # Was hat sich geaendert?
git log --oneline   # Letzte Commits
git diff            # Details zu Aenderungen
```

---

## README.md (optional aber empfohlen)

Erstelle eine `README.md` im Projektordner mit:
```markdown
# LLM Benchmark Tool

Benchmark-System fuer lokale LLMs uber LM Studio.

## Features
- 10 Benchmarks: DS1000, CoderEval, HumanEval+, MBPP+, MathQA, ...
- 4 Pipelines: Custom, EvalPlus, LM-Eval, Agentic
- Einheitlicher CSV-Output mit Systemmetriken
- Konsolidierung mit Ranglisten und Kategorie-Scores

## Voraussetzungen
- Python 3.10+
- LM Studio mit installiertem LLM
- lm-evaluation-harness, evalplus, tool-eval-bench

## Nutzung
```bash
python run_benchmarks_v11.py --model all --benchmarks all --sample-size 5
```

## Tests
```bash
pytest tests/ -v
```
```

Dann:
```powershell
git add README.md
git commit -m "Add README"
git push
```
