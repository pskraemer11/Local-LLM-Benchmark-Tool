import subprocess, json
r = subprocess.run(['lms','ls','--json'], capture_output=True, text=True, timeout=15)
data = json.loads(r.stdout)
for item in data if isinstance(data, list) else data.values():
    if isinstance(item, dict):
        mk = item.get('modelKey','')
        if mk and item.get('type') == 'llm' and 'qwen3.6' in mk.lower():
            q = item.get('quantization',{}) or {}
            print("Key:", mk)
            print("  Display:", item.get('displayName'))
            print("  Params:", item.get('paramsString'))
            print("  Quant:", q.get('name','?') if isinstance(q,dict) else str(q))
            path = item.get('path','')
            print("  Path:", path[:80] if len(path) > 80 else path)
            print("  Size GB:", round((item.get('sizeBytes',0) or 0) / 1e9, 2))
            print()
