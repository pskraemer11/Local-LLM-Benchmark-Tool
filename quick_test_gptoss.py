#!/usr/bin/env python3
"""
Quick-Test: GPT-OSS 20B (Unsloth Q6_0) mit korrekten Settings
- temperature=1.0, top_p=1.0
- max_tokens=4096 (wg. Reasoning-Tokens)
- System-Prompt mit Reasoning: low
"""

import json, os, subprocess, sys, time, csv
from urllib.request import Request, urlopen

API_BASE = "http://127.0.0.1:1234/v1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")
os.makedirs(RESULTS_DIR, exist_ok=True)

def query(prompt, system="You are ChatGPT, a large language model trained by OpenAI.\nReasoning: low", max_tokens=4096):
    body = json.dumps({
        "model": "gpt-oss-20b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 1.0,
        "top_p": 1.0,
        "top_k": 0,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = Request(f"{API_BASE}/chat/completions", data=body,
                  headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - t0
    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    tokens_out = usage.get("completion_tokens", 0)
    reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    tok_s = tokens_out / elapsed if elapsed > 0 else 0
    return {
        "content": content,
        "elapsed": elapsed,
        "tokens_out": tokens_out,
        "reasoning_tokens": reasoning_tokens,
        "tok_s": tok_s,
        "usage": usage,
    }

print("=" * 60)
print("  GPT-OSS 20B (Unsloth Q6_0) Quick-Test")
print("=" * 60)

# 1. Simple code generation
print("\n--- 1. Simple Python (is_prime) ---")
r = query("Write a Python function to check if a number is prime. Return only the code, no explanation.")
print(f"  Time: {r['elapsed']:.1f}s | Tokens: {r['tokens_out']} (reasoning: {r['reasoning_tokens']}) | {r['tok_s']:.1f} tok/s")
print(f"  Response:\n{r['content'][:300]}")

# 2. Math
print("\n--- 2. Math (3 + 5 * 2) ---")
r = query("What is 3 + 5 * 2? Just give the number.")
print(f"  Time: {r['elapsed']:.1f}s | Tokens: {r['tokens_out']} (reasoning: {r['reasoning_tokens']}) | {r['tok_s']:.1f} tok/s")
print(f"  Response: {r['content'][:100]}")

# 3. HumanEval/0 (return_solution) via evalplus
print("\n--- 3. HumanEval+ (2 tasks, temp=1.0) ---")
model_tag = "openai_gpt-oss-20b-q6"
root_dir = os.path.join(RESULTS_DIR, f"evalplus_{model_tag}")
os.makedirs(root_dir, exist_ok=True)

t0 = time.time()
r1 = subprocess.run(
    [sys.executable, "-m", "evalplus.codegen",
     "--model", "local-model",
     "--dataset", "humaneval",
     "--backend", "openai",
     "--base-url", "http://127.0.0.1:1234/v1",
     "--temperature", "1.0",
     "--n_samples", "1",
     "--id-range", "[0,1]",
     "--root", root_dir],
    capture_output=True, text=True, timeout=300,
    encoding="utf-8", errors="replace"
)
print(f"  codegen stdout:\n{r1.stdout[-500:]}")
if r1.returncode != 0:
    print(f"  codegen stderr:\n{r1.stderr[-300:]}")

samples_path = os.path.join(root_dir, "humaneval",
    "local-model_openai_temp_1.0.jsonl")
skip_eval = False
if not os.path.exists(samples_path):
    print(f"  [WARN] samples nicht gefunden: {samples_path}")
    skip_eval = True
else:
    r2 = subprocess.run(
        [sys.executable, "-m", "evalplus.evaluate",
         "--dataset", "humaneval",
         "--samples", samples_path,
         "--i_just_wanna_run"],
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace"
    )
    eval_out = r2.stdout[-500:] if r2.stdout else ""
    print(f"  evaluate:\n{eval_out}")
    if r2.returncode != 0:
        print(f"  evaluate stderr:\n{r2.stderr[-300:]}")
elapsed = time.time() - t0
print(f"  HumanEval+ done ({elapsed:.0f}s)")

# 4. DS1000 simple task
print("\n--- 4. DS1000 1 task ---")
ds_csv = os.path.join(RESULTS_DIR, f"20260618_quick_DS1000_GPT-OSS_20B_Q6.csv")
# Run a single DS1000 task via the benchmark script
# We'll do a manual query
r = query(
    "Task: Write the code to complete the following:\n"
    "import pandas as pd\n\n"
    "# Create a DataFrame from a dictionary\n"
    "df = pd.DataFrame({"
)
print(f"  Time: {r['elapsed']:.1f}s | Tokens: {r['tokens_out']} (reasoning: {r['reasoning_tokens']}) | {r['tok_s']:.1f} tok/s")
print(f"  continuation:\n{r['content'][:300]}")

# 5. Speed test (simple Q&A batch)
print("\n--- 5. Speed (5 simple Q&A) ---")
times = []
for i, q in enumerate([
    "What is 2+2?",
    "What is the capital of France?",
    "Write hello world in Python.",
    "What is 15*3?",
    "What color is the sky?"
]):
    r = query(q, max_tokens=128)
    times.append(r)
    print(f"  [{i}] {r['elapsed']:.1f}s | {r['tok_s']:.1f} tok/s | reasoning: {r['reasoning_tokens']}")

avg_tok_s = sum(t["tok_s"] for t in times) / len(times)
print(f"\n  Average speed: {avg_tok_s:.1f} tok/s")
print(f"  (mxfp4 version: 40.2 tok/s)")

print("\nDone.")
