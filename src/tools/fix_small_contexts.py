#!/usr/bin/env python3
"""Fix configs with contextLength < 32768 (MIN_CONTEXT_LENGTH).

Sets contextLength to 32768 for all configs below the threshold.
"""
import json
from pathlib import Path

CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
MIN_CTX = 32768

# Target configs identified by validation
TARGET_CONFIGS = [
    "Intel/MiroThinker-v1.5-30B-gguf-q2ks-mixed-AutoRound/MiroThinker-v1.5-30B-Q2_K_S.gguf.json",
    "lmstudio-community/DeepSeek-Coder-V2-Lite-Instruct-GGUF/DeepSeek-Coder-V2-Lite-Instruct-Q5_K_M.gguf.json",
    "lmstudio-community/gpt-oss-20b-GGUF/gpt-oss-20b-MXFP4.gguf.json",
    "mradermacher/deepseek-coder-33b-instruct-GGUF/deepseek-coder-33b-instruct.Q3_K_S.gguf.json",
    "unsloth/GLM-4.7-Flash-GGUF/GLM-4.7-Flash-Q3_K_S.gguf.json",
    "unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF/GLM-4.7-Flash-REAP-23B-A3B-Q4_K_S.gguf.json",
    "unsloth/phi-4-GGUF/phi-4-Q5_K_M.gguf.json",
    "vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF/Ternary-Bonsai-27B-MTP-Q2_K.gguf.json",
]

def fix_configs():
    fixed = 0
    for rel_path in TARGET_CONFIGS:
        path = CONFIG_ROOT / rel_path
        if not path.exists():
            print(f"[WARN] Not found: {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            updated = False
            # Check both load.fields and operation.fields
            for section in ("load", "operation"):
                fields = data.get(section, {}).get("fields", [])
                for field in fields:
                    if field.get("key") == "llm.load.contextLength":
                        old = field.get("value")
                        if old is not None and int(old) < MIN_CTX:
                            field["value"] = MIN_CTX
                            print(f"[FIX] {rel_path} ({section}): {old} -> {MIN_CTX}")
                            fixed += 1
                            updated = True
                        else:
                            print(f"[SKIP] {rel_path} ({section}): contextLength={old}")
            if updated:
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[ERROR] {rel_path}: {e}")
    print(f"\nDone. Fixed {fixed} configs.")

if __name__ == "__main__":
    fix_configs()