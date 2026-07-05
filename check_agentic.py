import csv, glob, os

files = glob.glob("ergebnisse/konsolidiert_2026*.csv")
if not files:
    print("No consolidated CSVs found.")
    raise SystemExit(1)
latest = max(files, key=os.path.getmtime)
print("Latest:", latest)

with open(latest, "r", encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter=";")
    rows = list(r)

total = len(rows)
has = [row["Model"] for row in rows if row.get("Agentic", "")]
missing = [row["Model"] for row in rows if not row.get("Agentic", "")]

print()
for row in rows:
    a = row.get("Agentic", "")
    if a:
        print(f'{row["Model"]:35s} Agentic={a}')

print()
print(f"{len(has)}/{total} models have Agentic")
print()
print("Missing Agentic:")
for m in missing:
    print(f"  {m}")
