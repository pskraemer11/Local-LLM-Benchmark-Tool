# Hardening Context

## Source scan

- Scan ID: `c6fef5c3-f885-4cfb-afd0-b53a34cda5cf`
- Manifest SHA-256: `56e0ca675bb503af0f3a05e796f7accbeaf2d34aadd1ad64c4903129000c9b66`
- Target revision: `bd69619758aaac35358713a50cee566b78d40917`
- Snapshot: `codex-security-snapshot/v1:sha256:53183da47073825a204c56454677bb389f175a0d0b79fb04237212a8893a7f92`
- Archived scan artifacts: [`security-scan/report.md`](security-scan/report.md), including `findings.json`, `coverage.json`, `scan-manifest.json`, and `exports/results.sarif`.
- Scan coverage: partial; 153 files fully reviewed, remainder keyword-reviewed.
- Source drift: unknown. The worktree was already dirty when the scan ran.

## Evidence registry

| ID | Human-readable evidence | What it establishes |
| --- | --- | --- |
| `csf_57dcc81118eb3aba784ea723` | Generated-code sandbox can escape through allowlisted native-loader APIs | `numpy` and other native-capable packages are exposed to `exec()` code without a filesystem/native capability boundary. |
| `csf_93aa4dc792063d79c336499b` | LM-Eval proxy leaves request, response, buffering, and concurrency resources unbounded | The proxy has no bounded body/response/SSE/concurrency policy. |
| `csf_3b9d51bdd18255fa689920a9` | Windows EvalPlus execution disables memory enforcement for generated solutions | Windows sets `EVALPLUS_MAX_MEMORY_BYTES=-1` and replaces signal timers with no-ops; only an outer wall-clock timeout remains. |

## Relevant source anchors

- `src/sandbox_worker.py:31-139` — import allowlist, AST/builtin filtering, and `exec()`.
- `src/custom_benchmark.py:1224-1281` — temporary working directory and Windows Job Object for the custom worker.
- `src/evalplus_subset_eval.py:27-56,115-145` — disabled memory/timer controls and generated-solution evaluation.
- `src/tools/lmeval_proxy.py:38-74,124-199` — unbounded reads/buffering, threaded listener, configurable bind.
- `src/run_benchmarks.py:346-357,2162-2166,2200-2205` — proxy startup, incomplete exit cleanup, normal-path shutdown.

## Constraints and assumptions

- Windows compatibility is non-negotiable; POSIX-only signal or fork solutions are not acceptable as the primary fix.
- No latency, throughput, or memory budget was supplied. Performance effects are therefore hypotheses until benchmarked.
- The normal launcher uses loopback for the proxy; external binding is an operator-selected deployment mode.
- The plan is design guidance only. No source finding is considered fixed until the original paths are revalidated after implementation.
