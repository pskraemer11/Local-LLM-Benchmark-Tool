"""Debug: test v2 readiness check directly."""
import subprocess, sys, os
os.chdir(r'C:\Users\pskra\Python-Projekte\Benchmarks')

# First ensure no model is loaded
subprocess.run(["lms", "unload", "--all"], capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")

# Load the model
r = subprocess.run(["lms", "load", "google/gemma-4-12b", "--yes"], capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace")
print("Load:", r.stdout.strip(), r.stderr.strip()[:100])

# Now test the exact readiness check used in v2
import urllib.request, urllib.error, json, time

start = time.time()
timeout = 30
while time.time() - start < timeout:
    time.sleep(2)
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:1234/v1/chat/completions", method="POST",
            data=json.dumps({
                "model": "check",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            print(f"OK: status={resp.status}, model={json.loads(body).get('model', '?')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP Error {e.code}: {body[:200]}")
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")
