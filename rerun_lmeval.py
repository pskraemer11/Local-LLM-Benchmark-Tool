"""
Re-run lm_eval for all 15 dense models using the fixed --output_path.
Skips custom (DS1000/PandasEval) and evalplus benchmarks.
"""
import subprocess, sys, os, time, json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "ergebnisse")

WHITELIST_KEYS = [
    "google/gemma-4-12b",
    "ibm/granite-4.1-8b",
    "mathstral-7b-v0.1",
    "microsoft/phi-4",
    "essentialai/rnj-1",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mistral-nemo-instruct-2407",
    "mistralai/codestral-22b-v0.1",
    "qwen/qwen2.5-coder-14b",
    "qwen/qwen3.5-9b",
    "qwopus3.5-9b-coder-mtp",
    "starcoder2-15b-instruct-v0.1",
    "pandalyst_13b_v1.0",
    "wizardcoder-python-13b-v1.0-i1",
    "januscoder-14b-i1",
]

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

LOG_FILE = os.path.join(BASE_DIR, "rerun_lmeval.log")
ERR_FILE = os.path.join(BASE_DIR, "rerun_lmeval_err.log")
log_fh = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
err_fh = open(ERR_FILE, "w", encoding="utf-8", buffering=1)
sys.stdout = log_fh
sys.stderr = err_fh

print("=" * 60)
print(f"  LM-Eval Re-Run: {len(WHITELIST_KEYS)} Modelle")
print(f"  Tasks: ARC-Challenge, HellaSwag, TruthfulQA, MathQA (SampleSize=5)")
print("=" * 60)

total_start = time.time()
for idx, model_key in enumerate(WHITELIST_KEYS, 1):
    print(f"\n{'#' * 60}")
    print(f"  Modell {idx}/{len(WHITELIST_KEYS)}: {model_key}")
    print(f"{'#' * 60}")

    # Unload previous model
    subprocess.run(["lms", "unload", "--all"],
                   capture_output=True, text=True, timeout=30,
                   encoding="utf-8", errors="replace")
    time.sleep(2)

    cmd = [
        sys.executable, os.path.join(BASE_DIR, "run_benchmarks_v11.py"),
        "--sample-size", "5",
        "--model", model_key,
        "--benchmarks", "arc-challenge,hellaswag,truthfulqa,mathqa",
    ]
    model_start = time.time()
    try:
        result = subprocess.run(cmd, timeout=3600,
                               encoding="utf-8", errors="replace")
        rc = result.returncode
    except subprocess.TimeoutExpired:
        print(f"\n  [TIMEOUT] {model_key} nach 1h abgebrochen")
        rc = -1
    elapsed = time.time() - model_start
    mins, secs = divmod(int(elapsed), 60)
    print(f"  [{model_key}] Fertig in {mins}m {secs}s (Code: {rc})")

    # Check if results were saved
    safe = model_key.replace("/", "_")
    lmeval_dir = os.path.join(RESULTS_DIR, f"lmeval_{safe}")
    if os.path.isdir(lmeval_dir):
        files = []
        for root, dirs, fnames in os.walk(lmeval_dir):
            for fn in fnames:
                if fn.endswith(".json"):
                    files.append(os.path.join(root, fn))
        print(f"  [INFO] {len(files)} Ergebnisdateien in {lmeval_dir}")

total_elapsed = time.time() - total_start
hours, rem = divmod(int(total_elapsed), 3600)
mins, secs = divmod(rem, 60)
print(f"\n{'=' * 60}")
print(f"  ALLE {len(WHITELIST_KEYS)} MODELLE FERTIG in {hours}h {mins}m {secs}s")
print(f"{'=' * 60}")
