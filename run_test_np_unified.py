#!/usr/bin/env python3
"""
Test harness: Parameter dependency (np, unified KV cache, context_length).
4 models × 2 benchmarks × 2 conditions = 16 runs.
"""
import json, os, subprocess, sys, shutil, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Test models (modelKey from LMS, registry key, display name, current np)
TEST_MODELS = [
    {"key": "granite-4.0-h-tiny",         "display": "Granite 4.0 H Tiny",       "np_default": 4, "arch": "MoE"},
    {"key": "mellum2-12b-a2.5b-instruct", "display": "Mellum2 12B A2.5B Instruct","np_default": 4, "arch": "MoE"},
    {"key": "nerdsking-python-coder-7b-i",  "display": "Nerdsking Python Coder 7B","np_default": 1, "arch": "Dense"},
    {"key": "granite-4.1-8b",              "display": "Granite 4.1 8B",           "np_default": 1, "arch": "Dense"},
]

BENCHMARKS = ["ds1000", "arc-challenge"]
SAMPLE_SIZE = 20

# ── Config path helpers ────────────────────────────────────

def _load_lms_configs(root: Path):
    """Mirrors assemble_blueprint.read_lms_configs but returns config dicts."""
    cfgs = []
    if not root.is_dir():
        return cfgs
    for pub_dir in sorted(root.iterdir()):
        if not pub_dir.is_dir():
            continue
        for model_dir in sorted(pub_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            for f in sorted(model_dir.iterdir()):
                if f.suffix.lower() != ".json":
                    continue
                with open(f, "r", encoding="utf-8-sig") as fh:
                    data = json.load(fh)
                cfgs.append({
                    "dir_name": model_dir.name,
                    "publisher": pub_dir.name,
                    "json_path": str(f),
                    "data": data,
                })
    return cfgs


def find_configs(model_key: str) -> list[dict]:
    """Find JSON config(s) matching a model key (fuzzy)."""
    root = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"
    cfgs = _load_lms_configs(root)
    mk_lower = model_key.lower()
    matches = []
    for c in cfgs:
        dn = c["dir_name"].lower()
        if mk_lower in dn:
            matches.append(c)
    return matches


def patch_config(cfg: dict, field_key: str, value):
    """Patch a JSON config's load.fields entry, returns old value."""
    data = cfg["data"]
    load_section = data.setdefault("load", {})
    fields = load_section.get("fields")
    if fields is None:
        fields = []
        load_section["fields"] = fields
    old = None
    for f in fields:
        if isinstance(f, dict) and f.get("key") == field_key:
            old = f.get("value")
            f["value"] = value
            break
    else:
        fields.append({"key": field_key, "value": value})
    # Write back
    with open(cfg["json_path"], "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return old


def load_model(model_key: str) -> bool:
    """Load model so config changes take effect."""
    r = subprocess.run(
        ["lms", "load", model_key, "--yes"],
        capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace"
    )
    return r.returncode == 0


def unload_model():
    subprocess.run(["lms", "unload", "--all"], capture_output=True, timeout=30)


def run_benchmark(model_key: str, benchmark: str, sample_size: int, label: str) -> dict:
    """Run a single benchmark, return result dict."""
    log_dir = BASE_DIR / "ergebnisse" / "test_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{label}.log"

    cmd = [
        sys.executable,
        str(BASE_DIR / "run_benchmarks_v13.py"),
        "-m", model_key,
        "-b", benchmark,
        "-s", str(sample_size),
    ]

    print(f"\n{'='*60}")
    print(f"  RUN: {label}")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{'='*60}")

    start = time.time()
    with open(log_file, "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600,
                           encoding="utf-8", errors="replace")
        lf.write(r.stdout)
        if r.stderr:
            lf.write("\n--- STDERR ---\n")
            lf.write(r.stderr)
    elapsed = time.time() - start

    print(f"  Exit code: {r.returncode}")
    print(f"  Duration: {elapsed/60:.1f} min")
    print(f"  Log: {log_file}")

    return {
        "label": label,
        "model": model_key,
        "benchmark": benchmark,
        "np": "?",
        "unified": "?",
        "exit_code": r.returncode,
        "duration_min": round(elapsed / 60, 1),
    }


# ── Main ───────────────────────────────────────────────────

def main():
    results = []

    for model in TEST_MODELS:
        mk = model["key"]
        np_def = model["np_default"]
        np_flip = 1 if np_def == 4 else 4

        # Find configs
        cfgs = find_configs(mk)
        if not cfgs:
            print(f"[ERROR] No configs found for {mk}")
            continue
        cfg = cfgs[0]  # use first match

        back_path = cfg["json_path"] + ".bak"
        shutil.copy2(cfg["json_path"], back_path)

        try:
            # ── Condition A: baseline ──
            patch_config(cfg, "llm.load.numParallelSessions", np_def)

            for bm in BENCHMARKS:
                label = f"{mk}__{bm}__np{np_def}_def"
                # Runner loads model itself with current config
                res = run_benchmark(mk, bm, SAMPLE_SIZE, label)
                res["np"] = np_def
                results.append(res)

            # ── Condition B: np-flip ──
            patch_config(cfg, "llm.load.numParallelSessions", np_flip)

            for bm in BENCHMARKS:
                label = f"{mk}__{bm}__np{np_flip}_flip"
                res = run_benchmark(mk, bm, SAMPLE_SIZE, label)
                res["np"] = np_flip
                results.append(res)

        finally:
            # Restore original config
            shutil.copy2(back_path, cfg["json_path"])
            os.remove(back_path)

    # Summary
    print("\n\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    for r in results:
        ok = "OK" if r["exit_code"] == 0 else "FAIL"
        print(f"  {r['label']:55s} {ok}  {r['duration_min']:5.1f} min")


if __name__ == "__main__":
    main()
