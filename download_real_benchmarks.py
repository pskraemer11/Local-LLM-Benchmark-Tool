#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Laedt ALLE verfuegbaren Benchmark-Datensaetze von HuggingFace und anderen Quellen
herunter und speichert sie als JSONL-Dateien im simple_evals/ Ordner.
Jede Aufgabe erhaelt ein _group-Feld fuer die spaetere Subsampling-Logik
in custom_benchmark_v11.py (subsample_tasks()).

Quellen: HumanEval+, MathQA, MBPP+, DS1000, BBH, MMLU, MMLU-Pro,
         ARC-Challenge, TruthfulQA, HellaSwag, PandasEval
"""

import json
import os
import sys
import requests
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "simple_evals")
os.makedirs(DATA_DIR, exist_ok=True)

TIMEOUT = 60


def save_jsonl(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  [OK] {filename}: {len(data)} Eintraege -> {path}")
    return path


def fetch_jsonl_from_hf(dataset_name, split="test"):
    url = f"https://datasets-server.huggingface.co/first-rows?dataset={dataset_name}&config=default&split={split}"
    print(f"  [INFO] Lade {dataset_name} ({split})...")
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code != 200:
        print(f"  [WARN] API Fehler {r.status_code}: {dataset_name}")
        return None
    data = r.json()
    rows = data.get("rows", [])
    return [row["row"] for row in rows]


def main():
    print("  Modus: ALLE Fragen")
    print(f"  Ausgabeordner: {DATA_DIR}")

    # ─────────────────── 1. CODING: HumanEval+ ───────────────────
    print("\n" + "=" * 60)
    print("  1. HumanEval+ (Coding) - ALLE")
    print("=" * 60)

    coding_data = []
    try:
        from evalplus.data import get_human_eval_plus

        he_plus = get_human_eval_plus()
        all_ids = list(he_plus.keys())
        for task_id in all_ids:
            p = he_plus[task_id]
            coding_data.append({
                "prompt": p["prompt"],
                "entry_point": p["entry_point"],
                "tests": [p["test"]],
                "canonical_solution": p.get("canonical_solution", ""),
                "task_id": task_id,
                "type": "coding",
                "base_input": p.get("base_input", []),
                "plus_input": p.get("plus_input", []),
                "contract": p.get("contract", ""),
                "atol": p.get("atol", 0),
                "_group": "coding",
            })
        print(f"  [OK] HumanEval+: {len(coding_data)} Probleme (alle {len(he_plus)})")
    except ImportError:
        print("  [WARN] evalplus nicht installiert. Fallback auf human_eval package...")
        try:
            from human_eval.data import read_problems
            problems = read_problems()
            all_ids = list(problems.keys())
            for task_id in all_ids:
                p = problems[task_id]
                coding_data.append({
                    "prompt": p["prompt"],
                    "entry_point": p["entry_point"],
                    "tests": [p["test"]],
                    "canonical_solution": p.get("canonical_solution", ""),
                    "task_id": task_id,
                    "type": "coding",
                    "_group": "coding",
                })
            print(f"  [OK] HumanEval (Fallback): {len(coding_data)} Probleme (alle {len(all_ids)})")
        except Exception as e:
            print(f"  [ERROR] HumanEval nicht verfuegbar: {e}")

    save_jsonl("coding.jsonl", coding_data)

    # ─────────────────── 2. MATH: MathQA ───────────────────
    print("\n" + "=" * 60)
    print("  2. MathQA (Mathematik, Multiple Choice) - ALLE Kategorien")
    print("=" * 60)

    math_data = []
    mathqa_categories = ["gain", "general", "geometry", "other", "physics", "probability"]
    try:
        import zipfile, io
        import requests as req
        url = "https://math-qa.github.io/math-QA/data/MathQA.zip"
        print(f"  [INFO] Lade MathQA von {url}...")
        r = req.get(url, timeout=60)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            with z.open("test.json") as f:
                all_data = json.load(f)
            by_cat = defaultdict(list)
            for item in all_data:
                by_cat[item["category"]].append(item)
            for cat in sorted(mathqa_categories):
                pool = by_cat.get(cat, [])
                for item in pool:
                    problem = item["Problem"]
                    options_raw = item["options"]
                    answer = item["correct"].strip().lower()
                    choices_text = options_raw
                    prompt = f"{problem}\n\n{choices_text}"
                    entry = {
                        "prompt": prompt,
                        "answer": answer,
                        "category": cat,
                        "type": "math",
                        "_group": cat,
                    }
                    math_data.append(entry)
                print(f"    {cat}: {len(pool)} verfuegbar, nehme alle")
            save_jsonl("math.jsonl", math_data)
            print(f"  [OK] MathQA: {len(math_data)} Aufgaben (alle)")
        else:
            print(f"  [ERROR] MathQA Download: HTTP {r.status_code}")
            save_jsonl("math.jsonl", [])
    except Exception as e:
        print(f"  [ERROR] MathQA Download fehlgeschlagen: {e}")
        save_jsonl("math.jsonl", [])

    # ─────────────────── 3. ALGORITHMIC: MBPP+ ───────────────────
    print("\n" + "=" * 60)
    print("  3. MBPP+ (Algorithmen) - ALLE")
    print("=" * 60)

    algo_data = []
    try:
        import urllib.request, gzip
        url = "https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz"
        print(f"  [INFO] Lade MBPP+ von GitHub...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        content = gzip.decompress(raw).decode("utf-8")
        all_tasks = [json.loads(l) for l in content.strip().split("\n") if l.strip()]
        for t in all_tasks:
            algo_data.append({
                "prompt": t["prompt"],
                "entry_point": t.get("entry_point", ""),
                "canonical_solution": t.get("canonical_solution", ""),
                "assertion": t.get("assertion", ""),
                "base_input": t.get("base_input", []),
                "plus_input": t.get("plus_input", []),
                "atol": t.get("atol", 0),
                "type": "algorithmic",
                "_group": "mbpp",
            })
        save_jsonl("algorithmic.jsonl", algo_data)
        print(f"  [OK] MBPP+: {len(algo_data)} Aufgaben (alle {len(all_tasks)})")
    except Exception as e:
        print(f"  [ERROR] MBPP+ Download fehlgeschlagen: {e}")

    # ─────────────────── 4. DATA SCIENCE: DS1000 ───────────────────
    DS1000_LIBS = ["Matplotlib", "Numpy", "Pandas", "Scipy", "Sklearn"]
    EXCLUDE_LIBS = {"Pytorch", "Tensorflow"}

    print("\n" + "=" * 60)
    print("  4. Data Science (DS1000) - ALLE Libraries")
    print("=" * 60)

    ds_data = []
    try:
        import datasets
        ds = datasets.load_dataset("xlangai/DS-1000", split="test")
        per_library = defaultdict(list)
        for item in ds:
            lib = item["metadata"]["library"]
            per_library[lib].append(item)

        print("  Verteilung:")
        for lib in DS1000_LIBS:
            items = per_library.get(lib, [])
            if not items:
                print(f"    {lib}: 0 verfuegbar")
                continue
            for item in items:
                entry = {
                    "prompt": item.get("prompt", ""),
                    "type": "data_science",
                    "entry_point": item.get("entry_point", ""),
                    "tests": item.get("test", []),
                    "reference_code": item.get("reference_code", ""),
                    "code_context": item.get("code_context", ""),
                    "library": lib,
                    "_group": lib,
                }
                ds_data.append(entry)
            print(f"    {lib}: {len(items)} verfuegbar, nehme alle")
        for lib in sorted(per_library.keys()):
            if lib in EXCLUDE_LIBS:
                print(f"    {lib}: {len(per_library[lib])} verfuegbar, UEBERSPRUNGEN")
        save_jsonl("data_science.jsonl", ds_data)
        total_libs = len(set(d.get('library') for d in ds_data))
        print(f"  [OK] DS1000: {len(ds_data)} Aufgaben aus {total_libs} Libraries")
    except Exception as e:
        print(f"  [WARN] DS1000 Download fehlgeschlagen: {e}")
        placeholder = [{"prompt": "DS1000 Benchmark nicht verfuegbar", "type": "data_science"}]
        save_jsonl("data_science.jsonl", placeholder)

    # ─────────────────── 5. REASONING: BBH ───────────────────
    print("\n" + "=" * 60)
    print("  5. BBH (Reasoning) - ALLE")
    print("=" * 60)

    bbh_subsets_hf = {
        "boolean_expressions": "boolean_expressions",
        "causal_judgement": "causal_judgment",
        "date_understanding": "date_understanding",
        "disambiguation_qa": "disambiguation_qa",
        "formal_fallacies": "formal_fallacies",
        "geometric_shapes": "geometric_shapes",
        "hyperbaton": "hyperbaton",
        "logical_deduction_three_objects": "logical_deduction_three_objects",
        "navigate": "navigate",
        "object_counting": "object_counting",
        "penguins_in_a_table": "penguins_in_a_table",
        "reasoning_about_colored_objects": "reasoning_about_colored_objects",
        "ruin_names": "ruin_names",
        "snarks": "snarks",
        "temporal_sequences": "temporal_sequences",
        "tracking_shuffled_objects_three_objects": "tracking_shuffled_objects_three_objects",
        "web_of_lies": "web_of_lies",
        "word_sorting": "word_sorting",
    }

    reasoning_data = []
    try:
        import datasets
        for hf_name, display_name in bbh_subsets_hf.items():
            ds = datasets.load_dataset("Joschka/big_bench_hard", hf_name, split=hf_name)
            all_items = list(ds)
            for item in all_items:
                reasoning_data.append({
                    "prompt": item.get("input", item.get("question", "")),
                    "answer": item.get("target", item.get("answer", "")),
                    "subset": display_name,
                    "type": "reasoning",
                    "_group": display_name,
                })
            print(f"    {display_name}: {len(all_items)} verfuegbar, nehme alle")
        save_jsonl("reasoning.jsonl", reasoning_data)
        print(f"  [OK] BBH: {len(reasoning_data)} Aufgaben (alle)")
    except Exception as e:
        print(f"  [WARN] BBH via HuggingFace fehlgeschlagen: {e}")
        print("  [INFO] Versuche GitHub Raw Fallback...")
        for hf_name, display_name in bbh_subsets_hf.items():
            url = f"https://raw.githubusercontent.com/suzgunmirac/BIG-Bench-Hard/main/bbh/{display_name}.json"
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    examples = data.get("examples", [])
                    for ex in examples:
                        reasoning_data.append({
                            "prompt": ex.get("input", ""),
                            "answer": ex.get("target", ""),
                            "subset": display_name,
                            "type": "reasoning",
                            "_group": display_name,
                        })
                    print(f"    {display_name}: {len(examples)} verfuegbar, nehme alle (GitHub)")
            except Exception:
                print(f"    {display_name}: Fehler beim Laden (GitHub)")
        if reasoning_data:
            save_jsonl("reasoning.jsonl", reasoning_data)
            print(f"  [OK] BBH (GitHub): {len(reasoning_data)} Aufgaben")

    # ─────────────────── 6. UNDERSTANDING: MMLU ───────────────────
    print("\n" + "=" * 60)
    print("  6. MMLU (Sprachverstaendnis) - ALLE")
    print("=" * 60)

    mmlu_data = []
    try:
        import datasets
        print("  [INFO] Lade MMLU (57 Fachgebiete, 'all' config)...")
        ds = datasets.load_dataset("leiliu-710072/mmlu", "all", split="test")

        for item in ds:
            choices = item.get("choices", [])
            answer_idx = item.get("answer", 0)
            choices_text = "\n".join([f"{chr(65+i)}) {c}" for i, c in enumerate(choices)])
            prompt = f"{item.get('question', '')}\n\n{choices_text}"
            answer_letter = chr(65 + answer_idx) if isinstance(answer_idx, int) and answer_idx < len(choices) else str(answer_idx)
            mmlu_data.append({
                "prompt": prompt,
                "answer": answer_letter,
                "subject": item.get("subject", ""),
                "type": "understanding",
                "_group": item.get("subject", "unknown"),
            })
        save_jsonl("understanding.jsonl", mmlu_data)
        print(f"  [OK] MMLU: {len(mmlu_data)} Aufgaben (alle)")
    except Exception as e:
        print(f"  [ERROR] MMLU Download fehlgeschlagen: {e}")

    # ─────────────────── 7. COMPLEX TASKS: MMLU-Pro ───────────────────
    print("\n" + "=" * 60)
    print("  7. Complex Tasks (MMLU-Pro) - ALLE")
    print("=" * 60)

    complex_data = []
    try:
        import datasets
        print("  [INFO] Lade MMLU-Pro...")
        ds = datasets.load_dataset("TIGER-Lab/MMLU-Pro", split="test")

        all_items = list(ds)
        has_categories = "category" in (all_items[0] if all_items else {})
        by_category = defaultdict(list)
        for item in all_items:
            by_category[item.get("category", "unknown")].append(item)
        if has_categories:
            print(f"  [INFO] {len(by_category)} Kategorien, ALLE {len(all_items)} Aufgaben")
        else:
            print(f"  [INFO] Keine Kategorien, {len(all_items)} Aufgaben")

        for item in all_items:
            question = item.get("question", item.get("prompt", ""))
            choices = item.get("options", [])
            choices_text = "\n".join([f"{chr(65+j)}) {c}" for j, c in enumerate(choices)]) if choices else ""
            answer = item.get("answer", "")
            if isinstance(answer, int) and choices:
                answer = chr(65 + answer) if 0 <= answer < len(choices) else str(answer)
            full_prompt = f"{question}\n\n{choices_text}" if choices_text else question
            entry = {
                "prompt": full_prompt,
                "type": "complex",
                "answer": str(answer),
            }
            if has_categories:
                entry["_group"] = item.get("category", "unknown")
            complex_data.append(entry)
        save_jsonl("complex_tasks.jsonl", complex_data)
        print(f"  [OK] MMLU-Pro: {len(complex_data)} Aufgaben (alle)")
    except Exception as e:
        print(f"  [WARN] MMLU-Pro Download fehlgeschlagen: {e}")
        save_jsonl("complex_tasks.jsonl", [])

    # ─────────────────── 8. ARC-CHALLENGE ───────────────────
    print("\n" + "=" * 60)
    print("  8. ARC-Challenge (Science Reasoning) - ALLE")
    print("=" * 60)

    science_data = []
    try:
        import datasets
        ds = datasets.load_dataset("allenai/ai2_arc", "ARC-Challenge", split="test")
        all_items = list(ds)
        for item in all_items:
            question = item["question"]
            texts = item["choices"]["text"]
            choices_text = "\n".join([f"{chr(65+i)}) {t}" for i, t in enumerate(texts)])
            raw_key = item["answerKey"]
            if raw_key in ("1", "2", "3", "4"):
                answer = chr(65 + int(raw_key) - 1)
            else:
                answer = raw_key
            prompt = f"{question}\n\n{choices_text}"
            science_data.append({
                "prompt": prompt,
                "answer": answer,
                "type": "science",
                "_group": "arc_challenge",
            })
        if science_data:
            save_jsonl("science.jsonl", science_data)
            print(f"  [OK] ARC-Challenge: {len(science_data)} Aufgaben (alle {len(all_items)})")
        else:
            print("  [WARN] ARC-Challenge leer, versuche Fallback...")
            raise Exception("Leer")
    except Exception as e:
        print(f"  [WARN] ARC-Challenge Download fehlgeschlagen: {e}")
        try:
            import requests
            url = "https://raw.githubusercontent.com/allenai/ARC/master/data/ARC-Challenge/ARC-Challenge-Test.jsonl"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                lines = [json.loads(l) for l in r.text.strip().split("\n") if l.strip()]
                for item in lines:
                    question = item.get("question", {}).get("stem", "")
                    choices_raw = item.get("question", {}).get("choices", [])
                    choices_text = "\n".join([f"{chr(65+i)}) {c['text']}" for i, c in enumerate(choices_raw)])
                    raw_key = item.get("answerKey", "")
                    if raw_key in ("1", "2", "3", "4"):
                        answer = chr(65 + int(raw_key) - 1)
                    else:
                        answer = raw_key
                    prompt = f"{question}\n\n{choices_text}"
                    science_data.append({
                        "prompt": prompt,
                        "answer": answer,
                        "type": "science",
                        "_group": "arc_challenge",
                    })
                if science_data:
                    save_jsonl("science.jsonl", science_data)
                    print(f"  [OK] ARC-Challenge (GitHub): {len(science_data)} Aufgaben (alle)")
            else:
                print(f"  [ERROR] ARC GitHub: HTTP {r.status_code}")
                save_jsonl("science.jsonl", [])
        except Exception as e2:
            print(f"  [ERROR] ARC Fallback fehlgeschlagen: {e2}")
            save_jsonl("science.jsonl", [])

    # ─────────────────── 9. TRUTHFULQA ───────────────────
    print("\n" + "=" * 60)
    print("  9. TruthfulQA (Faktenwahrheit) - ALLE (MC1)")
    print("=" * 60)

    truth_data = []
    try:
        import datasets
        ds = datasets.load_dataset("truthfulqa/truthful_qa", "multiple_choice", split="validation")
        for item in ds:
            mc1 = item["mc1_targets"]
            labels = mc1["labels"]
            correct_idx = next((i for i, lbl in enumerate(labels) if lbl == 1), None)
            if correct_idx is not None:
                question = item["question"]
                choices = item["mc1_targets"]["choices"]
                choices_text = "\n".join([f"{chr(65+i)}) {c}" for i, c in enumerate(choices)])
                prompt = f"{question}\n\n{choices_text}"
                truth_data.append({
                    "prompt": prompt,
                    "answer": chr(65 + correct_idx),
                    "type": "truthfulness",
                    "_group": "truthfulqa",
                })
        save_jsonl("truthfulness.jsonl", truth_data)
        print(f"  [OK] TruthfulQA: {len(truth_data)} Aufgaben (alle validen)")
    except Exception as e:
        print(f"  [WARN] TruthfulQA Download fehlgeschlagen: {e}")
        save_jsonl("truthfulness.jsonl", [])

    # ─────────────────── 10. HELLASWAG ───────────────────
    print("\n" + "=" * 60)
    print("  10. HellaSwag (Commonsense Reasoning) - ALLE")
    print("=" * 60)

    commonsense_data = []
    try:
        import datasets
        ds = datasets.load_dataset("Rowan/hellaswag", split="validation")
        for item in ds:
            label = item.get("label", "")
            if label in ("0", "1", "2", "3"):
                ctx = item["ctx"]
                endings = item["endings"]
                correct_idx = int(item["label"])
                choices_text = "\n".join([f"{chr(65+i)}) {e}" for i, e in enumerate(endings)])
                prompt = f"{ctx}\n\n{choices_text}"
                commonsense_data.append({
                    "prompt": prompt,
                    "answer": chr(65 + correct_idx),
                    "type": "commonsense",
                    "_group": "hellaswag",
                })
        save_jsonl("commonsense.jsonl", commonsense_data)
        print(f"  [OK] HellaSwag: {len(commonsense_data)} Aufgaben (alle validen)")
    except Exception as e:
        print(f"  [WARN] HellaSwag Download fehlgeschlagen: {e}")
        save_jsonl("commonsense.jsonl", [])

    # ─────────────────── 11. PANDAS EVAL (kuratiert) ───────────────────
    print("\n" + "=" * 60)
    print(f"  11. PandasEval (Pandas-Coding) - 10 kuratierte Aufgaben")
    print("=" * 60)

    pandas_tasks = [
        {
            "prompt": "Create a function that computes a cross-tabulation of two DataFrame columns with margins and normalization.",
            "entry_point": "compute_crosstab",
            "canonical_solution": "def compute_crosstab(df, col1, col2):\n    return pd.crosstab(df[col1], df[col2], margins=True, normalize='index')",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'Dept': ['Engineering', 'Engineering', 'Sales', 'Sales'], 'Grade': ['A', 'B', 'A', 'B']})",
            "tests": ["result = compute_crosstab(df, 'Dept', 'Grade')\nassert isinstance(result, pd.DataFrame)\nassert 'All' in result.index\nassert abs(result.loc['Engineering', 'A'] - 0.5) < 0.01"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that explodes a DataFrame column containing list values and computes the mean of another column per exploded category.",
            "entry_point": "explode_and_agg",
            "canonical_solution": "def explode_and_agg(df, explode_col, value_col):\n    return df.explode(explode_col).groupby(explode_col)[value_col].mean().reset_index()",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'id': [1, 2], 'categories': [['A', 'B'], ['B', 'C']], 'score': [10, 20]})",
            "tests": ["result = explode_and_agg(df, 'categories', 'score')\nassert isinstance(result, pd.DataFrame)\nassert 'categories' in result.columns\nassert 'score' in result.columns"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that uses pipe() to chain multiple DataFrame transformations: filter rows, add a computed column, then sort.",
            "entry_point": "pipe_transform",
            "canonical_solution": "def pipe_transform(df, threshold):\n    return (df\n        .pipe(lambda d: d[d['value'] > threshold])\n        .pipe(lambda d: d.assign(ratio=d['value'] / d['max_value']))\n        .pipe(lambda d: d.sort_values('ratio', ascending=False))\n    )",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'value': [5, 15, 25], 'max_value': [10, 20, 30]})",
            "tests": ["result = pipe_transform(df, 10)\nassert isinstance(result, pd.DataFrame)\nassert 'ratio' in result.columns\nassert all(result['value'] > 10)"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that compares two DataFrames and returns only the rows that have differences in specified columns.",
            "entry_point": "compare_dfs",
            "canonical_solution": "def compare_dfs(df1, df2, on_cols):\n    merged = df1.merge(df2, on=on_cols, how='outer', suffixes=('_old', '_new'), indicator=True)\n    return merged[merged['_merge'] != 'both']",
            "setup_code": "import pandas as pd\ndf1 = pd.DataFrame({'id': [1, 2, 3], 'val': ['a', 'b', 'c']})\ndf2 = pd.DataFrame({'id': [1, 2, 4], 'val': ['a', 'x', 'd']})",
            "tests": ["result = compare_dfs(df1, df2, ['id'])\nassert isinstance(result, pd.DataFrame)\nassert '_merge' in result.columns\nassert len(result) == 2"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that factorizes a categorical column and returns both the encoded values and the unique categories.",
            "entry_point": "factorize_column",
            "canonical_solution": "def factorize_column(df, col):\n    codes, uniques = pd.factorize(df[col])\n    df_result = df.copy()\n    df_result[f'{col}_code'] = codes\n    return df_result, list(uniques)",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'color': ['red', 'blue', 'green', 'blue', 'red']})",
            "tests": ["df_result, cats = factorize_column(df, 'color')\nassert isinstance(df_result, pd.DataFrame)\nassert 'color_code' in df_result.columns\nassert len(cats) == df['color'].nunique()"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that uses qcut() to divide a numeric column into quantile-based bins with custom labels.",
            "entry_point": "quantile_bin",
            "canonical_solution": "def quantile_bin(df, col, q=4, labels=None):\n    if labels is None:\n        labels = [f'Q{i+1}' for i in range(q)]\n    df_result = df.copy()\n    df_result[f'{col}_bin'] = pd.qcut(df[col], q=q, labels=labels)\n    return df_result",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'price': [10, 20, 30, 40, 50, 60]})",
            "tests": ["result = quantile_bin(df, 'price', q=3, labels=['Low', 'Mid', 'High'])\nassert isinstance(result, pd.DataFrame)\nassert 'price_bin' in result.columns\nassert result['price_bin'].nunique() == 3"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that uses assign() with lambda to add multiple derived columns in a single chain.",
            "entry_point": "assign_derived",
            "canonical_solution": "def assign_derived(df):\n    return df.assign(\n        total=df['price'] * df['quantity'],\n        discounted=lambda d: d['total'] * 0.9,\n        category=lambda d: d['total'].apply(lambda x: 'Premium' if x > 100 else 'Standard')\n    )",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'price': [50, 150], 'quantity': [2, 1]})",
            "tests": ["result = assign_derived(df)\nassert isinstance(result, pd.DataFrame)\nassert 'total' in result.columns\nassert 'discounted' in result.columns\nassert 'category' in result.columns"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that bins a numeric column into custom intervals using cut() with descriptive labels.",
            "entry_point": "custom_bin",
            "canonical_solution": "def custom_bin(df, col, bins, labels):\n    df_result = df.copy()\n    df_result[f'{col}_range'] = pd.cut(df[col], bins=bins, labels=labels, include_lowest=True)\n    return df_result",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'age': [5, 20, 30, 45, 60, 80]})",
            "tests": ["bins = [0, 18, 35, 50, 100]\nlabels = ['Youth', 'Young Adult', 'Adult', 'Senior']\nresult = custom_bin(df, 'age', bins, labels)\nassert isinstance(result, pd.DataFrame)\nassert 'age_range' in result.columns\nassert result['age_range'].cat.categories.tolist() == labels"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that uses eval() to compute a new column from an expression referencing existing columns.",
            "entry_point": "eval_expression",
            "canonical_solution": "def eval_expression(df):\n    return df.eval('ratio = (price * quantity) / (max_price + 1e-6)')\n",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'price': [10, 20], 'quantity': [5, 3], 'max_price': [100, 100]})",
            "tests": ["result = eval_expression(df)\nassert isinstance(result, pd.DataFrame)\nassert 'ratio' in result.columns\nassert result['ratio'].between(0, 10).all()"],
            "type": "pandas_eval",
        },
        {
            "prompt": "Create a function that filters rows using between() and then applies a conditional replacement with where().",
            "entry_point": "filter_and_replace",
            "canonical_solution": "def filter_and_replace(df, col, lo, hi, replacement):\n    mask = df[col].between(lo, hi, inclusive='both')\n    df_result = df.copy()\n    df_result[col] = df_result[col].where(mask, replacement)\n    return df_result",
            "setup_code": "import pandas as pd\ndf = pd.DataFrame({'score': [30, 60, 80, 95, 120]})",
            "tests": ["result = filter_and_replace(df, 'score', 50, 100, 0)\nassert isinstance(result, pd.DataFrame)\nassert result['score'].between(0, 100).all()\nassert (result['score'] == 0).sum() > 0"],
            "type": "pandas_eval",
        },
    ]
    save_jsonl("pandas_eval.jsonl", pandas_tasks)

    # ─────────────────── Zusammenfassung ───────────────────
    print("\n" + "=" * 60)
    print("  DOWNLOAD ABGESCHLOSSEN")
    print("=" * 60)
    for f in sorted(os.listdir(DATA_DIR)):
        fpath = os.path.join(DATA_DIR, f)
        if os.path.isfile(fpath) and f.endswith(".jsonl"):
            with open(fpath, "r", encoding="utf-8") as fh:
                count = sum(1 for _ in fh)
            print(f"  {f}: {count} Zeilen")
    print(f"\n  Ordner: {DATA_DIR}")


if __name__ == "__main__":
    main()
