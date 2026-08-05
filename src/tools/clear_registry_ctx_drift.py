#!/usr/bin/env python3
"""Clear registry context_length for entries where config differs (config_context_drift).

This allows sync-ctx to fill in the correct values from configs.
"""
import sys
import yaml
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_DIR))

from assemble_blueprint import read_lms_configs, normalize_model_name, normalize_for_config

REGISTRY_PATH = Path(__file__).parent.parent.parent / "doc-git" / "model_registry.yaml"

def clear_drift_context_lengths():
    # Load registry
    reg = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not reg:
        print("[ERROR] Empty registry")
        return

    # Load configs to compare
    from assemble_blueprint import read_lms_configs, normalize_model_name, normalize_for_config
    CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
    configs = read_lms_configs(CONFIG_ROOT)
    
    # Build config lookup (normalized -> contextLength)
    config_ctx = {}
    for c in configs:
        raw = f"{c['publisher']}/{c['dir_name']}"
        norm = normalize_model_name(raw)
        broad = normalize_for_config(raw)
        ctx = c.get("context_length")
        if ctx is not None:
            config_ctx[norm] = int(ctx)
            config_ctx[broad] = int(ctx)
    
    print(f"Loaded {len(config_ctx)} config contextLength entries")

    # Build registry key map (normalized -> original key)
    norm_reg = {}
    for key, entry in reg.items():
        if isinstance(entry, dict):
            norm_reg[normalize_model_name(key)] = key

    print(f"Registry has {len(norm_reg)} model entries")

    # Find mismatches and clear registry context_length
    cleared = 0
    skipped = 0
    for norm_key, orig_key in norm_reg.items():
        entry = reg[orig_key]
        if not isinstance(entry, dict):
            continue
        reg_ctx = entry.get("context_length")
        if reg_ctx is None:
            continue
        
        # Check config for this key (try multiple normalizations)
        config_val = config_ctx.get(norm_key)
        if config_val is None:
            # Try stripped quant
            base = norm_key.split('@')[0] if '@' in norm_key else norm_key
            config_val = config_ctx.get(base)
        if config_val is None:
            # Try broad normalization
            broad = normalize_for_config(orig_key)
            config_val = config_ctx.get(broad)
        
        if config_val is not None and config_val != reg_ctx:
            print(f"[CLEAR] {orig_key}: registry={reg_ctx}, config={config_val}")
            entry["context_length"] = None
            cleared += 1
        else:
            skipped += 1

    if cleared > 0:
        REGISTRY_PATH.write_text(yaml.dump(reg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"\nCleared {cleared} registry context_length entries (set to null)")
    else:
        print("\nNo mismatches found to clear")

if __name__ == "__main__":
    clear_drift_context_lengths()