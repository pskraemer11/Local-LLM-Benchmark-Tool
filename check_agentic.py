import csv, glob, os
files = glob.glob("ergebnisse/konsolidiert_2026*.csv")
latest = max(files, key=os.path.getmtime)
print("Latest:", latest)
with open(latest, "r", encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter=";")
    for row in r:
        a = row.get("Agentic","")
        if a:
            print(f'{row["Modell"]:35s} Agentic={a}')
print()
with open(latest, "r", encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter=";")
    has = [row["Modell"] for row in r if row.get("Agentic","")]
    f.seek(0)
    next(f)
    total = sum(1 for _ in csv.DictReader(f, delimiter=";"))
print(f"{len(has)}/{total} Modelle haben Agentic")
print()
# Also list which models are MISSING agentic
with open(latest, "r", encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter=";")
    missing = [row["Modell"] for row in r if not row.get("Agentic","")]
print("Fehlende Agentic:")
for m in missing:
    print(f"  {m}")
