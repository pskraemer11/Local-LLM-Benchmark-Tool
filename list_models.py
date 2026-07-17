import sys, os, subprocess, json
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
from model_manager import get_available_models
from benchmark_config import REASONING_PATTERNS, EXCLUDE_KEYWORDS
models = get_available_models(exclude_keywords=EXCLUDE_KEYWORDS)
print(f"Total models (after EXCLUDE): {len(models)}")
patterns = {p.lower() for p in REASONING_PATTERNS}
print(f"REASONING_PATTERNS: {sorted(patterns)}")
print()
print("=== Models matching REASONING_PATTERNS ===")
for i, m in enumerate(models):
    key = m["key"].lower()
    reasoning = any(p in key for p in patterns)
    if reasoning:
        print(f"[{i}] {m['key']}  |  {m['display']}")
print()
print("=== New models (GGUF files since 2026-07-14) ===")
# Get file dates
result = subprocess.run(
    ["powershell", "-Command", "Get-ChildItem -Path \"$env:USERPROFILE\\.lmstudio\\models\" -Recurse -Filter \"*.gguf\" | Where-Object { $_.LastWriteTime -gt [DateTime]'2026-07-14' } | ForEach-Object { $_.Name + '|' + $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm') }"],
    capture_output=True, text=True, timeout=30
)
recent_files = {}
for line in result.stdout.strip().split('\n'):
    if '|' in line:
        name, dt = line.split('|', 1)
        recent_files[name.strip()] = dt.strip()
# Match files to model keys
for m in models:
    # Extract a filename-like identifier from the model key
    key_lower = m["key"].lower()
    for fname, dt in recent_files.items():
        fbase = fname.lower().replace('.gguf', '')
        # Check if file name is in model key or vice versa
        fparts = fbase.replace('-', ' ').replace('_', ' ').split()
        kparts = key_lower.replace('@', ' ').replace('/', ' ').replace('-', ' ').replace('_', ' ').split()
        common = set(fparts) & set(kparts)
        if len(common) >= 3:  # at least 3 matching words
            print(f"[{i}] {m['key']}  |  {m['display']}  |  downloaded: {dt}")
            break
