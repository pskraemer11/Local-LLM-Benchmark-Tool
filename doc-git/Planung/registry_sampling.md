# Registry-Sampling – Migrationsplan

Status: 2026-08-13. Legend: [ ] open, [~] in progress, [x] done/checked.

## Ziel

Eine robuste, zentrale Quelle für Sampling-Parameter (temperature/top_p/top_k/min_p/enable_thinking)
pro Modell in `doc-git/model_registry.yaml` (SSOT), die von allen Lesern genutzt wird.
Bisher lag die Quelle ausschließlich in `MODEL_CATEGORY_SAMPLING` (`src/benchmark_config.py`),
einer zentralen Ausnahme-Tabelle (Research 06.08.2026).

## A. Registry-Datenmodell (Variante A – flaches Feld-Objekt pro Modell)

Entscheidung (Nutzer, 11.08.): **Option B** (Registry-Felder, SSOT), **Variante A** (flach).

Schema pro Modell in `doc-git/model_registry.yaml`:

```yaml
model_key@quant:
  publisher: ...
  hf_url: ...
  pub_url: ...
  arch: ...
  sampling:
    coding:
      temperature: 0.6
      top_p: 0.95
      top_k: 40
      min_p: 0.0
      enable_thinking: false
    knowledge:        # identische Struktur
    agentic:          # identische Struktur
    math:             # identische Struktur
    thinking:
      enabled: false
      temperature: 0.6
      top_p: 0.95
```

- Kategorien: `coding`, `knowledge`, `agentic`, `math` (je temperature/top_p/top_k/min_p/enable_thinking)
- `thinking` (optional): `enabled`, `temperature`, `top_p`
- Einfügeposition: direkt nach der `arch:`-Zeile des Modell-Blocks

### Validierungsregeln (Constraints)

- `0.0 <= temperature <= 1.0`
- `0.0 <= top_p <= 1.0`
- `0 <= top_k <= 2048` (modellabhängig)
- `min_p >= 0`
- `enable_thinking` ist bool
- `thinking.enabled` ist bool, `thinking.temperature/top_p` analog

### Backward-Compatibility

- Bestehende Einträge bleiben funktional; `sampling:` ist optional.
- Fehlt `sampling:`, greift der Fallback: `MODEL_CATEGORY_SAMPLING` → `BENCHMARK_CATEGORY_DEFAULTS`
  → `BENCHMARK_THINKING_DEFAULTS` (bestehende Logik in `get_model_config`, unverändert).

## B. Migration-Steps

- [x] **1. Spezifikation finalisieren** — Variante A (flach pro Modell), Kategorien coding/knowledge/agentic/math + thinking-Unterblock. Datenmodell siehe Abschnitt A.
- [x] **2. Schema-Design finalisieren** — verschachteltes dict pro Kategorie, Validierungsregeln definiert (Abschnitt A).
- [x] **3. Migration umsetzen** — 17 von 47 Registry-Modellen mit `sampling:`-Block ergänzt (4 als Pilot einzeln, 14 gebündelt per Skript, 1 Block entfernt). Jede Änderung im Migration-Log (`doc-git/Planung/registry_sampling_log.md`) protokolliert.
- [x] **4. Lesepfade implementieren** — `get_model_config`/`_sampling_cell` lesen die Registry-`sampling:`-Felder (Precedence: Registry → `MODEL_CATEGORY_SAMPLING`-Fallback → Kategorie-Defaults). Quelle via `_source` ("registry-sampling" | "benchmark-table" | "thinking-default" | "category-default").
- [x] **5. `MODEL_CATEGORY_SAMPLING` abwickeln** — Entscheidung (Nutzer, 13.08.): **als Fallback behalten** (gilt für die 30 Modelle ohne `sampling:`-Block + fehlende Kategorien in Registry-Blöcken).
- [x] **6. Tests** — 148 relevante Tests grün (inkl. 7 neue Registry-Sampling-Tests); volle Suite 790 passed / 3 pre-existing TabbyAPI-Fehler.
- [x] **7. Rollout / Doku** — CHANGELOG-Eintrag, `doc-git/Planung/registry_sampling.md` (diese Datei), `thinking-config_en.md` + `Temperature Recommondations_en.md` Referenz aktualisiert, HowTo (Abschnitt G).

## C. Betroffene Modelle (Ist-Stand 13.08.)

**17 von 47 Modellen** haben `sampling:` (Werte = recherchierte Empfehlungen aus `MODEL_CATEGORY_SAMPLING`):

1. `noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4` (Pilot)
2. `unsloth/gemma-4-12b-it-qat@q4_k_xl` (Pilot)
3. `mradermacher/kimi-linear-reap-35b-a3b-instruct-i1@iq3_xxs` (Pilot)
4. `mradermacher/qwen3.6-27b-i1@q3_k_s` (Pilot)
5. `mradermacher/qwen3.6-28b-reap-i1@iq3_s`
6. `mradermacher/qwen3.6-28b-reap-i1@q3_k_s`
7. `mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m`
8. `mradermacher/gemma-4-26b-a4b-it-heretic-i1@iq3_m`
9. `lmstudio-community/internlm2-math-plus-20b@q4_k_m`
10. `quietimpostor/nemotron-3-nano-reap-21b-a3b@mxfp4`
11. `intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k`
12. `jetbrains/mellum2-12b-a2-5b-thinking-moe@mxfp4`
13. `noctrex/lfm2-24b-a2b-moe@mxfp4`
14. `crucible-labs/gemma4-26b-a4b-reap-25@mixed`
15. `qwen/qwen3.5-9b@q6_k`
16. `qwen/qwen3-14b@q6_k`
17. `zai-org/glm-4.6v-flash@q6_k`

> Hinweis: `intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround@q2_k` hatte anfangs einen
> `sampling:`-Block (Platzhalter), wurde aber entfernt: keine recherchierten Werte in
> `MODEL_CATEGORY_SAMPLING` → Fallback (Thinking-Defaults 0.6/0.95 im --thinking-Lauf) ist korrekt.

Die übrigen 30 Modelle bleiben bewusst ohne `sampling:` (Fallback greift).

## D. Test-Strategie

- **Regression:** Lese-Logik (`get_model_config`) muss `sampling:` aus der Registry lesen, wenn vorhanden; Fallback zu Defaults, wenn Felder fehlen.
- **Funktional:** YAML valide (`yaml.safe_load` = 47 Einträge, keine ParserError); `validate` ohne neue Probleme.
- **End-to-End:** `consolidate_results.py` liefert Triple-Keys korrekt (bereits verifiziert).

## E. Governance / Logging

- Migration-Log: `doc-git/Planung/registry_sampling_log.md` — protokolliert jede Änderung (Was, Warum, betroffene Modelle).
- CHANGELOG.md: Eintrag „Registry Sampling (SSOT) – Plan & Migration" bei Abschluss von Schritt 4–7.

## F. Rollout-Plan

- [x] **Phase 0 (Pilot):** 4 Modelle einzeln migriert + getestet (ernie, gemma-4-12b, kimi-linear, qwen3.6-27b-i1).
- [x] **Phase 1 (Rest):** 14 weitere Modelle gebündelt migriert (Skript), YAML-Reparatur (Indent-Fix), Validierung grün.
- [x] **Phase 2 (Vollständige Umstellung):** Lesepfade (Schritt 4), `MODEL_CATEGORY_SAMPLING` bleibt als Fallback (Schritt 5), Registry-`sampling:`-Werte = recherchierte Empfehlungen, Reader-End-to-End verifiziert.

## G. HowTo: Sampling-Werte ergänzen

Einem Modell recherchierte Sampling-Parameter geben (SSOT = Registry):

1. Recherchierte Werte eintragen (z.B. in `Temperature Recommondations_en.md` dokumentieren).
2. In `doc-git/model_registry.yaml` nach der `arch:`-Zeile des Modell-Blocks einfügen:
   ```yaml
   sampling:
     coding:
       temperature: 0.6
       top_p: 0.95
     knowledge:        # identische Struktur
     agentic:          # identische Struktur
     math:             # identische Struktur
     thinking:
       enabled: false
       temperature: 0.6
       top_p: 0.95
   ```
   - Nur Kategorien mit recherchiertem Wert aufnehmen; fehlende Kategorien fallen auf
     `MODEL_CATEGORY_SAMPLING`/Kategorie-Defaults zurück.
   - `top_k`/`min_p`/`enable_thinking` bleiben in der LMS-JSON (Reader liest sie nicht aus der Registry).
3. Verifizieren: `python src/registry_tool.py validate` (keine neuen Probleme), Tests
   (`python -m pytest tests/test_benchmark_config.py -q`).
4. Migration-Log-Eintrag ergänzen (`doc-git/Planung/registry_sampling_log.md`).
