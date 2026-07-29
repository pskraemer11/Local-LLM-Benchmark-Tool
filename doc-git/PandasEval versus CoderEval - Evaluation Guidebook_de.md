## PandasEval versus CoderEval - Evaluation Guidebook – Relevante Hinweise

Die [huggingface/evaluation-guidebook](https://github.com/huggingface/evaluation-guidebook) empfiehlt:

1. **"Look at the data, both what you have, what the model generates, and its scores"** – Das haben wir getan.
2. **"You need benchmarks that match your specific use case"** – PandasEval testet ob Modelle spezifische Pandas-APIs kennen, nicht ob sie "gut coden" können.
3. **"Evaluations provide strong signal"** – 10 Aufgaben mit 0-12% liefern **kein differenzierendes Signal**. Ein Modell das 0% hat vs. 12% unterscheidet sich kaum.
4. **"Common pitfalls: tests that are too specific, prompts that hide context"** – Beides hier zutreffend.

---
neue Benchmark: CoderEval

## 1. Systematische Ursachen für die 0-12%-Scores bei PandasEval

Nach Analyse der Per-Task-CSVs und des Evaluations-Codes habe ich **drei systematische Fehler identifiziert**:

### **A) Setup-Code (DataFrame-Schema) wird NICHT im Prompt übermittelt**

In `benchmark_lmstudio_v20.py:848-856` wird der Prompt nur aus `task["prompt"]` gebaut – der `setup_code` (der die Test-DataFrames definiert) **fehlt komplett**:

```python
request_prompt = (
    "Complete the following Python function using pandas. "
    "Output only the function code, no additional text.\n\n"
    f"{prompt}"      # <-- nur die generische Beschreibung
)
```

Beispiel Aufgabe 5 (`assign_derived`):
- Prompt: *"Create a function that uses assign() with lambda to add multiple derived columns in a single chain."*
- Setup-Code (dem Modell **verborgen**): `pd.DataFrame({'price': [50, 150], 'quantity': [2, 1]})`
- Test erwartet: Spalten `'total'`, `'discounted'`, `'category'`
- Modelle raten Spaltennamen wie `'a'`, `'b'`, `'column1'`, `'derived1'` → **0/1**

Das ist der **Hauptgrund** für das systematische Scheitern. Das Modell kann die Spaltennamen nicht erraten, da sie weder im Prompt noch als Funktionsparameter übergeben werden (sondern hardgecoded in der Lösung sind).

### **B) Tests prüfen auf exakte Spaltennamen statt funktionales Verhalten**

Die Tests sind **implementierungsspezifisch** statt **verhaltensorientiert**. Bsp:

| Aufgabe             | Prompt sagt                               | Test prüft 								                               |
|---------------------|-------------------------------------------|------------------------------------------------------------------------|
| 1 (explode_and_agg) | "explodes a DF column… computes mean…"    | `isinstance(result, pd.DataFrame)` + columns `'categories'`, `'score'` |
| 5 (assign_derived)  | "add multiple derived columns"            | columns `'total'`, `'discounted'`, `'category'`  			           |
| 7 (eval_expression) | "compute a new column from an expression" | column `'ratio'` 							                           |

Die Kanonische Lösung für Aufgabe 1 nutzt `.reset_index()`, was einen DataFrame liefert. Modelle, die ohne `.reset_index()` nur eine Series retournieren **oder** mit `.reset_index()` aber anderem Column-Naming scheitern, auch wenn die Logik korrekt ist.

### **C) Sandbox entfernt `eval` aus Builtins**

In `_build_sandbox_script:551-552` werden unter anderem `eval` und `compile` aus den Builtins entfernt:

```python
"for _bd_rm in ('eval', 'exec', 'open', 'input', 'compile', 'globals', 'locals', 'vars'):",
```

DeepSeek Coder v2 Lite generiert für Aufgabe 7: `df['new_column'] = eval(expr)` → **schlägt fehl**, weil `eval` nicht existiert. Modelle die `df.eval()` verwenden sind nicht betroffen (pandas interne eval-Nutzung geht über globale Builtins, nicht die restricted namespace), aber der Fehler ist schwer nachvollziehbar.

---

## 2. Code-Review: `benchmark_lmstudio_v20.py` – Kritische Fundstellen

| Fundstelle  | Problem 										                                            | Schwere  |
|-------------|---------------------------------------------------------------------------------------------|----------|
| `Z.848-856` | `setup_code` fehlt im Prompt 					  			                                | **Hoch** |
| `Z.551-552` | `eval`, `compile` entfernt, aber pandas intern benötigt diese ggf. 			                | Mittel (nur bei explizitem `eval()`-Aufruf) |
| `Z.364-368` | `extract_code()` Fallback: erfasst nur Zeilen die `_is_bare_statement` entsprechen – 	    | Niedrig  |
                    verpasst Code ohne Funktionsdefinition 						                            |	       |
| `Z.371-427` | `_repair_indentation()` repariert Einrückungsfehler, kann aber Syntaxfehler nicht beheben   | Mittel   |
| `Z.475-510` | Sandbox blockiert `os`, `subprocess` etc. – sinnvoll, aber Debugging bei Fehlern erschwert  | Niedrig  |
|   `Z.51`    | `SAMPLE_SIZE=8` bei nur 10 Aufgaben – statistisch schwaches Signal 			                | Mittel   |



===============================================

## 4. CoderEval – Eignung und Docker-Prüfung

**CoderEval** ([GitHub](https://github.com/CoderEval/CoderEval)): 230 Python-Funktionen aus 43 realen Open-Source-Projekten mit 6 Runnable-Levels (self_contained → project_runnable).

### Kann CoderEval ohne Docker laufen?

**Teilweise ja, mit Einschränkungen:**

- Die JSON-Daten sind standalone lesbar (`CoderEval4Python.json`): 230 Einträge mit `docstring`, `code`, `file_content`, `dependency`, `level`
- *`self_contained`* und **`slib_runnable`* (nur Standard-Lib-Abhängigkeiten): ~60% der Aufgaben – könnten mit dem bestehenden Sandbox-Ansatz evaluiert werden, 
	nachdem `extract_code` und das Evaluations-Framework angepasst wurden
- *`plib_runnable` / `class_runnable` / `file_runnable` / `project_runnable`*: benötigen externe Pakete oder ganze Projekt-Repos → *ohne Docker nicht praktikabel* (müssten 43 GitHub-Repos klonen + Umgebungen aufsetzen)

### CoderEval vs. PandasEval

| Kriterium 	 | PandasEval (aktuell) 		      | CoderEval 						                     |
|----------------|------------------------------------|------------------------------------------------------|
| Aufgaben 	     | 10 (selbst erstellt) 		      | 230 (aus realen Projekten) 				             |
| Tests 	     | Assertions mit harten Column-Namen | Echte Unit-Tests aus OSS-Projekten 			         |
| Abdeckung 	 | Nur Pandas 				          | Datenbanken, Web-Frameworks, Datenverarbeitung, etc. |
| Prompt-Güte 	 | Vage (ohne Kontext) 			      | Docstrings + File-Context 				             |
| Signalstärke 	 | Schwach (0-12% bei allen) 		  | Stärker (differenziertere Scores) 			         |
| Docker-Pflicht | Nein 				              | Ja (für vollständige Evaluation) 			         |

### Empfehlung

CoderEval ist **prinzipiell besser geeignet** als die selbst erstellten PandasEval-Aufgaben, aber:
- Für **non-Docker-Betrieb** müssten nur die `self_contained`- und `slib_runnable`-Aufgaben extrahiert werden (ca. 60% von 230 ≈ 138 Tasks)
- Der `CoderEval4Python.json` müsste so aufbereitet werden, dass er ins bestehende `simple_evals/`-Schema passt (mit extrahierbaren Test-Assertions)
- Docker-freie Nutzung erfordert Anpassung des Evaluations-Wrappers (derzeit auf Insert-basierte DS1000-Harness + direkte Tests ausgelegt)

## Sofort-Maßnahmen
1. ... 
2. ... 
3. **CoderEval evaluieren**: `level: "self_contained"` Aufgaben aus `CoderEval4Python.json` extrahieren und in Pipeline aufnehmen

