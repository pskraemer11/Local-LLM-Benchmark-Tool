#!/usr/bin/env python3
"""Clear registry context_length for 3 specific drift entries, then sync-ctx."""
import yaml
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent.parent / "doc-git" / "model_registry.yaml"

DRIFT_KEYS = [
    "jetbrains/mellum2-12b-a2.5b-instruct",
    "mradermacher/nemotron-cascade-14b-thinking",
    "quietimpostor/nemotron-3-nano-reap-21b-a3b",
]

def clear_three_drift():
    reg = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    cleared = 0
    for key in DRIFT_KEYS:
        entry = reg.get(key)
        if entry and isinstance(entry, dict) and entry.get("context_length") is not None:
            print(f"[CLEAR] {key}: context_length={entry['context_length']} -> null")
            entry["context_length"] = None
            cleared += 1
        else:
            print(f"[SKIP] {key}: not found or already null")
    
    if cleared:
        REGISTRY_PATH.write_text(yaml.dump(reg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"\nCleared {cleared} entries")
    else:
        print("Nothing to clear")

if __name__ == "__main__":
    clear_three_drift()