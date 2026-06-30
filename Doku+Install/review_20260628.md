# Review: Benchmark-Evaluierungssystem (Stand 2026-06-28)

## 1. Architekturübersicht

```
run_benchmarks_v8.py  (Launcher – load/unload + Dispatch)
  ├── model_manager_v3.py      (lms CLI-Hilfsfunktionen)
  ├── custom_benchmark_v25.py  (Subprozess: DS1000, CoderEval)
  ├── csv_writer_v3.py         (einheitlicher CSV-Output)
  ├── evalplus                 (HumanEval+, MBPP+)
  ├── lm_eval                  (ARC, HellaSwag, TruthfulQA, MathQA, MMLU-Pro)
  └── tool_eval_bench          (Agentic)
       ↓
consolidate_results_v9.py     (Liest CSVs + JSON → MD/CSV-Report)
```

**Insgesamt 5 aktive Hauptskripte (1743 + 997 + 914 + 330 + 210 = 4.194 Zeilen)**  
Dazu 6 Hilfsskripte/Wrapper (run_all_dense, rerun_*, resume_*, check_*, top5_report – ca. 450 Zeilen insgesamt)  
Legacy: benchmark_lmstudio_v22.py (1.692 Zeilen, nicht mehr in Nutzung)

---

## 2. Datenfluss

```
custom_benchmark_v25.py
  → tasks_{ts}_{bench}_{model}.csv  (Per-Task-Rohdaten, Semikolon-Delimiter)

run_benchmarks_v8.py  (Pipelines)
  → modell_{model_key}.csv           (akkumulierte Modell-Zusammenfassung)
  → evalplus_{safe}/                 (JSON-Ergebnisverzeichnis)
  → lmeval_{safe}/                   (JSON-Ergebnisverzeichnis)
  → agentic_{safe}/                  (JSON-Ergebnisverzeichnis)

consolidate_results_v9.py
  ← tasks_*.csv, modell_*.csv, 2026*_*.csv (?), evalplus_*, lmeval_*, agentic_*
  → konsolidiert_{ts}.csv            (33 Modelle × Benchmarks, Semikolon-Delimiter)
  → konsolidiert_{ts}.md             (Human-Readable Report)
```

---

## 3. Bewertung

### Stärken

1. **Klare Trennung der Verantwortlichkeiten**  
   - Launcher (run_benchmarks_v8.py) managt nur Pipeline-Dispatch + Modell-Lebenszyklus
   - model_manager_v3.py kapselt lms-CLI komplett
   - csv_writer_v3.py definiert einheitliches CSV-Schema für alle Pipelines
   - consolidate_results_v9.py ist reiner Reader (keine Imports eigener Skripte)

2. **Dynamische Skript-Erkennung**  
   - run_benchmarks_v8.py:130-142 sucht automatisch `custom_benchmark_v*.py` mit höchster Version – kein Hardcode nötig

3. **Robustes CSV-Handling**  
   - Fallback auf `tasks_*`-Namen (neue Pipeline) und `2026*_*`-Format (alte Pipeline)
   - Auto-Delimiter-Erkennung (`,` oder `;`) mit Semikolon als Standard
   - Spalten-Aliase (z.B. `latency`/`latency_s`)

4. **Gewichtungssystem**  
   - `compute_category_scores()` normalisiert automatisch nach verfügbaren Benchmarks
   - Kategorien: Coding (35%), Math (25%), Agentic (25%), Knowledge (15%)
   - Fehlende Benchmarks werden übersprungen ohne Null-Score

5. **Modell-Timeout-Konfiguration**  
   - PIPELINE_TIMEOUTS in model_manager_v3.py zentral definiert
   - Basis-Werte werden bei Reasoning-Modellen automatisch verdoppelt

### Schwächen / Probleme

1. **Zwei parallele Dateiformate**  
   - Alte Pipeline: `20260617_193457_DS1000_Modell.csv`  
   - Neue Pipeline: `tasks_20260617_193457_DS1000_Modell.csv`  
   - consolidate_results_v9.py muss beide parsen → erhöhte Komplexität (find_latest_csvs hat zwei fast identische Blöcke)

2. **Kein zentrales Test-Framework**  
   - Es gibt keine automatisierten Tests für die Kernlogik (z.B. compute_category_scores, CSV-Parsing, Weight-Normalisierung)
   - Änderungen müssen manuell per Voll-Durchlauf getestet werden

3. **Versionsnummern-Chaos**  
   - Historisch gewachsen: `v23` bis `v25`, `v2`/`v3`, `v7`/`v11` – uneinheitliches Schema  
   - Interne Nummern waren z.T. asynchron zum Dateinamen (z.B. filename v24, intern v25)
   - Legacy-Wrapper (run_all_dense.py, rerun_lmeval.py) rufen `run_benchmarks_v3.py` auf – nicht die aktuelle v8

4. **Harter Code in Tool-Eval-Bench**  
   - `run_benchmarks_v8.py` startet `tool_eval_bench` fest verdrahtet (Pfad, Args, Modell)
   - Kein dynamisches Discovery (anders als custom_benchmark)

5. **System-Metriken-Mischung**  
   - CPU/GPU/RAM/VRAM werden über alle Custom-Benchmarks (DS1000, CoderEval) gemittelt  
   - Mischung von Per-Task-Peak (`cpu_during`) und Benchmark-Gesamt-Maximum führt zu uneinheitlichen Werten

6. **Legacy-Skripte im Hauptverzeichnis**  
   - `benchmark_lmstudio_v18.py`–`v22.py`, `consolidate_results_v6.py`–`v7.py`, etc. liegen direkt im Hauptverzeichnis  
   - Nur manuell ausgelagerte Versionen liegen in `alte_skripte/`
   - Erschwert Auffindbarkeit der aktiven Skripte

7. **Keine Typprüfung**  
   - Keine Type Hints in den Kernmodulen (trotz Python 3.10+)
   - `consolidate_results_v9.py` mischt `int`, `float`, `str`, `None` in Dicts ohne Struktur

8. **Konfiguration über Kommentare**  
   - WHITELIST, DISPLAY_NAMES, CAT_WEIGHTS, OVERALL_WEIGHTS sind hardcoded in `consolidate_results_v9.py`
   - Änderungen erfordern Code-Eingriffe, keine externe Konfiguration

9. **Fehlerbehandlung inkonsistent**  
   - `read_custom_csv()` gibt `None` bei Fehlern → Caller müssen prüfen  
   - `try_read_evalplus()` fängt Exceptions intern und gibt `None` zurück  
   - Lesbarkeit leidet unter Try/Except-Vielfalt

---

## 4. Detailkritik pro Skript

### model_manager_v3.py (210 Zeilen) ⭐⭐⭐⭐⭐
- Sauberste Einheit: klare API, keine Seiteneffekte
- Einzige Schwäche: `API_BASE` ist hardcoded auf `localhost:1234`

### csv_writer_v3.py (330 Zeilen) ⭐⭐⭐⭐
- Gut strukturiert, vier klar getrennte CSV-Typen
- Backward-Compat-Aliase (save_csv etc.) erhöhen Wartungskosten
- Felddefinitionen redundant zwischen `write_*`-Funktionen und Feld-Listen

### custom_benchmark_v25.py (1743 Zeilen) ⭐⭐⭐
- ✅ Dynamischer JSONL-Loader
- ✅ Korrekter Per-Task-Output mit GPU/CPU/Latenz
- ❌ Zu lang: enthält Legacy-Code (interaktiver Modus, PandasEval-Reste)
- ❌ Kein Task-Retry-Mechanismus
- ❌ Zwei Code-Pfade für DS1000 (altes Format + neues Format nebeneinander)

### run_benchmarks_v8.py (997 Zeilen) ⭐⭐⭐
- ✅ Gute Pipeline-Orchestrierung
- ✅ Dynamische custom_benchmark-Erkennung
- ❌ `run_lmeval()` und `run_evalplus()` fast identisch → hohe Redundanz
- ❌ MMLU-Pro-Subset-Logik ist 150 Zeilen inline (besser auslagern)
- ❌ Fehlerbehandlung in Parallelverarbeitung fehlt

### consolidate_results_v9.py (914 Zeilen) ⭐⭐⭐
- ✅ Flexible CSV-Einleseroutine mit Auto-Delimiter
- ✅ TOP5/BOTTOM5/Benchmark-Tabellen im MD
- ❌ Spaltenbreiten-Logik doppelt (`widths` + `widths2`)
- ❌ Kein Caching: liest alle CSVs jedes Mal neu
- ❌ Keine inkrementelle Aktualisierung

---

## 5. Empfehlungen

1. **Alte Skripte aufräumen**: Alle `benchmark_lmstudio_v18–v22`, `consolidate_v6–v7`, `run_benchmarks_v1–v6` in `alte_skripte/` verschieben
2. **Tests einführen**: `pytest` für `compute_category_scores()`, `read_custom_csv()`, `find_latest_csvs()` mit Fixtures aus echten CSV-Dateien
3. **Type Hints**: Alle Funktionen in den 5 Kernskripten typisieren
4. **Konfiguration externalisieren**: `WHITELIST`, `DISPLAY_NAMES`, `CAT_WEIGHTS`, `OVERALL_WEIGHTS` in YAML/JSON auslagern
5. **Parallel-Execution verbessern**: `run_evalplus()` und `run_lmeval()` in eine generische `run_subprocess()`-Funktion überführen
6. **Einheitliches Dateinamen-Schema**: `tasks_` für alle Custom-Benchmarks, `modell_` für alles andere – `find_latest_csvs` vereinfachen
7. **MMLU-Pro-Logik auslagern**: In eigene Funktion/Modul (überschaubar + testbar)
8. **Legacy-Wrapper aktualisieren**: `run_all_dense.py` etc. auf aktuelle `run_benchmarks_v8.py` umstellen

---

*Review erstellt aus Code-Analyse der 5 Kernskripte + 6 Hilfsskripte.*
*Alle Pfade relativ zu `C:\Users\pskra\Python-Projekte\Benchmarks\`.*
