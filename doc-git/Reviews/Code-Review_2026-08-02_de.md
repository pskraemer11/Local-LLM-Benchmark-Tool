# Code-Review / Änderungslog 2026-08-02 – Struktur-Gate, Agentic-Safety, Run-Spec

> **Status:** Umsetzung Plan-Punkte 1, 3 und 4 (LLM-as-judge [P2] wegen Cloud-Abhängigkeit abgelehnt).
> **Scope:** `run_benchmarks.py`, `custom_benchmark.py`, `csv_writer.py`, `type_defs.py`,
> `benchmark_config.py`, `tools/parallel_ab.py` + Tests (693 gruen).
> **Basis:** Vorgänger-Review `Code-Review_2026-07-28` (9 Haupt-Skripte, 7.925 LOC, 559 Tests).

---

## 0. Zusammenfassung

| Punkt | Inhalt | Status |
|---|---|---|
| P1 | Struktur-Gate / Output-Fidelity (CSV-Spalten `output_status`, `entry_point_found`, `extracted_code`) | done |
| P4 | Adversarial-Safety-Selektion (`--agentic-mode safety`, 13 Category-K-Szenarien) | done |
| P3 | YAML-Run-Spec (`--run-spec/--config run.yaml`, Precedence CLI>YAML>Defaults, Seed-Durchgängigkeit) | done |
| P2 | LLM-as-judge (OpenAI/promptfoo llm-rubric) | **nicht** – erfordert Cloud-Provider |
| Doku | Auswertung DS1000-Re-Run + Feature-Übersicht | ReRun teils (Ternary 0.10 / gpt-oss 0.20 gemessen; Q1_0+8B laufen) |

Test-Suite: **693 passed** (Delta +14: 12 TestRunSpec + 2 parallel_ab-Seed-Tests).

---

## 1. P1 – Struktur-Gate / Output-Fidelity

**Ziel:** Pro Antwort binär und granular erfassen, ob überhaupt eine parsebare Code-Struktur
vorliegt (d.h. DS1000-Harness-/Bare-Execution-Fehler von "kein Code erzeugt" trennen).

### `custom_benchmark.py`
- Neu `classify_output(code: str, response: str, is_structured: bool, entry_point: str = "")`
  → Status: `"empty" | "json_ok" | "json_missing_code" | "json_invalid" | "fenced" | "bare"`
  plus `entry_point_found: bool` (nur wenn `entry_point`-Param nicht leer).
- `_call_and_evaluate(...)` ruft `classify_output` und schreibt `output_status` +
  `entry_point_found` ins `TaskResult`. Timeout-/Unknown-/Error-Pfade setzen die Felder mit.
- `evaluate_code(...)`: Entry-Point-Triage **nur** im Direkt-Tests-Pfad
  (`tests and entry_point`); DS1000-Harness/Bare bleiben unverändert (DS1000 nutzt
  `exec()`-Semantik statt Entry-Point-Suite → keine Triage-Restriktion).

**Abgrenzung:** Keine Score-/Pipeline-Änderung; reine Diagnose-Telemetrie.

---

## 2. P4 – Adversarial-Safety-Selektion

- `benchmark_config.py`: Neu `AGENTIC_SAFETY_SCENARIO_IDS` (13 TC-Strings):
  TC-31..36 (Prompt-Injection-assoziert) + TC-41..43 (Safety/Boundaries) + TC-57..60
  (weitere Category-K, s. `evals/scenarios*.py` aus tool_eval_bench v2.0.7).
- `run_benchmarks.py`: `run_agentic(model_info, limit, mode="random", seed)`.
  - `mode="safety"` → `AGENTIC_SAFETY_SCENARIO_IDS`, sonst alle 69 (`TOOL_EVAL_SCENARIO_IDS`).
  - deterministisch via `random.Random(seed)` (nicht globales `random`).
- CLI: `--agentic-mode {random,safety}` (Default `random`).
- Aufruf in `_run_benchmarks_for_model` übergibt `mode=` und `seed=`.

---

## 3. P3 – YAML-Run-Spec + Seed

### `run_benchmarks.py`
- `RUN_SPEC_DEST_MAP`: YAML-Keys → CLI-Dest (snake/kebab-Aliase akzeptiert).
- `_load_run_spec(path)`: PyYAML `safe_load`; fatal bei Datei-Fehler / Nicht-Mapping;
  unbekannte Top-Level-Keys → `[WARN]` (ignoriert). Listen-Felder (models/benchmarks/
  exclude_benchmarks) → Komma-String; Bool-/int-Validierung.
- `_validate_run_spec_selections(spec, available_models)`: Warnt bei unbekannten
  Benchmark-Namen (gegen `ALL_BENCH_NAMES` / Numerik-Ranges) und unbekannten
  Modell-Namen (nur Text-Einträge; `all`/Nummern/Ranges werden übersprungen).
- `_apply_run_spec(args, spec, explicit_dests)`: **Precedence CLI > YAML > Defaults**.
  Exakt via SUPPRESS-Probe-Parser (nur explizit gesetzte CLI-Dest-Namen zählen),
  nicht über Default-Vergleich-Heuristik.
- `--run-spec`/`--config <file.yaml>` in `_parse_args`.
- Parser-Argumente in `_LAUNCHER_ARG_SPECS` zusammengefasst (Haupt- + Probe-Parser nutzen dieselben Specs).

### `tools/parallel_ab.py`
- `build_prompts(..., seed=None)` (ohne Seed weiterhin `RANDOM_SEED=42`).
- CLI-Flag `--seed` (reproduzierbare Prompt-Auswahl).

### Beispiel
eine lokale YAML-Run-Spec (Modelle/Benchmarks/sample_size/seed/agentic_mode + Flags).

---

## 4. Tests (neu)

| Test-Klasse/-Fall | Datei | Zweck |
|---|---|---|
| `TestRunSpec` (12) | `tests/test_run_benchmarks.py` | Laden, Listen→CSV, Unbekannt-Warn, Bool/Int-Typen, Fatal-Fehler (Datei fehlt/YAML kaputt), `_apply_run_spec` Precedence (YAML füllt Defaults; CLI-Werte bleiben), End-to-End `_parse_args` mit `--run-spec` |
| `test_parse_args_cli_flags_win_over_run_spec` | dito | CLI `-s`/`--seed` über YAML |
| Seed-Tests (2) | `tests/test_parallel_ab.py` | impliziter Seed 42 reproduzierbar; expliziter Seed identisch |

---

## 5. Offene Punkte / empfohlene Schritte

- **DS1000-Re-Run (Struktur-Gate) 02.08. abgeschlossen (alle 4 Modelle):**
  - Ternary-Bonsai 0.10 (9×`empty`, 1×`fenced`); GPT-OSS 0.20 (10×`fenced`),
    Bonsai 27B@Q1_0 0.30 (6×`empty`, 4×`fenced`); Bonsai 8B 0.60 (10×`bare`).
  - 8B-Diff zu Morgenlauf (0.0 → 0.6) über `bare`-Pfad; siehe Auswertungsdatei Sektion 7.
- **Lauf-Hürde behoben:** `resolve_models(registry_only=True)` fand anfangs nur 2/4 Modelle
  (Registry-Normalisierung `prism-ml/bonsai-27b@q1_0`→`bonsai-27b@q1-0` ≠ installiertes `bonsai-27b`).
  Nach `registry_tool.py sync` (53 assembled, 191 validiert) stehen alle 4 bereit.
- Ergebnisdoku in `Auswertung Bonsai-27b + gpt-oss DS1000-Testlauf ..._02.08.2026.md` (Sektion 7).
- Bewusst NICHT enthalten: P2-Judge, temperatura/top_p-Overrides im Run-Spec (wird aus
  `MODEL_TEMP_OVERRIDES` versorgt; Hinweis im Spec).
