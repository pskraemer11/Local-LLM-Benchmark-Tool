# create_humanevalplus_subset.py
# https://chat.mistral.ai/chat/786388ff-8fc8-4c74-bd68-9155ff57d230
import json

input_path = r"C:\Users\pskra\Python-Projekte\Benchmarks\human_eval_plus\HumanEvalPlus-OriginFmt.jsonl"
output_path = r"C:\Users\pskra\Python-Projekte\Benchmarks\human_eval_plus\humanevalplus-80.jsonl"

try:
    # Lese die gesamte Datei als Text
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Fall 1: Datei ist ein JSON-Array (z. B. [ {...}, {...}, ... ])
    if content.startswith("[") and content.endswith("]"):
        print("[INFO] Datei ist ein JSON-Array. Parsen als Liste...")
        all_problems = json.loads(content)
        if not isinstance(all_problems, list):
            raise ValueError("Datei ist kein JSON-Array.")

    # Fall 2: Datei ist JSONL (jeder Eintrag ist eine Zeile)
    else:
        print("[INFO] Datei ist JSONL. Parsen als Zeilen...")
        all_problems = []
        for i, line in enumerate(content.split("\n")):
            line = line.strip()
            if line:
                try:
                    all_problems.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"[WARNING] Zeile {i+1} ist keine gültige JSON: {e}")
                    print(f"Inhalt: {line[:100]}...")

    if not all_problems:
        raise ValueError("Keine gültigen JSON-Daten in der Datei gefunden.")

    print(f"[INFO] Gelesene Aufgaben: {len(all_problems)}")

    # Extrahiere die 80 neuen Aufgaben (ab Index 164)
    if len(all_problems) >= 244:
        new_problems = all_problems[164:244]  # 164 bis 243 (80 Aufgaben)
        print(f"[INFO] Extrahiere 80 neue Aufgaben (Index 164-243).")
    elif len(all_problems) > 164:
        new_problems = all_problems[164:]
        print(f"[WARNING] Datei enthält nur {len(all_problems)} Aufgaben. Nehme alle ab Index 164: {len(new_problems)} Aufgaben.")
    else:
        new_problems = []
        print(f"[ERROR] Datei enthält nur {len(all_problems)} Aufgaben. Keine Aufgaben ab Index 164.")

    if not new_problems:
        raise ValueError("Keine neuen Aufgaben ab Index 164 gefunden.")

    # Speichere das Subset als JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for problem in new_problems:
            f.write(json.dumps(problem) + "\n")

    print(f"[SUCCESS] Subset mit {len(new_problems)} Aufgaben erstellt: {output_path}")

except FileNotFoundError:
    print(f"[ERROR] Datei nicht gefunden: {input_path}")
    print("Bitte überprüfe den Pfad oder benenne die Datei in 'HumanEvalPlus.jsonl' um.")
except Exception as e:
    print(f"[ERROR] Fehler: {e}")