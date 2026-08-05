"""Generate correlation CSV from registry + LMS JSON configs.

Run: python tools/correlation_export.py
Output: correlation_export.csv in project root.

Filters:
- Only rows where context_length_cfg (if exists) < max_context_length_native
- Exclude Kimi-Linear and Gemma-4 architectures
"""

import csv
import json
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_SRC_DIR))

from benchmark_config import USABLE_VRAM_GB
from registry_tool import load_registry, _KV_BYTES
from assemble_blueprint import read_lms_configs, find_all_configs_for_registry_key

CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"

# ── Extended config reader ───────────────────────────────────────────

def _read_config_value(fields: list, key: str):
    """Extract a scalar or {'checked': bool, 'value': ...} from a load/operation field list."""
    for f in fields:
        if f.get("key") == key:
            v = f.get("value")
            if isinstance(v, dict) and "value" in v:
                return v["value"]
            return v
    return None


def read_full_configs(config_root: Path) -> list[dict]:
    """Like read_lms_configs but also reads KV cache, offload, num_parallel, UKV."""
    import time as _time
    models = []
    if not config_root.exists():
        print(f"[WARN] Config root not found: {config_root}")
        return models
    for publisher_dir in sorted(config_root.iterdir()):
        if not publisher_dir.is_dir():
            continue
        publisher = publisher_dir.name
        for item in sorted(publisher_dir.iterdir()):
            if item.is_file() and item.suffix.lower() == ".json":
                json_files = [item]
                model_dir_name = item.stem
            elif item.is_dir():
                json_files = list(item.glob("*.json"))
                if not json_files:
                    continue
                model_dir_name = item.name
            else:
                continue
            for json_path in json_files:
                data = None
                for enc in ("utf-8", "utf-8-sig"):
                    try:
                        with open(json_path, "r", encoding=enc) as f:
                            data = json.load(f)
                        break
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                if data is None:
                    continue
                try:
                    # ── load fields ──
                    ld_fields = data.get("load", {}).get("fields", [])
                    ctx = _read_config_value(ld_fields, "llm.load.contextLength")
                    off = _read_config_value(ld_fields, "llm.load.llama.acceleration.offloadRatio")
                    np_val = _read_config_value(ld_fields, "llm.load.numParallelSessions")
                    ukv = _read_config_value(ld_fields, "llm.load.useUnifiedKvCache")
                    k_cache = _read_config_value(ld_fields, "llm.load.llama.kCacheQuantizationType")
                    v_cache = _read_config_value(ld_fields, "llm.load.llama.vCacheQuantizationType")
                    models.append({
                        "publisher": publisher,
                        "dir_name": model_dir_name,
                        "file_name": json_path.name,
                        "context_length": ctx,
                        "offload": off,
                        "num_parallel": np_val,
                        "use_unified_kv": ukv,
                        "k_cache": k_cache,
                        "v_cache": v_cache,
                        "json_path": json_path,
                    })
                except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"[WARN] Error parsing {json_path}: {e}")
    return models


# ── Helpers ──────────────────────────────────────────────────────────

def _normalize_quant(q: str) -> str:
    """Normalize quant names: fp16→f16, fp32→f32."""
    q = q.lower().replace("fp32", "f32").replace("fp16", "f16")
    return q


def _kv_bytes(k_type: str | None, v_type: str | None) -> float:
    k = _KV_BYTES.get(_normalize_quant(str(k_type)), 2.0) if k_type else 1.5
    v = _KV_BYTES.get(_normalize_quant(str(v_type)), 2.0) if v_type else 1.5
    return k + v


def _is_moe(arch: str, entry: dict) -> str:
    """Determine if model is MoE. Check registry MoE hints first, fall back to arch."""
    # Direct registry fields are most reliable
    ne = entry.get("n_experts")
    nae = entry.get("n_active_experts")
    if ne and nae:
        return "Y"
    if not arch:
        return "N"
    al = arch.lower()
    # DeepSeek-style MoE
    if arch in ("DeepSeek 2", "DeepSeek MoE"):
        return "Y"
    # Some arch names contain architecture/capacity info in parentheses
    if al == "granite-4.0, moe":
        return "N"  # data entry error — Granite-4.0 H Tiny is dense
    # Standard MoE pattern: "Y MoE" where "MoE" is a separate token
    import re
    if re.search(r'\bmoe\b', al):
        return "Y"
    return "N"


def _arch_display(arch: str) -> str:
    return arch or "?"


def _parse_nl_hd_from_arch(arch: str | None) -> tuple[int | None, int | None]:
    """Parse (n_layers, hidden_dim) from arch string if it contains tuple."""
    if not arch:
        return None, None
    # Arch format sometimes: "Qwen3 Dense (48/2048)" or "Gemma-4 (12B)" etc.
    # Actually nl/hd aren't in arch. Return None.
    return None, None


def _model_size_gb(entry: dict) -> float:
    """Get model size in GB from file_size_bytes or offload heuristic."""
    fb = entry.get("file_size_bytes")
    if fb and isinstance(fb, (int, float)) and fb > 0:
        return round(fb / 1_000_000_000, 2)
    # fallback: could parse from model name or leave blank
    return 0.0


# ── Excluded architectures ───────────────────────────────────────────

EXCLUDE_ARCHS = {"kimi-linear", "kimi", "gemma-4"}  # case-insensitive prefix match


def _is_excluded(arch: str, model_key: str) -> bool:
    """Check if model should be excluded (Kimi-Linear or Gemma-4 arch)."""
    al = arch.lower() if arch else ""
    for excl in EXCLUDE_ARCHS:
        if excl in al:
            return True
    return False


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("[1] Registry laden ...")
    reg = load_registry()
    if not reg:
        print("[ERROR] Leere Registry")
        sys.exit(1)

    print("[2] JSON-Configs scannen ...")
    # Use extended reader to get KV cache info
    configs = read_full_configs(CONFIG_ROOT)
    print(f"  -> {len(configs)} Config-Dateien gefunden")

    # Build reverse lookup: normalized config dir_name -> configs
    from registry_tool import normalize_model_name
    config_lookup: dict[str, list[dict]] = {}
    for cfg in configs:
        key = normalize_model_name(cfg["dir_name"])
        config_lookup.setdefault(key, []).append(cfg)
        pub = cfg.get("publisher", "")
        if pub:
            key2 = normalize_model_name(f"{pub}-{cfg['dir_name']}")
            config_lookup.setdefault(key2, []).append(cfg)

    rows = []
    skipped_excluded = 0
    skipped_filter = 0
    skipped_no_match = 0

    print("[3] Daten sammeln ...")
    from registry_tool import normalize_model_name as nfn

    for model_key, entry in reg.items():
        if not isinstance(entry, dict):
            continue

        arch = entry.get("arch", "")
        if _is_excluded(arch, model_key):
            skipped_excluded += 1
            continue

        # ── registry fields ──
        size_gb = _model_size_gb(entry)
        if size_gb == 0:
            size_gb = entry.get("size_gb", 0) or 0

        nl = entry.get("n_layers")
        hd = entry.get("hidden_dim")

        np_reg = entry.get("num_parallel", 1) or 1
        k_reg = str(entry.get("k_cache", "q8_0")) if entry.get("k_cache") else "q8_0"
        v_reg = str(entry.get("v_cache", "iq4_nl")) if entry.get("v_cache") else "iq4_nl"
        ukv_reg = entry.get("useUnifiedKvCache", False)
        off_reg = entry.get("offload", 1.0) or 1.0
        ctx_reg = entry.get("context_length")
        max_ctx_native = entry.get("max_context_length")
        template = entry.get("template", "")
        reasoning = entry.get("reasoning", "")

        if ctx_reg is None:
            continue  # skip entries with no context_length

        context_length_reg = int(ctx_reg)

        # ── find matching configs ──
        search_key = nfn(model_key)
        cfgs = config_lookup.get(search_key, [])
        if not cfgs:
            # Try fuzzy match
            for ck, ci in config_lookup.items():
                if search_key in ck or ck in search_key:
                    cfgs.extend(ci)

        if not cfgs:
            skipped_no_match += 1
            # Still produce a row with only reg values (cfg columns empty)
            cfgs = [{}]  # will use empty defaults

        # Use the first matching config (prefer the one with same publisher)
        cfg = cfgs[0]
        pub = cfg.get("publisher", "")
        if len(cfgs) > 1 and pub:
            same_pub = [c for c in cfgs if c.get("publisher") == pub]
            if same_pub:
                cfg = same_pub[0]

        ctx_cfg = cfg.get("context_length")
        np_cfg = cfg.get("num_parallel")
        k_cfg = cfg.get("k_cache")
        v_cfg = cfg.get("v_cache")
        ukv_cfg = cfg.get("use_unified_kv")
        off_cfg = cfg.get("offload")

        # ── derived values ──
        kv_bytes = _kv_bytes(k_reg, v_reg)

        nl_val = nl if nl and nl > 0 else 0
        hd_val = hd if hd and hd > 0 else 0
        np_reg_val = int(np_reg) if np_reg else 1

        kv_cache_reg_gb = round(
            nl_val * hd_val * 2 * kv_bytes * context_length_reg * np_reg_val / 1e9, 2
        ) if nl_val > 0 and hd_val > 0 else 0.0

        # ── filter: effective_ctx < native_ctx ──
        if ctx_cfg is not None and max_ctx_native is not None:
            if ctx_cfg >= max_ctx_native:
                skipped_filter += 1
                continue

        ratio = round(ctx_cfg / context_length_reg, 2) if ctx_cfg and context_length_reg else None

        rows.append({
            "model_key": model_key,
            "size_gb": size_gb,
            "arch_display": _arch_display(arch),
            "is_moe": _is_moe(arch, entry),
            "n_layers": nl or "",
            "hidden_dim": hd or "",
            "n_heads": entry.get("n_heads", ""),
            "n_kv_heads": entry.get("n_kv_heads", ""),
            "n_experts": entry.get("n_experts", ""),
            "n_active_experts": entry.get("n_active_experts", ""),
            "num_parallel_reg": np_reg_val,
            "num_parallel_cfg": np_cfg if np_cfg is not None else "",
            "k_cache_reg": k_reg if k_reg else "",
            "v_cache_reg": v_reg if v_reg else "",
            "k_cache_cfg": k_cfg if k_cfg else "",
            "v_cache_cfg": v_cfg if v_cfg else "",
            "kv_bytes_per_element": kv_bytes,
            "use_unified_kv_reg": ukv_reg if ukv_reg is not None else "",
            "use_unified_kv_cfg": ukv_cfg if ukv_cfg is not None else "",
            "offload_reg": off_reg,
            "offload_cfg": off_cfg if off_cfg is not None else "",
            "context_length_reg": context_length_reg,
            "context_length_cfg": ctx_cfg if ctx_cfg is not None else "",
            "cfg_vs_reg_ratio": ratio if ratio is not None else "",
            "kv_cache_reg_gb": kv_cache_reg_gb,
            "max_context_length_native": max_ctx_native if max_ctx_native else "",
            "template": template if template else "",
            "reasoning": reasoning if reasoning else "",
        })

    print(f"  -> {len(rows)} Rows erzeugt")
    print(f"  -> {skipped_excluded} ausgeschlossen (Kimi/Gemma-4 Architektur)")
    print(f"  -> {skipped_filter} gefiltert (effective_ctx >= native_ctx)")
    print(f"  -> {skipped_no_match} ohne Config-Match")

    # ── write CSV ──
    output_path = _PROJECT_ROOT / "correlation_export.csv"
    columns = [
        "model_key", "size_gb", "arch_display", "is_moe",
        "n_layers", "hidden_dim", "n_heads", "n_kv_heads",
        "n_experts", "n_active_experts",
        "num_parallel_reg", "num_parallel_cfg",
        "k_cache_reg", "v_cache_reg", "k_cache_cfg", "v_cache_cfg",
        "kv_bytes_per_element",
        "use_unified_kv_reg", "use_unified_kv_cfg",
        "offload_reg", "offload_cfg",
        "context_length_reg", "context_length_cfg", "cfg_vs_reg_ratio",
        "kv_cache_reg_gb", "max_context_length_native",
        "template", "reasoning",
    ]

    print(f"\n[4] Schreibe {output_path} ...")
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[OK] {len(rows)} Zeilen geschrieben -> {output_path}")


if __name__ == "__main__":
    main()
