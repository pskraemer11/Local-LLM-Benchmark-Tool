"""Inject chat-template promptTemplate into all LM Studio config JSONs.

Reads model_registry.yaml, finds models with 'template:' set,
locates all matching config JSONs (incl. multi-quant directories),
and injects the Jinja template content into llm.prediction.promptTemplate.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from assemble_blueprint import read_lms_configs, find_all_configs_for_registry_key
from registry_tool import load_registry

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BASE_DIR / "doc-git" / "Jinja-Chat-Templates"
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
TEMPLATE_KEY = "llm.prediction.promptTemplate"


def main():
    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)

    # Collect models with template: set
    to_inject = []
    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        tpl_name = entry.get("template")
        if not tpl_name:
            continue
        tpl_path = TEMPLATE_DIR / tpl_name
        if not tpl_path.exists():
            print(f"SKIP {model_key}: template file not found ({tpl_path})")
            continue
        matches = find_all_configs_for_registry_key(model_key, cfgs)
        if not matches:
            print(f"SKIP {model_key}: no config JSON found")
            continue
        to_inject.append((model_key, tpl_path, matches))

    print(f"\nFound {len(to_inject)} models with template: set and config JSONs\n")

    total_injected = 0
    for model_key, tpl_path, matches in sorted(to_inject, key=lambda x: x[0]):
        template_raw = tpl_path.read_text(encoding="utf-8")
        print(f"\n{model_key}")
        print(f"  template: {tpl_path.name} ({len(template_raw)} chars)")
        for cfg in matches:
            json_path = Path(cfg["json_path"])
            if not json_path.exists():
                print(f"  SKIP (not found): {json_path.name}")
                continue
            backup = json_path.with_suffix(json_path.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(json_path, backup)
                print(f"  BACKUP: {backup.name}")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            fields = data.setdefault("operation", {}).setdefault("fields", [])
            found = False
            for field in fields:
                if field.get("key") == TEMPLATE_KEY:
                    old_len = len(field.get("value", ""))
                    field["value"] = template_raw
                    print(f"  UPDATE {json_path.name}: promptTemplate {old_len} -> {len(template_raw)} chars")
                    found = True
                    break
            if not found:
                fields.append({"key": TEMPLATE_KEY, "value": template_raw})
                print(f"  ADD {json_path.name}: promptTemplate ({len(template_raw)} chars)")
            json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            total_injected += 1

    print(f"\n{'='*60}")
    print(f"  Done. {total_injected} config JSONs updated across {len(to_inject)} models.")


if __name__ == "__main__":
    main()
