# Lint-Issues (ruff check . --no-fix)

Erzeugt: 2026-08-11 11:42:08

3 Probleme, Exit-Code 1

F841 Local variable `cfg_np` is assigned to but never used
    --> src\registry_tool.py:2329:9
     |
2328 |         cfg_ctx = load_fields.get("llm.load.contextLength")
2329 |         cfg_np = load_fields.get("llm.load.numParallelSessions")
     |         ^^^^^^
2330 |         cfg_ukv = load_fields.get("llm.load.useUnifiedKvCache")
2331 |         cfg_offload = load_fields.get("llm.load.llama.acceleration.offloadRatio")
     |
help: Remove assignment to unused variable `cfg_np`

F841 Local variable `cfg_ukv` is assigned to but never used
    --> src\registry_tool.py:2330:9
     |
2328 |         cfg_ctx = load_fields.get("llm.load.contextLength")
2329 |         cfg_np = load_fields.get("llm.load.numParallelSessions")
2330 |         cfg_ukv = load_fields.get("llm.load.useUnifiedKvCache")
     |         ^^^^^^^
2331 |         cfg_offload = load_fields.get("llm.load.llama.acceleration.offloadRatio")
     |
help: Remove assignment to unused variable `cfg_ukv`

F841 Local variable `cfg_offload` is assigned to but never used
    --> src\registry_tool.py:2331:9
     |
2329 |         cfg_np = load_fields.get("llm.load.numParallelSessions")
2330 |         cfg_ukv = load_fields.get("llm.load.useUnifiedKvCache")
2331 |         cfg_offload = load_fields.get("llm.load.llama.acceleration.offloadRatio")
     |         ^^^^^^^^^^^
2332 |
2333 |         # context_length: Config-Wert kleiner als Registry-Erwartung ÔåÆ Altlast?
     |
help: Remove assignment to unused variable `cfg_offload`

Found 3 errors.
No fixes available (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

