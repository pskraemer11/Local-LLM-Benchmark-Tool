# Langzeit-Planung & offene Punkte

Stand: 2026-08-06. Legende: [ ] offen, [~] in Arbeit, [x] erledigt/geprüft.

## Aktive Punkte

- [x] **1. Planung.md anlegen** — erledigt 05.08., wird laufend gepflegt.
- [x] **2. `Parallel-Slots-Optimization_en.md` überarbeiten** — erledigt 05.08.: veraltete Dense=np=1-Tabelle als historisch markiert, neue Regeln (04.08.) eingearbeitet, Recommendation-Sektion auf Priority-Algorithmus aktualisiert.
- [x] **3. CI-Failures auf GitHub fixen** — geprüft 05.08.: alle 5 letzten Runs `success` (inkl. `a73c15b2`); ruff mit CI-Flags (`--select E,F`) lokal grün. Kein Handlungsbedarf.
- [x] **4. `fill-arch` soll `max_context_length` aus GGUF lesen** — bereits implementiert: `cmd_fill_arch` in `src/registry_tool.py:1329-1438`, füllt `max_context_length` aus GGUF-Header wenn `None` (Z. 1382-1396, via `_read_gguf_arch` 4-Tupel `(block_count, embedding_length, is_reasoning, context_length)`). Erledigt durch Fix vom 05.08. 08:20.
- [x] **5. Fallback `max_context_length: None`** — keine 8192-Stelle mehr gefunden; `cmd_suggest`/`_compute_np_ukv` (`src/registry_tool.py:810-844`) nutzen `entry.get("max_context_length") or 262144`, `MIN_CONTEXT_LENGTH = 32768` (`src/benchmark_config.py:563`). Fallback 256k ist deutlich über der geforderten 16k-Untergrenze.
- [x] **6. `thinking-config_en.md` aktualisieren** — erledigt 05.08.: Priority-Chain auf 05.08.-Stand korrigiert (LMS-JSON-Config ist EINZIGE Quelle, `MODEL_TEMP_OVERRIDES`/Knowledge-Floor entfernt), Current-Patterns-Tabelle, `--thinking`-Tabelle (Keyword-Matching via REASONING_PATTERNS), Konfigurations-Flow und History aktualisiert.
- [x] **7. Native `max_token_length` klären** — Registry-Werte sind korrekt und decken sich mit LMS GUI: `noctrex/lfm2-24b-a2b_moe` → max 128000 (**128k Token**, nicht 128), `mradermacher/gemma-4-26b-a4b-it-i1` → max 262144 (**262k Token**, nicht 262!). Korrektur des Nutzers vom 05.08. übernommen.
- [x] **8. Reale Benchmarks laufen mit 1 Slot statt 4** — **GEFIXT + VERIFIZIERT (05.08.):** ZWEI Pipeline-Fehler, nicht der Load:
  1. **`run_evalplus()`** (run_benchmarks.py:1038): hatte keinen `num_parallel`-Parameter, evalplus `codegen()` sendet strikt sequenziell (ThreadPool max_workers=1). **Fix:** `num_parallel` durchgereicht (Aufruf Z. 1988) + eigene parallele Codegen-Schleife mit `ThreadPoolExecutor(max_workers=num_parallel)`, identisches JSONL-Format (sanitized+raw) pro Task unter Write-Lock.
  2. **`lmeval_proxy.py`**: nutzte `HTTPServer` (synchron, 1 Request gleichzeitig) → lm_eval `num_concurrent>1` wurde am Proxy serialisiert. **Fix:** `ThreadingHTTPServer`.
  - **Testlauf-Verifikation (05.08., Rnj 1@Q8_0 + ERNIE-4.5-21B-A3B-PT, HumanEval+/HellaSwag/DS1000 SS=20 np=4):** evalplus lief mit 4 Parallel-Workern, DS1000-Custom weiterhin 4 Worker. HellaSwag fiel im ersten Lauf aus (lm_eval `NameError: TCPConnector` — aiohttp zu alt für Python 3.14, nutzt entferntes `cgi`).
  - **lm_eval-TCPConnector-Fix (05.08.):** `pip install --upgrade aiohttp` → 3.14.3. **HellaSwag-Verifikationslauf erfolgreich:** 100 Tasks in 149s, Score 0.34 (Rnj 1). **Slot-Beweis aus Server-Log 19:38-19:41: Slots 0/1/2/3 aktiv (12/12/8/6 Events)** — vor dem Fix: alle 384 Requests auf Slot 3. Damit sind ALLE 3 Pipeline-Arten parallelisiert und verifiziert: evalplus (ThreadPool), lmeval (ThreadingHTTPServer + aiohttp), custom (war schon ThreadPool).
  - **ERNIE-Fallstudie (Beleg für VRAM>np-Ranking):** ERNIE IQ4_NL lief 934s/20 Tasks (ctx=131k + UKV=False → 15,5 GB VRAM + 7,3 GB Shared-RAM → PCIe-Paging). Nach GUI-Neustart ctx=32k + UKV=True: 13,3 GB VRAM, 0 GB Shared, **5-10× schneller**. Damit ist die alte ERNIE-np=1-Hypothese (Shared-Experts/CUDA-Kernels) **WIDERLEGT** — Ursache war VRAM-Überlauf, nicht Architektur. MXFP4-Variante separat langsam (605s) — vermutlich MXFP4-Slow-Path, nicht KV/ctx-bedingt.
  - Verifikation: 717/717 Tests grün, py_compile OK. **Punkt 8 abgeschlossen.**
- [x] **9. Quarantäne-Ordner** — 137 Waisen-Configs in `~\.lmstudio\.internal\user-concrete-model-default-config\_quarantine_orphans_20260805\`; Entscheid 05.08.: Quarantäne dauerhaft als Papierkorb behalten (kein Löschen). Abgeschlossen durch Entscheid.

## 06.08.2026 – Registry-Validierung, README, Help-Text

- [x] **10. Registry-Validierung auf 0 Probleme** — Commits `0eca0867`, `d2cc53f7`, `1ec72067`: 48 Registry-`context_length` gecleart + sync-ctx, 8 Configs auf 32768 angehoben, `gemma-4-12b-it-qat` UKV-Drift behoben, `unsloth/phi-4` + `mradermacher/deepseek-coder-33b-instruct` auf natives GGUF-Limit 16384 gecappt, fehlende promptTemplate-Felder ergänzt. Validierungslogik in `src/registry_tool.py` korrigiert: nur noch `cfg_ctx > max_ctx` und `cfg_ctx <= 0` — KEINE arithmetischen Minimums (8192/32768); Nutzer: "Es gibt kein so definiertes Minimum!" Kleine max_ctx-Modelle (<16k) sind nur Embedding/RAG/RIG/Math und gehören auf die Blacklist.
- [x] **11. README.md aktualisiert** — Commit `166b5cf7`, 7 Punkte: (1) Thinking-Support generell für alle Pipelines, (2) Stratified Subsamping breiter (DS1000, CoderEval, andere), (3) Quickstart auf `qwen3-30b-a3b-instruct --thinking` (Gemma-4 ist immer im Thinking-Mode), (4) dev-Deps komplett, (5) `--num-parallel` in CLI-Tabelle, (6) Registry-Tool-Abschnitt mit echten Commands + Prinzip (05.08.), (7) neuer Abschnitt "Consolidate Results (src/consolidate_results.py)". Dabei CLI-Tabelle mit echter `--help`-Ausgabe abgeglichen: `--bootstrap`, `--non-interactive`, `--output-dir` existieren **nicht** als Flags (Quickstart-Aufruf `consolidate_results.py --bootstrap` hätte gecrasht), doppelte `--unload-between`-Zeile entfernt; Bootstrap-CIs laufen automatisch, paired nur via `--compare`.
- [x] **12. Thinking-Help-Text auf "all pipelines"** — Commit `7a8ac4d7`: 3 Stellen in `src/run_benchmarks.py` (CLI-Help Z. 1756, Kommentar Z. 753, Summary-Print Z. 1838).
- [x] **13. Unbegründete ResourceExhausted-Änderungen zurückgenommen** — `src/custom_benchmark.py` + `src/tools/lmeval_proxy.py` via `git checkout`; die 502/ResourceExhausted-Fehler kamen vom NVIDIA-Provider (Nemotron 3 Ultra Free), nicht vom Benchmark-Code.
- [x] **14. Aufgeräumt (Git-Unreinheiten)** — 4 ungetrackte `logs_3098*.zip` + `src/utils/modeling_gguf_pytorch_utils.py.lnk` gelöscht; `logs/` bleibt über `.gitignore` abgedeckt.
- [x] **15. Manual-Corrections-Tabelle + VRAM-Regel** — in `doc-git/Model-Parameters-and-Benchmarks_en.md` (05.08.): Manuelle Overrides (np/UKV/ctx) + General rule: ≥12 GB Modellgröße ⇒ UKV=true bei np=4 (16 GB GPU). VRAM-Regel auch in README.md (06.08., Commit `888b22a0`).

## Offen

- [ ] **16. Top-Candidates-Tabelle aktualisieren** — nach dem laufenden SS=30/np=4-Lauf (seit ~05.08., Bugfixes: Parallelisierung evalplus + lmeval, aiohttp 3.14.3): Tabellenwerte in `doc-git/Model-Parameters-and-Benchmarks_en.md` aus dem neuen Konsolidierungs-ODS neu erzeugen (Scores + Effizienz ändern sich durch schnellere Laufzeiten). Vorher (06.08.) bereinigt: veralteter SS=4-Hinweis (12.07., nicht aussagekräftig) entfernt, Quellenangabe `konsolidiert_15 Modelle, SampleSize 100, seit 20260711_20260803_172150.ods` verifiziert — Tabelle stammt aus dem SS=100-Lauf 11.07.–03.08. **Danach comitten** (inkl. Manual-Corrections-Tabelle 05.08. + SS=4-Entfernung, aktuell uncommittet in `Model-Parameters-and-Benchmarks_en.md`).
- [ ] **17. Zentrales Alias-Map für Modellfamilien-Namen** — Idee aus Sichtung von transformers `modeling_gguf_pytorch_utils.py` (06.08.): eine zentrale Tabelle für Namens-Aliasse (HF-model_type ↔ GGUF-arch ↔ Registry-arch, z. B. `gpt-oss-20b` → `gpt_oss`, `qwen2_moe` → `qwen2moe`, `minimax_m2` → `minimax-m2`) statt verstreuter Regexes (`-(ud|qat|imatrix)`-Suffixe, `@quant`-Strips, Arch-Substring-Erkennung). Anwendungsorte: `normalize_model_name`/`_normalize_lms_model_name` + `_ARCH_REASONING_MAP` + `GGUF_TO_TRANSFORMERS_MAPPING`-Analogon. Reine Struktur-Verbesserung (Robustheit), kein Funktionsgewinn — aufschiebbar.
- [ ] **18. qwen3.5-9b: Reasoning-Einstufung vs. Hub klären** — gefunden durch neuen `validate --repro`-Hub-Check (06.08.): Registry sagt `reasoning: instruct` (`model_registry.yaml:1232`), Hub-model.yaml sagt `reasoning: true` + `enableThinking`-Toggle mit `defaultValue: true` (Thinking standardmäßig AN; Quelle `C:\Users\pskra\.lmstudio\hub\models\qwen\qwen3.5-9b\model.yaml`). Zusätzlich:
  - **Gilt für ALLE Qwen 3.5/3.6-Modelle** (Nutzer-Bestätigung 06.08.): Dual-Mode, Thinking per Toggle steuerbar, steht so auf der Qwen-Model-Card.
  - **Registry ist intern inkonsistent**: alle anderen Qwen3.5/3.6-Einträge (`Qwen/Qwen3.5-9B-GGUF@q6_k`, `unsloth/qwen3.6-27b`, `-mtp`, `mradermacher/qwen3.6-27b-i1`, `qwen3.6-28b-reap-i1@iq3_s/@q3_k_s`) haben `reasoning: thinking` — nur `qwen/qwen3.5-9b` hat `instruct` (gleiche file_size_bytes 8281142495 wie die @q6_k-Variante).
  - `max_context_length` fehlt im Eintrag (Hub: 262144) — obwohl `fill-arch` das laut Planungspunkt 4 auffüllen sollte.
  - Code-Kommentar `assemble_blueprint.py:248-249` („Qwen3.6 Default Non-Thinking, enable_thinking=False Default") widerspricht der Hub-model.yaml (`defaultValue: true`).
  - Pipeline-Wirkung (`custom_benchmark.py:907-909`): bei `is_thinking_enabled=False` wird `enable_thinking: False` explizit gesendet → qwen3.5-9b-Benchmark-Ergebnisse (falls gelaufen) wären ohne Thinking erzeugt, obwohl das Modell thinking-fähig ist.
  - **Zu klären:** (a) `qwen/qwen3.5-9b` auf `reasoning: thinking` angleichen (Konsistenz mit @q6_k-Variante + Hub) oder Abweichung begründen + im Review dokumentieren; (b) `max_context_length` nachtragen; (c) Kommentar in `assemble_blueprint.py` verifizieren/korrigieren; (d) `enable_thinking`-Handling für qwen35-Modelle in `benchmark_config.py` prüfen.

## Bewusst NICHT enthalten (Entscheid 02.08., Code-Review §5)

- P2-Judge als zweiter Scoring-Instanz.
- `temperatura`/`top_p`-Overrides in der Run-Spec (bleiben auf Standard).

## Abschluss-Registry-Bereinigung (05.08., committed `a73c15b2`)

- 3 Waisen-Keys entfernt (kein GGUF mehr): `intel/qwen3-8b-q4km-autoround-inc-v1`, `prism-ml/bonsai-27b`, `prism-ml/bonsai-27b@q1_0`.
- 9 Einträge: `context_length` auf `max_context_length` gecappt (rnj-1, phi-4, falcon3-10b, mellum2 ×2, nerdsking-python-coder-7b, internlm2_5-20b, bonsai-8b, granite-4.1-8b).
- Registry: 70 Einträge, 0 Inkonsistenzen, Tests 717/717 grün.
