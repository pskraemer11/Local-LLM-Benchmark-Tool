#!/usr/bin/env python3
"""Delegates to registry_tool.py sync-ctx."""
import subprocess, sys
from pathlib import Path
sys.exit(subprocess.call([sys.executable,
    str(Path(__file__).resolve().parent / "registry_tool.py"), "sync-ctx"]))
