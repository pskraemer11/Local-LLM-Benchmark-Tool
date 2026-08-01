#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Traegt gpt-oss-20b-GGUF-Varianten die fehlende Reasoning-Effort-Konfiguration
in LM Studio nach (Fix 2026-07-31).

Hintergrund: LM Studio-Warnung
  "No valid custom reasoning fields found in model '...'. Reasoning setting
  'low' cannot be converted to any custom KVs."
Nur openai/gpt-oss-20b.json (das Original) besitzt die Felder
  ext.virtualModel.customField.openai.gptOss20b.reasoningEffort = "low"
  llm.prediction.reasoning.parsing = {enabled:false, <think>/</think>}
Alle GGUF-Datei-Varianten (Intel AutoRound, bartowski, lmstudio-community,
unsloth) haben sie nicht -> reasoning_effort aus der API wird ignoriert.

Das Tool ergaenzt die fehlenden Felder idempotent und erstellt vor jeder
Aenderung ein Backup (Datei + ".bak-<ts>").

Usage:
  python src/tools/patch_reasoning_effort.py [--dry-run] [--wait-for-lock]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Optional

import psutil

LMSTUDIO_ROOT = os.path.join(os.path.expanduser("~"), ".lmstudio")
CONFIG_DIR = os.path.join(LMSTUDIO_ROOT, ".internal", "user-concrete-model-default-config")
LOCK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "ergebnisse", ".benchmark.lock")

EFFORT_FIELD = {
    "key": "ext.virtualModel.customField.openai.gptOss20b.reasoningEffort",
    "value": "low",
}
PARSING_FIELD = {
    "key": "llm.prediction.reasoning.parsing",
    "value": {"enabled": False, "startString": "<think>", "endString": "</think>"},
}
REQUIRED_FIELDS = [EFFORT_FIELD, PARSING_FIELD]


def find_configs() -> list[str]:
    """Alle gpt-oss-20b-Konfigurationsdateien unter dem LM-Studio-Config-Verzeichnis."""
    pattern = os.path.join(CONFIG_DIR, "**", "*gpt-oss*20b*.json")
    configs = []
    for path in glob.glob(pattern, recursive=True):
        if ".bak" in path:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "operation" in data and "fields" in data.get("operation", {}):
                configs.append(path)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(configs)


def missing_fields(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Die der Konfiguration fehlenden Pflichtfelder (idempotent)."""
    present_keys = {f.get("key") for f in data.get("operation", {}).get("fields", [])}
    return [f for f in REQUIRED_FIELDS if f["key"] not in present_keys]


def backup_path(path: str) -> str:
    return f"{path}.bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def patch_config(path: str, dry_run: bool = False) -> tuple[bool, list[str], Optional[str]]:
    """Patcht eine Config-Datei. Returns (changed, added_keys, backup_path)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    missing = missing_fields(data)
    if not missing:
        return False, [], None
    if dry_run:
        return True, [m["key"] for m in missing], None
    backup = backup_path(path)
    with open(path, "r", encoding="utf-8") as f_src, open(backup, "w", encoding="utf-8") as f_dst:
        f_dst.write(f_src.read())
    data["operation"]["fields"].extend(missing)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True, [m["key"] for m in missing], backup


def lock_held_by_live_process() -> Optional[int]:
    if not os.path.exists(LOCK_PATH):
        return None
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as f:
            pid = int(json.load(f).get("pid", -1))
    except (OSError, ValueError, KeyError):
        return None
    if pid > 0 and psutil.pid_exists(pid):
        try:
            if psutil.Process(pid).is_running():
                return pid
        except psutil.Error:
            return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fuegt gpt-oss-20b GGUF-Varianten die Reasoning-Effort-Felder nach")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen, welche Configs patchen wuerden (keine Aenderung)")
    parser.add_argument("--wait-for-lock", action="store_true",
                        help="Warten, bis kein Benchmark-Launcher mehr laeuft")
    args = parser.parse_args()

    while True:
        owner = lock_held_by_live_process()
        if owner is None:
            break
        if not args.wait_for_lock:
            print("[FATAL] Benchmark-Launcher laeuft noch (PID %s) - Config-Aenderung "
                  "waehrend eines Laufs wuerde die Ergebnisse inkonsistent machen. "
                  "--wait-for-lock nutzen." % owner)
            sys.exit(1)
        print("[WAIT] Launcher PID %s laeuft noch - pruefe in 60s erneut..." % owner)
        time.sleep(60)

    configs = find_configs()
    if not configs:
        print("[WARN] Keine gpt-oss-20b-Konfigurationsdateien unter %s gefunden" % CONFIG_DIR)
        sys.exit(0)

    print("[INFO] %d gpt-oss-20b-Configs gefunden%s" % (len(configs),
                                                        " (DRY-RUN)" if args.dry_run else ""))
    changed = 0
    for path in configs:
        did_change, added, backup = patch_config(path, dry_run=args.dry_run)
        if did_change:
            changed += 1
            short = path.replace(CONFIG_DIR, "")
            print("  [%s] %s" % ("PATCH" if not args.dry_run else "WUERDE PATCHEN", short))
            for key in added:
                print("      + %s" % key)
            if backup:
                print("      Backup: %s" % backup)
        else:
            print("  [OK]   %s (bereits vollstaendig)" % path.replace(CONFIG_DIR, ""))
    print("\n[%s] %d/%d Configs geaendert." %
          ("DRY-RUN" if args.dry_run else "OK", changed, len(configs)))
    if not args.dry_run and changed:
        print("[INFO] Wirksam ab dem naechsten Laden des Modells.")


if __name__ == "__main__":
    main()
