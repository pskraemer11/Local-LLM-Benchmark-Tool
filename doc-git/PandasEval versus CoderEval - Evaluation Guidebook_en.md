## PandasEval versus CoderEval - Evaluation Guidebook – Relevant Notes

The [huggingface/evaluation-guidebook](https://github.com/huggingface/evaluation-guidebook) recommends:

1. **"Look at the data, both what you have, what the model generates, and its scores"** – We have done this.
2. **"You need benchmarks that match your specific use case"** – PandasEval tests whether models know specific Pandas APIs, not whether they can "code well".
3. **"Evaluations provide strong signal"** – 10 tasks at 0-12% yield **no differentiating signal**. A model scoring 0% vs. 12% is barely distinguishable.
4. **"Common pitfalls: tests that are too specific, prompts that hide context"** – Both apply here.

---
New benchmark: CoderEval

## 1. Systematic Causes of the 0-12% Scores on PandasEval

After analyzing the per-task CSVs and the evaluation code, I **identified three systematic errors**:

### **A) Setup Code (DataFrame schema) is NOT passed in the prompt**

In `benchmark_lmstudio_v20.py:848-856`, the prompt is built only from `task["prompt"]` – the `setup_code` (which defines the test DataFrames) is **completely missing**:

```python
request_prompt = (
    "Complete the following Python function using pandas. "
    "Output only the function code, no additional text.\n\n"
    f"{prompt}"      # <-- only the generic description
)
```

Example task 5 (`assign_derived`):
- Prompt: *"Create a function that uses assign() with lambda to add multiple derived columns in a single chain."*
- Setup code (**hidden** from model): `pd.DataFrame({'price': [50, 150], 'quantity': [2, 1]})`
- Test expects: columns `'total'`, `'discounted'`, `'category'`
- Models guess column names like `'a'`, `'b'`, `'column1'`, `'derived1'` → **0/1**

This is the **main cause** of systematic failure. The model cannot guess the column names since they are neither in the prompt nor passed as function parameters (but hardcoded in the solution).

### **B) Tests check for exact column names instead of functional behavior**

The tests are **implementation-specific** rather than **behavior-oriented**. Example:

| Task              | Prompt says                                | Test checks                                                                 |
|-------------------|--------------------------------------------|-----------------------------------------------------------------------------|
| 1 (explode_and_agg) | "explodes a DF column… computes mean…"    | `isinstance(result, pd.DataFrame)` + columns `'categories'`, `'score'`    |
| 5 (assign_derived)  | "add multiple derived columns"            | columns `'total'`, `'discounted'`, `'category'`                              |
| 7 (eval_expression) | "compute a new column from an expression" | column `'ratio'`                                                            |

The canonical solution for task 1 uses `.reset_index()`, which returns a DataFrame. Models that return only a Series without `.reset_index()` **or** that use `.reset_index()` but with different column naming fail, even if the logic is correct.

### **C) Sandbox removes `eval` from builtins**

In `_build_sandbox_script:551-552`, among others, `eval` and `compile` are removed from builtins:

```python
"for _bd_rm in ('eval', 'exec', 'open', 'input', 'compile', 'globals', 'locals', 'vars'):",
```

DeepSeek Coder v2 Lite generates for task 7: `df['new_column'] = eval(expr)` → **fails** because `eval` does not exist. Models using `df.eval()` are not affected (pandas internal eval usage bypasses the restricted namespace), but the error is hard to debug.

---

## 2. Code Review: `benchmark_lmstudio_v20.py` – Critical Findings

| Location   | Problem                                                                                             | Severity  |
|------------|-----------------------------------------------------------------------------------------------------|-----------|
| `L.848-856`| `setup_code` missing from prompt                                                                    | **High**  |
| `L.551-552`| `eval`, `compile` removed, but pandas may internally require them                                   | Medium (only for explicit `eval()` call) |
| `L.364-368`| `extract_code()` fallback: only captures lines matching `_is_bare_statement` – misses code without function definition | Low       |
| `L.371-427`| `_repair_indentation()` fixes indentation errors but cannot fix syntax errors                       | Medium    |
| `L.475-510`| Sandbox blocks `os`, `subprocess` etc. – sensible, but debugging is harder when errors occur        | Low       |
|   `L.51`   | `SAMPLE_SIZE=8` with only 10 tasks – statistically weak signal                                       | Medium    |



===============================================

## 4. CoderEval – Suitability and Docker Check

**CoderEval** ([GitHub](https://github.com/CoderEval/CoderEval)): 230 Python functions from 43 real open-source projects with 6 Runnable levels (self_contained → project_runnable).

### Can CoderEval run without Docker?

**Partially yes, with limitations:**

- The JSON data is readable standalone (`CoderEval4Python.json`): 230 entries with `docstring`, `code`, `file_content`, `dependency`, `level`
- *`self_contained`* and **`slib_runnable`* (standard library dependencies only): ~60% of tasks – could be evaluated with the existing sandbox approach,
  after adapting `extract_code` and the evaluation framework
- *`plib_runnable` / `class_runnable` / `file_runnable` / `project_runnable`*: require external packages or full project repos → *not practical without Docker* (would need to clone 43 GitHub repos + set up environments)

### CoderEval vs. PandasEval

| Criterion       | PandasEval (current)                   | CoderEval                                                           |
|-----------------|----------------------------------------|---------------------------------------------------------------------|
| Tasks           | 10 (self-created)                      | 230 (from real projects)                                            |
| Tests           | Assertions with hardcoded column names | Real unit tests from OSS projects                                   |
| Coverage        | Pandas only                            | Databases, web frameworks, data processing, etc.                    |
| Prompt Quality  | Vague (without context)                | Docstrings + File context                                           |
| Signal Strength | Weak (0-12% across all)                | Stronger (more differentiated scores)                               |
| Docker Required | No                                     | Yes (for full evaluation)                                           |

### Recommendation

CoderEval is **in principle better suited** than the self-created PandasEval tasks, but:
- For **non-Docker operation**, only the `self_contained` and `slib_runnable` tasks would need to be extracted (approx. 60% of 230 ≈ 138 tasks)
- The `CoderEval4Python.json` would need to be adapted to fit the existing `simple_evals/` schema (with extractable test assertions)
- Docker-free usage requires adapting the evaluation wrapper (currently designed for insert-based DS1000 harness + direct tests)

## Immediate Actions
1. ...
2. ...
3. **Evaluate CoderEval**: extract `level: "self_contained"` tasks from `CoderEval4Python.json` and include them in the pipeline
