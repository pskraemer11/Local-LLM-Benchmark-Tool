#!/usr/bin/env python3
"""Extract Top 5 lists from the consolidated CSV."""
import csv, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(BASE_DIR, "ergebnisse", "konsolidiert_20260618_001220.csv")

rows = []
with open(path, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=";")
    for r in reader:
        rows.append(r)

def top5(title, key, show_eff=False):
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")
    sorted_rows = sorted(rows, key=lambda r: float(r.get(key, 0) or 0), reverse=True)
    for i, r in enumerate(sorted_rows[:5], 1):
        val = float(r.get(key, 0) or 0)
        overall = float(r.get("Overall", 0) or 0)
        if key == "Avg tok/s":
            print(f"  {i}. {r['Modell']:35s} {val:>6.1f} tok/s  (Overall: {overall:.1%})")
        elif key == "Eff (Score/tok/s)":
            print(f"  {i}. {r['Modell']:35s} {val:>8.4f}  (Overall: {overall:.1%})")
        else:
            print(f"  {i}. {r['Modell']:35s} {val:>5.1%}  (Overall: {overall:.1%})")

top5("TOP 5 GESCHWINDIGKEIT (tok/s)", "Avg tok/s")
top5("TOP 5 EFFIZIENZ (Score/tok/s)", "Eff (Score/tok/s)")
top5("TOP 5 CODING", "Coding")
top5("TOP 5 MATH", "Math")
