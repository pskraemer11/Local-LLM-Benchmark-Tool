#!/usr/bin/env python3
"""Delegates to registry_tool.py (fill-ctx / fmt)."""
import subprocess, sys
from pathlib import Path
RT = Path(__file__).resolve().parent / "registry_tool.py"
args = [a for a in sys.argv[1:] if not a.startswith("--path") and not a.startswith("--default-ctx")]
# Map old CLI flags → new subcommands
if "--fill-only" in args:
    r = subprocess.call([sys.executable, str(RT), "fill-ctx"])
elif "--format-only" in args:
    r = subprocess.call([sys.executable, str(RT), "fmt"])
else:
    # Default: both
    r1 = subprocess.call([sys.executable, str(RT), "fill-ctx"])
    if r1:
        sys.exit(r1)
    r = subprocess.call([sys.executable, str(RT), "fmt"])
sys.exit(r)
