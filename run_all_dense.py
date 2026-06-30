"""
Wrapper script: runs all dense (non-MoE, non-Reasoning) models 
with all 10 benchmarks at sample_size=5.
Skips: MoE, Reasoning, Vision/OCR, Embedding models.

ACHTUNG: Die WHITELIST unten ist MANUELL gepflegt und kann veraltet sein!
Bei Aenderungen an installierten Modellen muss diese Liste aktualisiert werden.
Die aktuellen Modelle stehen in benchmark_config.py (DISPLAY_NAMES/WHITELIST).
"""
import subprocess, sys, json, os, time

# Ensure UTF-8 for all subprocesses
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Redirect output to log file immediately
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_run.log")
ERR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_run_err.log")
try:
    log_fh = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
    err_fh = open(ERR_FILE, "w", encoding="utf-8", buffering=1)
    sys.stdout = log_fh
    sys.stderr = err_fh
except Exception as e:
    print(f"[WARN] Log redirect: {e}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Whitelist: alle Dense-Modelle (non-MoE, non-Reasoning, non-VL)
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

result = subprocess.run(
    ["lms", "ls", "--json"],
    capture_output=True, text=True, timeout=30,
    encoding="utf-8", errors="replace"
)
if result.returncode != 0:
    print(f"[ERROR] lms ls: {result.stderr}")
    sys.exit(1)

data = json.loads(result.stdout)
models = []
for item in data if isinstance(data, list) else data.values():
    if isinstance(item, dict):
        key = item.get("modelKey", "")
        if key in WHITELIST_KEYS:
            models.append({
                "key": key,
                "display": item.get("displayName", key),
            })

if not models:
    print("[ERROR] Keine Dense-Modelle gefunden!")
    sys.exit(1)

# Sort by whitelist order
models.sort(key=lambda m: WHITELIST_KEYS.index(m["key"]))

print(f"\n{'='*60}")
print(f"  Dense-Modelle ({len(models)}):")
for i, m in enumerate(models, 1):
    print(f"  [{i:2d}] {m['display']}  ({m['key']})")
print(f"{'='*60}")
print(f"\nStarte jetzt alle {len(models)} Modelle mit allen 10 Benchmarks, SampleSize=5.")
print("Drücke Strg+C zum Abbrechen.\n")
time.sleep(3)

total_start = time.time()
for idx, model in enumerate(models, 1):
    print(f"\n{'#'*60}")
    print(f"  Modell {idx}/{len(models)}: {model['display']} ({model['key']})")
    print(f"{'#'*60}")
    model_start = time.time()

    # Leere GPU-VRAM vor Modellwechsel
    subprocess.run(["lms", "unload", "--all"],
                   capture_output=True, text=True, timeout=30,
                   encoding="utf-8", errors="replace")
    time.sleep(2)

    cmd = [
        sys.executable, os.path.join(BASE_DIR, "run_benchmarks_v11.py"),
        "--sample-size", "5",
        "--model", model["key"],
        "--benchmarks", "all",
    ]
    try:
        result = subprocess.run(cmd, timeout=14400,  # 4h per model max
                               encoding="utf-8", errors="replace")
        rc = result.returncode
    except subprocess.TimeoutExpired:
        print(f"\n  [TIMEOUT] {model['display']} nach 4h abgebrochen")
        rc = -1

    elapsed = time.time() - model_start
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n  [{model['display']}] Fertig in {mins}m {secs}s (Code: {rc})")

total_elapsed = time.time() - total_start
hours, rem = divmod(int(total_elapsed), 3600)
mins, secs = divmod(rem, 60)
print(f"\n{'='*60}")
print(f"  ALLE {len(models)} MODELLE FERTIG in {hours}h {mins}m {secs}s")
print(f"{'='*60}")
