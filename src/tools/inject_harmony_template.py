"""Inject the Harmony Jinja template into all GPT-OSS LM Studio config JSONs."""

import json
import shutil
from pathlib import Path

TEMPLATE_FILE = Path(__file__).resolve().parents[2] / "doc-git" / "Jinja-Chat-Templates" / "gpt-oss-20b-template_unsloth.jinja"
CONFIG_DIR = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"

CONFIGS = [
    "unsloth/gpt-oss-20b-GGUF/gpt-oss-20b-Q6_K.gguf.json",
    "unsloth/gpt-oss-20b-GGUF/gpt-oss-20b-Q8_0.gguf.json",
    "lmstudio-community/gpt-oss-20b-GGUF/gpt-oss-20b-MXFP4.gguf.json",
    "openai/gpt-oss-20b.json",
]

TEMPLATE_KEY = "llm.prediction.promptTemplate"


def main():
    template_raw = TEMPLATE_FILE.read_text(encoding="utf-8")
    template_escaped = template_raw

    for rel_path in CONFIGS:
        path = CONFIG_DIR / rel_path
        if not path.exists():
            print(f"SKIP (not found): {rel_path}")
            continue

        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        print(f"BACKUP: {backup}")

        data = json.loads(path.read_text(encoding="utf-8"))
        fields = data.setdefault("operation", {}).setdefault("fields", [])

        found = False
        for field in fields:
            if field.get("key") == TEMPLATE_KEY:
                print(f"  UPDATE: {TEMPLATE_KEY} (was {len(field['value'])} chars)")
                field["value"] = template_escaped
                found = True
                break

        if not found:
            fields.append({"key": TEMPLATE_KEY, "value": template_escaped})
            print(f"  ADD: {TEMPLATE_KEY} ({len(template_escaped)} chars)")

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  DONE: {rel_path}\n")


if __name__ == "__main__":
    main()
