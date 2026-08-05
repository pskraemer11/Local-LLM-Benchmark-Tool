#!/usr/bin/env python3
"""
Korrelation effective_ctx vs Parameter.
Filter: ctx_cfg < native_ctx, OHNE Gemma-4 und Kimi-Linear (keine KV-Quantisierung).
"""

import json, os, sys, re
from pathlib import Path
from statistics import median, mean
_SRC_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_SRC_DIR))

from ruamel.yaml import YAML
y = YAML()
y.preserve_quotes = True

REGISTRY_PATH = _PROJECT_ROOT / "doc-git" / "model_registry.yaml"
reg = y.load(open(REGISTRY_PATH, "r", encoding="utf-8")) or {}
CONFIG_ROOT = Path.home() / ".lmstudio" / ".internal" / "user-concrete-model-default-config"

from assemble_blueprint import normalize_model_name, find_all_configs_for_registry_key

def read_lms_configs(config_root: Path) -> list[dict]:
    cfgs = []
    if not config_root.is_dir():
        return cfgs
    for pub in sorted(os.listdir(str(config_root))):
        pub_dir = config_root / pub
        if not pub_dir.is_dir():
            continue
        for repo in sorted(os.listdir(str(pub_dir))):
            repo_dir = pub_dir / repo
            if not repo_dir.is_dir():
                continue
            for fname in sorted(os.listdir(str(repo_dir))):
                if not fname.endswith(".json"):
                    continue
                fp = repo_dir / fname
                try:
                    data = json.loads(fp.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    continue
                fields = {}
                for f in data.get("load", {}).get("fields", []):
                    if isinstance(f, dict):
                        v = f.get("value")
                        if isinstance(v, dict) and "value" in v:
                            v = v["value"]
                        fields[f.get("key")] = v
                ctx = fields.get("llm.load.contextLength")
                cfgs.append({
                    "context_length": int(ctx) if ctx else None,
                    "publisher": pub,
                    "dir_name": repo,
                    "fname": fname,
                    "num_parallel": fields.get("llm.load.numParallelSessions"),
                    "use_unified_kv": fields.get("llm.load.useUnifiedKvCache"),
                    "k_cache": fields.get("llm.load.llama.kCacheQuantizationType"),
                    "v_cache": fields.get("llm.load.llama.vCacheQuantizationType"),
                })
    return cfgs

_KV_BYTES = {"q8_0": 1.0, "q5_1": 0.625, "iq4_nl": 0.5, "f16": 2.0, "q4_0": 0.5, "q4_1": 0.625}

def is_gemma4(key: str) -> bool:
    return "gemma-4" in key.lower() or "google_gemma-4" in key.lower()

def is_kimi(key: str) -> bool:
    return "kimi" in key.lower() or "moonshotai_kimi" in key.lower()

cfgs = read_lms_configs(CONFIG_ROOT)
reg_key_map = {normalize_model_name(k): (k, v) for k, v in reg.items() if isinstance(v, dict)}

rows = []
for norm_key, (orig_key, v) in reg_key_map.items():
    fs = v.get("file_size_bytes")
    if not fs or not v.get("n_layers") or not v.get("hidden_dim"):
        continue
    size_gb = fs / 1_000_000_000
    arch = v.get("arch", "?")
    np_val = v.get("num_parallel", 1)
    kc = v.get("k_cache", "?")
    vc = v.get("v_cache", "?")
    ctx_reg = v.get("context_length")
    nl = v.get("n_layers")
    hd = v.get("hidden_dim")
    native = v.get("max_context_length")
    ukv = v.get("useUnifiedKvCache")

    kl = orig_key.lower()
    is_moe = "MoE" in arch or any(x in kl for x in ["a4b", "a3b", "a2b"])
    kv_bytes = _KV_BYTES.get(kc, 1.0) + _KV_BYTES.get(vc, 0.5)

    matches = find_all_configs_for_registry_key(orig_key, cfgs)
    ctx_cfg = None
    cfg_np = None
    if matches:
        ctx_vals = [m["context_length"] for m in matches if m.get("context_length")]
        if ctx_vals:
            ctx_cfg = min(ctx_vals)

    rows.append({
        "key": orig_key[:64],
        "fam": "Gemma4" if is_gemma4(orig_key) else ("Kimi" if is_kimi(orig_key) else "Normal"),
        "size_gb": size_gb,
        "is_moe": is_moe,
        "np": np_val,
        "nl": nl,
        "hd": hd,
        "kc": kc, "vc": vc,
        "kv_bytes": kv_bytes,
        "ctx_reg": ctx_reg, "ctx_cfg": ctx_cfg,
        "native": native,
    })

# ── FILTER ──
total = len(rows)
vram = [r for r in rows if r["ctx_cfg"] and r["native"] and r["ctx_cfg"] < r["native"]]
vram_normal = [r for r in vram if r["fam"] == "Normal"]
gemma_kimi = [r for r in vram if r["fam"] != "Normal"]
arch = [r for r in rows if r["ctx_cfg"] and r["native"] and r["ctx_cfg"] >= r["native"]]
unknown = [r for r in rows if r["ctx_cfg"] and (not r["native"] or r["ctx_cfg"] is None)]

print("=" * 100)
print("FILTERSTUFE")
print("=" * 100)
print(f"{'':30s} {'Anzahl':>8s}")
print(f"{'Modelle total':30s} {total:>8d}")
print(f"{'VRAM-begrenzt (cfg < native)':30s} {len(vram):>8d}")
print(f"{'  davon Normal':30s} {len(vram_normal):>8d}")
print(f"{'  davon Gemma-4/Kimi (excluded)':30s} {len(gemma_kimi):>8d}")
print(f"{'Architektur-begrenzt (cfg >= native)':30s} {len(arch):>8d}")
print(f"{'native_ctx unbekannt':30s} {len(unknown):>8d}")

print(f"\n{'='*100}")
print("VRAM-BEGRENZT (Normal) — Einzelmodelle")
print(f"{'='*100}")
for r in sorted(vram_normal, key=lambda x: x["ctx_cfg"] / x["native"]):
    ratio = r["ctx_cfg"] / r["native"]
    moe_s = "MoE" if r["is_moe"] else "Dense"
    print(f"  {r['key']:64s}  {r['size_gb']:5.1f}GB  {moe_s:5s}  np={r['np']}  "
          f"kv={r['kv_bytes']:.1f}B  {r['kc']:5s}/{r['vc']:5s}  "
          f"native={r['native']:>7_d}  cfg={r['ctx_cfg']:>7_d}  r={ratio:.2f}")

# Excluded
print(f"\n{'='*100}")
print(f"AUSGESCHLOSSEN (Gemma-4 / Kimi, keine KV-Quantisierung)")
print(f"{'='*100}")
for r in sorted(gemma_kimi, key=lambda x: x["ctx_cfg"] / x["native"]):
    ratio = r["ctx_cfg"] / r["native"]
    print(f"  {r['key']:64s}  {r['size_gb']:5.1f}GB  fam={r['fam']:7s}  "
          f"kv={r['kv_bytes']:.1f}B  {r['kc']:5s}/{r['vc']:5s}  "
          f"native={r['native']:>7_d}  cfg={r['ctx_cfg']:>7_d}  r={ratio:.2f}")

# ── KORRELATIONEN (nur vram_normal) ──
vr = vram_normal
if not vr:
    print("\nKeine Modelle für Korrelation.")
    sys.exit(0)

print(f"\n{'='*100}")
print("KORRELATIONEN (nur VRAM-begrenzt, Normal-Modelle)")
print(f"{'='*100}")

# 1. np
print(f"\n1. np-Effekt:")
by_np = {}
for r in vr:
    by_np.setdefault(r["np"], []).append(r)
for np_v in sorted(by_np):
    vals = sorted([r["ctx_cfg"] for r in by_np[np_v]])
    n_moe = sum(1 for r in by_np[np_v] if r["is_moe"])
    print(f"   np={np_v}: {len(vals):>2d} ({n_moe} MoE), median={int(median(vals)):>7_d}, range={vals[0]:>6_d}–{vals[-1]:>6_d}")

# 2. MoE vs Dense
print(f"\n2. MoE vs Dense:")
for is_moe, label in [(False, "Dense"), (True, "MoE")]:
    grp = [r for r in vr if r["is_moe"] == is_moe]
    if not grp:
        continue
    vals = sorted([r["ctx_cfg"] for r in grp])
    avg_gb = mean([r["size_gb"] for r in grp])
    avg_np = mean([r["np"] for r in grp])
    print(f"   {label} ({len(grp):>2d}, {avg_gb:.1f} GB avg, np={avg_np:.1f}): "
          f"median={int(median(vals)):>7_d}, range={vals[0]:>6_d}–{vals[-1]:>6_d}")

# 3. KV-Quant
print(f"\n3. KV-Quant (k/v aus Registry):")
kv_g = {}
for r in vr:
    kv_g.setdefault(f"{r['kc']}+{r['vc']}", []).append(r["ctx_cfg"])
for kk, vals in sorted(kv_g.items()):
    print(f"   {kk:16s} ({len(vals):>2d}): median={int(median(vals)):>7_d}")

# 4. Größenklassen (getrennt MoE/Dense)
print(f"\n4. Größenklassen (VRAM-begrenzt, Median):")
print(f"   {'Bereich':>12s} {'#MoE':>4s} {'#Den':>4s} {'MoE-med':>9s} {'Den-med':>10s} {'Reg-med':>8s}")
print(f"   {'-'*50}")
for lo, hi in [(0, 8), (8, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 99)]:
    gm = [r for r in vr if lo <= r["size_gb"] < hi and r["is_moe"]]
    gd = [r for r in vr if lo <= r["size_gb"] < hi and not r["is_moe"]]
    gr = [r for r in vr if lo <= r["size_gb"] < hi]
    mm = int(median([r["ctx_cfg"] for r in gm])) if gm else 0
    dm = int(median([r["ctx_cfg"] for r in gd])) if gd else 0
    rm = int(median([r["ctx_reg"] for r in gr])) if gr else 0
    print(f"   {f'{lo}–{hi} GB':>12s} {len(gm):>4d} {len(gd):>4d} {mm:>9_d} {dm:>10_d} {rm:>8_d}")

# 5. np=1 vs np=4 MoE
print(f"\n5. Dense np=1 vs MoE np=4 (die zwei Hauptgruppen):")
d1 = [r for r in vr if not r["is_moe"] and r["np"] == 1 and r["ctx_cfg"]]
m4 = [r for r in vr if r["is_moe"] and r["np"] == 4 and r["ctx_cfg"]]
if d1:
    v1 = sorted([r["ctx_cfg"] for r in d1])
    avg_gb = mean([r["size_gb"] for r in d1])
    print(f"   Dense np=1 ({len(d1):>2d}, {avg_gb:.1f} GB avg): median={int(median(v1)):>7_d}, range={v1[0]:>6_d}–{v1[-1]:>6_d}")
if m4:
    v4 = sorted([r["ctx_cfg"] for r in m4])
    avg_gb = mean([r["size_gb"] for r in m4])
    print(f"   MoE  np=4 ({len(m4):>2d}, {avg_gb:.1f} GB avg): median={int(median(v4)):>7_d}, range={v4[0]:>6_d}–{v4[-1]:>6_d}")

# 6. Spezifisch: 12-13 GB
print(f"\n6. 12–13 GB Band (die größte Gruppe):")
g12 = [r for r in vr if 12 <= r["size_gb"] < 13]
print(f"   Total: {len(g12)} Modelle")
for np_v in sorted(set(r["np"] for r in g12)):
    grp = [r for r in g12 if r["np"] == np_v]
    vals = sorted([r["ctx_cfg"] for r in grp])
    nm = sum(1 for r in grp if r["is_moe"])
    print(f"   np={np_v} ({len(grp):>2d}, {nm} MoE): median={int(median(vals)):>7_d}, range={vals[0]:>6_d}–{vals[-1]:>6_d}")

# 7. Vorschlag: basis_ctx aus der Realität
print(f"\n7. TABELLEN-VORSCHLAG (aus Median der VRAM-begrenzten Normal-Modelle):")
print(f"   {'Bereich':>12s} {'Dense np=1':>12s} {'MoE np=4':>12s} {'Aktuelle Tab':>12s}")
print(f"   {'-'*52}")
# Dense np=1
dense_tbl = {}
for r in vr:
    if not r["is_moe"] and r["np"] == 1:
        for lo, hi in [(0, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 99)]:
            if lo <= r["size_gb"] < hi:
                dense_tbl.setdefault((lo, hi), []).append(r["ctx_cfg"])
# MoE np=4
moe_tbl = {}
for r in vr:
    if r["is_moe"] and r["np"] == 4:
        for lo, hi in [(0, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 99)]:
            if lo <= r["size_gb"] < hi:
                moe_tbl.setdefault((lo, hi), []).append(r["ctx_cfg"])
# Aktuelle Tabelle
cur_tbl = {14: 16384, 13: 32768, 12: 49152, 11: 65536, 10: 98304, 9: 131072}

for lo, hi in [(0, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 99)]:
    dm = int(median(dense_tbl[(lo, hi)])) if (lo, hi) in dense_tbl and dense_tbl[(lo, hi)] else 0
    mm = int(median(moe_tbl[(lo, hi)])) if (lo, hi) in moe_tbl and moe_tbl[(lo, hi)] else 0
    # Aktuelle Tabelle: finde den base_ctx für diese GB-Klasse
    cur_base = 262144
    for limit, ctx in sorted(cur_tbl.items(), reverse=True):
        if lo >= limit:
            cur_base = ctx
            break
    cur_scaled = max(16384, int(cur_base * 1.0)) if dm else 0  # Dense np=1
    print(f"   {f'{lo}–{hi} GB':>12s} {dm:>12_d} {mm:>12_d} {cur_base:>12_d}")
