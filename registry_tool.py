#!/usr/bin/env python3
"""
Consolidated tool for model_registry.yaml and LM Studio JSON config maintenance.

Commands:
  compare       Compare registry vs LMS vs JSON configs (report only)
  add           Add new LMS models to registry
  configs       Write load.fields (offloadRatio, numParallelSessions) to JSON configs
  sync-ctx      Sync context_length from JSON configs into registry
  fill-ctx      Add default context_length to entries missing it
                (size-based rule or 16384 fallback)
  fill-size     Look up file_size_bytes from LMS for registry entries missing it
  fmt           Normalize blank lines in registry YAML (no blanks within entries,
                one blank between entries)
  migrate-keys  Re-key entries without publisher prefix to publisher/model-name
  sync          Full sync: add → configs → sync-ctx → fill-ctx → fmt
"""

import csv, json, os, re, sys, subprocess, tempfile
from pathlib import Path
from collections import OrderedDict

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "doc-git" / "model_registry.yaml"
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"

# ── ruamel.yaml setup ──────────────────────────────────────────────
from ruamel.yaml import YAML
y = YAML()
y.preserve_quotes = True
y.indent(mapping=2, sequence=4, offset=2)

# ── assemble_blueprint helpers ─────────────────────────────────────
import importlib.machinery
_ASM_PATH = str(BASE_DIR / "assemble_blueprint.py")
_asm = importlib.machinery.SourceFileLoader("asm", _ASM_PATH).load_module()
normalize_model_name = _asm.normalize_model_name
read_lms_configs = _asm.read_lms_configs

_ARCH_MAP = {
    "llama": "Llama Dense", "mistral3": "Mistral Dense",
    "qwen2": "Qwen2 Dense", "qwen3": "Qwen3 Dense", "qwen35": "Qwen3.5 Dense",
    "qwen35moe": "Qwen3.5 MoE", "qwen3moe": "Qwen3 MoE",
    "gemma3": "Gemma-3 Dense", "gemma4": "Gemma-4 Dense",
    "granite": "Granite Dense", "granitehybrid": "Granite Hybrid",
    "deepseek2": "DeepSeek 2", "ernie4_5-moe": "ERNIE MoE",
    "gpt-oss": "GPT-OSS Dense", "cohere2moe": "Cohere 2 MoE",
    "flux": "Flux", "kimi-linear": "Kimi Linear",
    "lfm2moe": "LFM2 MoE", "mellum": "Mellum MoE", "nomic-bert": "Nomic BERT",
}


# ── I/O helpers ────────────────────────────────────────────────────

def load_registry(path: Path = REGISTRY_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return y.load(f) or {}


def save_registry(reg: dict, path: Path = REGISTRY_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        y.dump(reg, f)
    _format_blank_lines(path)


def load_lms_json(path: str | Path) -> list:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _run_lms_ls() -> list:
    r = subprocess.run(["lms", "ls", "--json"], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        print(f"[WARN] lms ls fehlgeschlagen: {r.stderr.strip()}")
        return []
    data = json.loads(r.stdout)
    return data if isinstance(data, list) else list(data.values())


# ── Blank-line formatting ──────────────────────────────────────────

def _format_blank_lines(path: Path) -> None:
    """Normalize blank lines in YAML: none within entries, one between entries."""
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    def is_top_key(s: str) -> bool:
        s = s.rstrip()
        if not s or not s.endswith(":"):
            return False
        if s.startswith(" ") or s.startswith("\t"):
            return False
        return True

    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_top_key(line):
            if out and out[-1] != "" and out[-1].strip() != "":
                out.append("")
            out.append(line)
            i += 1
            while i < len(lines) and not is_top_key(lines[i]):
                if lines[i].strip() == "":
                    i += 1
                    continue
                out.append(lines[i])
                i += 1
        elif line.strip() == "" and out:
            if out[-1] != "":
                out.append("")
            i += 1
        else:
            out.append(line)
            i += 1
    while out and out[-1] == "":
        out.pop()
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ── fmt command ────────────────────────────────────────────────────

def cmd_fmt() -> None:
    _format_blank_lines(REGISTRY_PATH)
    print(f"[OK] Blank lines formatted in {REGISTRY_PATH.name}")


# ── fill-ctx command ───────────────────────────────────────────────

def cmd_fill_ctx(default: int = 16384) -> None:
    reg = load_registry()
    updated = 0
    for entry in reg.values():
        if not isinstance(entry, dict):
            continue
        if "context_length" in entry and entry["context_length"] is not None:
            continue
        size_bytes = entry.get("file_size_bytes")
        if size_bytes and size_bytes > 0:
            entry["context_length"] = _default_ctx_from_size(int(size_bytes))
        else:
            entry["context_length"] = default
        updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries got context_length")


# ── fill-size command ──────────────────────────────────────────────

def cmd_fill_size() -> None:
    """Look up file_size_bytes from LMS for registry entries missing it."""
    reg = load_registry()
    lms_models = _run_lms_ls()
    if not lms_models:
        print("[WARN] LMS nicht verfuegbar. Keine Aenderungen.")
        return
    # Build LMS lookup: normalized name -> sizeBytes
    lms_sizes: dict[str, int] = {}
    for m in lms_models:
        nk = normalize_model_name(m.get("modelKey", ""))
        sb = m.get("sizeBytes", 0)
        if sb and sb > 0:
            if nk not in lms_sizes:
                lms_sizes[nk] = int(sb)
    updated = 0
    for key, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        if "file_size_bytes" in entry and entry["file_size_bytes"]:
            continue
        nk = normalize_model_name(key)
        if nk in lms_sizes:
            entry["file_size_bytes"] = lms_sizes[nk]
            updated += 1
    if updated:
        save_registry(reg)
    print(f"[OK] {updated} entries got file_size_bytes from LMS")


# ── compare command ────────────────────────────────────────────────

def cmd_compare() -> dict:
    reg = load_registry()
    lms = _run_lms_ls()
    cfgs = read_lms_configs(CONFIG_ROOT)

    rk = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}
    lm = {normalize_model_name(m.get("modelKey", "")): m for m in lms}
    ck = {normalize_model_name(c["dir_name"]) for c in cfgs}

    new_models: list[dict] = []
    for lk, lm2 in sorted(lm.items()):
        if not any(lk == r for r in rk):
            new_models.append(lm2)

    missing: list[str] = []
    for rn, re_ in reg.items():
        if not isinstance(re_, dict) or re_.get("blueprint") == "none":
            continue
        rk2 = normalize_model_name(rn)
        if not any(rk2 in l or l in rk2 for l in lm):
            missing.append(rn)

    orphan: set[str] = set()
    for c in cfgs:
        n = normalize_model_name(c["dir_name"])
        if not any(n in r or r in n for r in rk):
            orphan.add(f"{c['publisher']}/{c['dir_name']}")

    report = {
        "lms": len(lms),
        "reg": len(rk),
        "cfg": len(cfgs),
        "new": len(new_models),
        "missing": len(missing),
        "orphan": len(orphan),
        "newd": [{
            "key": m.get("modelKey", "?"),
            "publisher": m.get("publisher", "?"),
            "arch": m.get("architecture", "?"),
            "params": m.get("paramsString", "?"),
            "ctx": m.get("maxContextLength", 0),
            "vision": m.get("vision", False),
            "tools": m.get("trainedForToolUse", False),
            "size_bytes": m.get("sizeBytes", 0),
        } for m in new_models[:20]],
        "missd": missing[:20],
        "orphd": sorted(orphan)[:20],
    }

    print(json.dumps(report, ensure_ascii=False, default=str))
    return report


# ── add command ────────────────────────────────────────────────────

def cmd_add(models: list[dict]) -> dict:
    reg = load_registry()
    added: list[str] = []
    skipped: list[tuple[str, str]] = []

    for m in models:
        mk = str(m.get("key", "")).strip()
        if not mk:
            skipped.append(("?", "leerer Key"))
            continue
        pub = str(m.get("publisher", "unknown")).strip()
        canonical = _canonical_key(mk, pub)
        sk = normalize_model_name(mk)
        if any(sk == normalize_model_name(k) for k in reg):
            skipped.append((mk, "bereits vorhanden"))
            continue
        ar = _ARCH_MAP.get(m.get("arch", ""), m.get("arch", "?"))
        is_mtp = "mtp" in mk.lower()
        nt = f"Architektur: {ar}"
        if is_mtp:
            nt += " | Multi-Token Prediction"
        if m.get("params"):
            nt += f" | {m['params']} Parameter"
        if m.get("vision"):
            nt += " | Vision"
        if m.get("tools"):
            nt += " | Tool-Use"
        num_p = 4 if ("MoE" in ar) or is_mtp else 1
        size_bytes = m.get("size_bytes", 0) or m.get("sizeBytes", 0)
        entry = {
            "publisher": pub,
            "hf_url": f"https://huggingface.co/{canonical}",
            "arch": ar,
            "k_cache": "q8_0",
            "v_cache": "iq4_nl",
            "offload": 1,
            "num_parallel": num_p,
            "notes": nt,
        }
        if size_bytes and size_bytes > 0:
            entry["file_size_bytes"] = int(size_bytes)
            entry["context_length"] = _default_ctx_from_size(int(size_bytes))
        reg[canonical] = entry
        added.append(canonical)

    if added:
        save_registry(reg)

    result = {"added": added, "skipped": skipped}
    print(json.dumps(result, ensure_ascii=False))
    return result


# ── configs command ────────────────────────────────────────────────

def cmd_configs() -> dict:
    reg = load_registry()
    cfgs = read_lms_configs(CONFIG_ROOT)
    rk = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}

    updated = skipped = errors = 0
    for cfg in cfgs:
        cn = normalize_model_name(cfg["dir_name"])
        match = None
        for rn2, rnk in rk.items():
            if cn == rn2 or (cn in rn2) or (rn2 in cn):
                match = rnk
                break
        if not match:
            skipped += 1
            continue
        entry = reg[match]
        jp = cfg["json_path"]
        try:
            with open(jp, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            load_section = data.setdefault("load", {})
            fields = load_section.get("fields")
            if fields is None:
                fields = []
                load_section["fields"] = fields
            fidx = {f.get("key"): i for i, f in enumerate(fields) if isinstance(f, dict)}

            def set_field(key, value):
                if key in fidx:
                    fields[fidx[key]]["value"] = value
                else:
                    fields.append({"key": key, "value": value})
                    fidx[key] = len(fields) - 1

            if "offload" in entry:
                set_field("llm.load.llama.acceleration.offloadRatio", entry["offload"])
            if "num_parallel" in entry:
                set_field("llm.load.numParallelSessions", entry["num_parallel"])

            with open(jp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            updated += 1
        except Exception as e:
            errors += 1

    result = {"updated": updated, "skipped": skipped, "errors": errors}
    print(json.dumps(result, ensure_ascii=False))
    return result


# ── sync-ctx command ───────────────────────────────────────────────

def _normalize_ctx(name: str) -> str:
    s = name.lower()
    s = re.sub(r'\.gguf$', '', s)
    s = re.sub(r'-(gguf|mxpr4)$', '', s)
    s = re.sub(r'^[^/]+/', '', s)
    s = s.replace('.', '-').replace('_', '-')
    while '--' in s:
        s = s.replace('--', '-')
    return s


def _strip_quant(norm_key: str) -> str:
    idx = norm_key.find('@')
    return norm_key[:idx] if idx > 0 else norm_key


_CTX_FROM_SIZE: list[tuple[float, int]] = [
    (14, 16384),
    (13, 32768),
    (12, 49152),
    (11, 65536),
    (10, 98304),
    (9, 131072),
]


def _default_ctx_from_size(size_bytes: int) -> int:
    gb = size_bytes / 1_000_000_000
    for limit, ctx in _CTX_FROM_SIZE:
        if gb > limit:
            return ctx
    return 262144


def _canonical_key(mk: str, pub: str) -> str:
    """Build canonical registry key: publisher/model-name (cleaned)."""
    s = mk.strip().lower()
    s = re.sub(r'\.gguf$', '', s)
    s = re.sub(r'-(gguf|mxpr4)$', '', s)
    if "/" not in s:
        s = f"{pub.lower().strip()}/{s}"
    return s


def cmd_sync_ctx() -> None:
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    print("[1] Registry laden ...")
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] JSON-Configs scannen ...")
    configs = read_lms_configs(CONFIG_ROOT)
    print(f"  -> {len(configs)} Config-Dateien gefunden")

    dir_to_ctx: dict[str, list[int]] = {}
    for c in configs:
        norm_dir = _normalize_ctx(c["dir_name"])
        ctx = c.get("context_length")
        if ctx is not None:
            dir_to_ctx.setdefault(norm_dir, []).append(int(ctx))
    dir_best_ctx = {d: min(ctxs) for d, ctxs in dir_to_ctx.items()}
    print(f"  -> {len(dir_best_ctx)} eindeutige Modelle mit context_length")

    norm_reg: dict[str, str] = {}
    for key in reg:
        if isinstance(reg[key], dict):
            norm_reg[_normalize_ctx(key)] = key

    print("[3] Registry-Einträge ergänzen ...")
    updated = skipped_no_config = skipped_has_value = 0
    for norm_key, orig_key in sorted(norm_reg.items()):
        entry = reg[orig_key]
        if not isinstance(entry, dict):
            continue
        if "context_length" in entry and entry["context_length"] is not None:
            skipped_has_value += 1
            continue
        base_key = _strip_quant(norm_key)
        ctx = dir_best_ctx.get(base_key) or dir_best_ctx.get(norm_key)
        if ctx is not None:
            entry["context_length"] = ctx
            updated += 1
        else:
            skipped_no_config += 1

    print(f"  -> {updated} Einträge aktualisiert")
    print(f"  -> {skipped_has_value} bereits vorhanden")
    print(f"  -> {skipped_no_config} keine Config gefunden")

    if updated:
        print("[4] Registry speichern ...")
        save_registry(reg)
        print("  [OK] Gespeichert")
    else:
        print("  Keine Änderungen")
    print("Fertig.")


# ── migrate-keys command ───────────────────────────────────────────

def cmd_migrate_keys() -> None:
    """Migrate registry keys without publisher prefix to canonical format (publisher/model-name)."""
    reg = load_registry()
    migrated = 0
    skipped_no_pub = 0
    merged = 0

    for key in list(reg.keys()):
        entry = reg[key]
        if not isinstance(entry, dict):
            continue
        if "/" in key:
            continue
        pub = str(entry.get("publisher", "")).strip()
        if not pub or pub == "?" or pub == "unknown":
            print(f"  [SKIP] Kein Publisher fuer '{key}'")
            skipped_no_pub += 1
            continue
        new_key = f"{pub}/{key}".lower()
        if new_key in reg:
            # Merge: copy missing fields from old entry to canonical one
            target = reg[new_key]
            for k, v in entry.items():
                if k not in target or target[k] is None:
                    target[k] = v
            del reg[key]
            merged += 1
            continue
        reg[new_key] = reg.pop(key)
        # Fix hf_url if it had double publisher (publisher/publisher/model-name)
        expected_url = f"https://huggingface.co/{new_key}"
        hf = reg[new_key].get("hf_url", "").lower()
        if hf.startswith("https://huggingface.co/"):
            path = hf.replace("https://huggingface.co/", "")
            parts = path.split("/")
            if len(parts) >= 2 and parts[0] == parts[1]:
                reg[new_key]["hf_url"] = expected_url
        migrated += 1

    if migrated or merged:
        save_registry(reg)
    print(f"[OK] Migriert: {migrated}, gemerged: {merged}, kein Publisher: {skipped_no_pub}")


# ── sync command (full) ────────────────────────────────────────────

def cmd_sync() -> None:
    """Full sync: add → configs → sync-ctx → fill-ctx → fmt"""
    lms = _run_lms_ls()
    reg = load_registry()
    rk = {normalize_model_name(k): k for k, v in reg.items() if isinstance(v, dict)}

    # Find new models
    new_models = []
    for m in lms:
        mk = str(m.get("modelKey", "")).strip()
        if not mk:
            continue
        sk = normalize_model_name(mk)
        if not any(sk == r for r in rk):
            new_models.append(m)

    if new_models:
        print(f"[add] {len(new_models)} neue Modelle zur Registry ...")
        cmd_add(new_models)
    else:
        print("[add] Keine neuen Modelle")

    print("[configs] load.fields in JSON-Configs schreiben ...")
    cmd_configs()

    print("[sync-ctx] context_length aus JSON-Configs in Registry ...")
    cmd_sync_ctx()

    print("[fill-ctx] Default context_length für fehlende Einträge ...")
    cmd_fill_ctx()

    print("[fmt] Blank lines normalisieren ...")
    cmd_fmt()

    print("[OK] Sync abgeschlossen")


# ── CLI dispatch ──────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "compare":
        cmd_compare()
    elif cmd == "add":
        # Read new models JSON from stdin or file arg
        if len(sys.argv) > 2:
            with open(sys.argv[2], "r", encoding="utf-8-sig") as f:
                models = json.load(f)
        else:
            models = json.load(sys.stdin)
        if not isinstance(models, list):
            models = [models]
        cmd_add(models)
    elif cmd == "configs":
        cmd_configs()
    elif cmd == "sync-ctx":
        cmd_sync_ctx()
    elif cmd == "fill-ctx":
        cmd_fill_ctx()
    elif cmd == "fill-size":
        cmd_fill_size()
    elif cmd == "fmt":
        cmd_fmt()
    elif cmd == "migrate-keys":
        cmd_migrate_keys()
    elif cmd == "sync":
        cmd_sync()
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
