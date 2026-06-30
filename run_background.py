"""Start the dense model benchmark run and log output."""
import subprocess, sys, os, time

script = os.path.join(os.path.dirname(__file__), "run_all_dense.py")
log = os.path.join(os.path.dirname(__file__), "full_run.log")
err = os.path.join(os.path.dirname(__file__), "full_run_err.log")

with open(log, "w", buffering=1) as flog, open(err, "w", buffering=1) as ferr:
    p = subprocess.Popen(
        [sys.executable, script],
        stdout=flog, stderr=ferr,
    )
    print(f"Started PID {p.pid}")
    print(f"Log: {log}")

# Wait a moment then check
time.sleep(20)
with open(log) as f:
    lines = f.readlines()
    print(f"Log has {len(lines)} lines")
    for line in lines[-10:]:
        print(line.rstrip())
