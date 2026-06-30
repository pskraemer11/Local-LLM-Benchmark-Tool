"""
Quick-Test: LFM2.5-8b (80 tok/s) mit 10 Tasks, SampleSize=10.
Nach Code-Änderungen ausführen, um Basis-Funktionalität zu prüfen.
"""
import subprocess, sys, os, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = "lfm2.5-8b-a1b"
BENCHMARKS = "arc-challenge,hellaswag,truthfulqa,mathqa,ds1000,pandaseval,humaneval+,mbpp+"
SAMPLE_SIZE = 10

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

print("=" * 60)
print(f"  Quick-Test: {MODEL}")
print(f"  Benchmarks: {BENCHMARKS}")
print(f"  SampleSize: {SAMPLE_SIZE}")
print("=" * 60)

# Unload all first
subprocess.run(["lms", "unload", "--all"],
               capture_output=True, text=True, timeout=30,
               encoding="utf-8", errors="replace")
time.sleep(2)

t0 = time.time()
cmd = [
    sys.executable, os.path.join(BASE_DIR, "run_benchmarks_v3.py"),
    "--model", MODEL,
    "--benchmarks", BENCHMARKS,
    "--sample-size", str(SAMPLE_SIZE),
]
result = subprocess.run(cmd, timeout=7200, encoding="utf-8", errors="replace")

elapsed = time.time() - t0
mins, secs = divmod(int(elapsed), 60)
print(f"\n  Quick-Test fertig in {mins}m {secs}s (Code: {result.returncode})")
