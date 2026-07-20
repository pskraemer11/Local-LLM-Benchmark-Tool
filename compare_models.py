import os, re, sys
sys.path.insert(0, os.getcwd())
from model_manager import get_available_models
from benchmark_config import EXCLUDE_KEYWORDS

# Normalize a model key for comparison (replace _ / with common char)
def normalize_key(k):
    return k.lower().replace("_", "/").replace("\\", "/").replace("@", "/")

# Get current LM Studio models
current = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS)
current_norm = {normalize_key(m["key"]): m for m in current}
print(f"=== Current lms ls models ({len(current)}) ===")

# Get model keys from existing result CSVs
ergebnisse = "ergebnisse"
benchmarked_norm = set()
pattern = re.compile(r'model_\d+_(.+)\.csv$')
pattern2 = re.compile(r'modell_\d+_(.+)\.csv$')
for f in os.listdir(ergebnisse):
    for pat in (pattern, pattern2):
        m = pat.match(f)
        if m:
            key = normalize_key(m.group(1))
            benchmarked_norm.add(key)
            break

print(f"=== Models with result CSVs (unique, normalized) ({len(benchmarked_norm)}) ===")

# Find NEW models (in lms ls but NOT yet benchmarked)
new_models = []
already_done = []
for m in current:
    normalized_key = normalize_key(m["key"])
    # Check if ANY benchmarked key matches (substring check)
    done = any(normalized_key in bk or bk in normalized_key for bk in benchmarked_norm)
    if done:
        already_done.append(m)
    else:
        new_models.append(m)

print(f"Already benchmarked: {len(already_done)}")
print(f"NEW (need benchmarking): {len(new_models)}")
print()
print("=== NEW models ===")
for i, m in enumerate(new_models, 1):
    print(f"  [{i:2d}] {m['key']}")

print()
print("=== Already done ===")
for i, m in enumerate(already_done, 1):
    print(f"  [{i:2d}] {m['key']}")
