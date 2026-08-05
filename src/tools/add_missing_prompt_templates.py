#!/usr/bin/env python3
"""Add missing promptTemplate field to configs where template file exists but field is missing."""
import json
from pathlib import Path

CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "doc-git" / "Jinja-Chat-Templates"

# Target configs with missing promptTemplate but template file exists
TARGET_CONFIGS = [
    {
        "rel_path": "mradermacher/gemma-4-19b-a4b-it-REAP-i1-GGUF/gemma-4-19b-a4b-it-REAP.i1-Q4_K_M.gguf.json",
        "template_file": "gemma4-19b-template_minijinja.jinja",
    },
    {
        "rel_path": "bartowski/google_gemma-4-26B-A4B-it-GGUF/google_gemma-4-26B-A4B-it-Q3_K_S.gguf.json",
        "template_file": "gemma4-26b-template_minijinja.jinja",
    },
]

def add_prompt_templates():
    fixed = 0
    for target in TARGET_CONFIGS:
        config_path = CONFIG_ROOT / target["rel_path"]
        template_path = TEMPLATE_DIR / target["template_file"]
        
        if not config_path.exists():
            print(f"[WARN] Config not found: {config_path}")
            continue
        if not template_path.exists():
            print(f"[WARN] Template not found: {template_path}")
            continue
        
        try:
            data = json.loads(config_path.read_text(encoding="utf-8-sig"))
            template_content = template_path.read_text(encoding="utf-8")
            
            fields = data.setdefault("operation", {}).setdefault("fields", [])
            
            # Check if promptTemplate already exists
            found = False
            for field in fields:
                if field.get("key") == "llm.prediction.promptTemplate":
                    found = True
                    if not field.get("value"):
                        field["value"] = template_content
                        print(f"[FIX] {target['rel_path']}: added missing promptTemplate")
                        fixed += 1
                    else:
                        print(f"[SKIP] {target['rel_path']}: promptTemplate already present")
                    break
            
            if not found:
                fields.append({"key": "llm.prediction.promptTemplate", "value": template_content})
                print(f"[FIX] {target['rel_path']}: added promptTemplate field")
                fixed += 1
            
            # Write back
            config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            
        except Exception as e:
            print(f"[ERROR] {target['rel_path']}: {e}")
    
    print(f"\nDone. Fixed {fixed} configs.")

if __name__ == "__main__":
    add_prompt_templates()