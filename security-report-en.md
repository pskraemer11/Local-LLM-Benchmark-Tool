# Security Review: Benchmarks

## Scope

Repository-wide standard source audit of the current Benchmarks worktree, with focused review of executable Python, local HTTP proxy behavior, subprocess boundaries, configuration loaders, registry maintenance, tests, and CI configuration.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_3f0254c7ba99525d33ea81dc54c1fcb3ac8bc25f4988ed6597ae02d0e3fce0c1
- Revision: 52adeba68549f918cfa7305ff52e3ba9849adef5
- Snapshot digest: codex-security-snapshot/v1:sha256:869f042feba38fed85c16e02ff0caf4bd977dc9785c24fc895d3e5b04324197c
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: Not executed; offline source review only.
- Artifacts reviewed: src/custom_benchmark.py, src/tools/lmeval_proxy.py, src/model_manager.py, src/run_benchmarks.py, src/registry_tool.py, src/benchmark_config.py, src/assemble_blueprint.py, src/evalplus_subset_eval.py, src/consolidate_results.py, src/csv_writer.py, src/tools/parallel_ab.py, src/tools/correlation_export.py, src/tools/gguf_full_metadata_reader.py, src/tools/tool_eval_bench_runner.py, pyproject.toml, .github/workflows/ci.yml, .github/workflows/review.yml

Limitations and exclusions:
- No runtime or network reproduction was performed.
- Legacy archive, generated result, cache, and large fixture/document trees were not exhaustively reviewed line by line.
- The optional proxy's effective upstream authentication and deployment bind address require deployment confirmation.
- Excluded Archiv/\*\*: Legacy archived code was not part of the active runtime surface.
- Excluded backups/\*\*: Backup copies are not active runtime code.
- Excluded Doku-intern/\*\*: Internal notes and generated working material are not runtime code.
- Excluded ergebnisse/\*\*: Generated benchmark outputs are data artifacts, not executable product source.
- Excluded logs/\*\*: Runtime logs were excluded from source review.
- Excluded runs/\*\*: Run outputs and transient data were excluded from source review.

### Scan Summary

| Field | Value |
| --- | --- |
| Reportable findings | 2 |
| Severity mix | high: 1, medium: 1 |
| Confidence mix | high: 1, medium: 1 |
| Coverage | partial |
| Validation mode | Parent-led static validation with local ripgrep and Ruff security-pattern audit; delegation workers unavailable. |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

A local benchmark operator runs model-driven evaluation code and an optional LM-Eval HTTP proxy against local LM Studio or TabbyAPI services. Security depends on keeping model-generated code contained, keeping local model-management APIs private, and preventing untrusted repository/configuration data from crossing into filesystem, process, or network operations.

### Assets

- The benchmark host user's filesystem and process credentials
- Local model-serving endpoints and loaded model state
- Benchmark results and model configuration files
- GPU/CPU resources and service availability

### Trust Boundaries

- Model/API response content entering the code extraction and execution pipeline
- HTTP clients reaching the optional LM-Eval proxy
- Repository datasets, YAML/JSON configuration, and environment variables consumed by the tools
- Benchmark subprocesses and local LM Studio/TabbyAPI services

### Attacker Capabilities

- Supply or influence model output when a model or upstream response is untrusted or compromised
- Reach the proxy over the configured bind interface when it is bound beyond loopback
- Provide malformed benchmark/API input within the supported local execution workflow

### Security Objectives

- Prevent model-generated or benchmark-controlled code from escaping its execution boundary
- Require authorization before exposing inference or model-management operations
- Avoid uncontrolled resource consumption and preserve host/service availability
- Keep local configuration and benchmark artifacts within their intended trust boundaries

### Assumptions

- The default LM Studio and proxy deployments are intended for a single local operator.
- No network or runtime exploit reproduction was performed; conclusions are based on current source.
- The repository contains no SECURITY.md policy overriding these assumptions.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [Model-generated Python can escape the restricted sandbox](#finding-1) | high | high | inline below |
| [Configurable proxy bind exposes unauthenticated LM Studio operations](#finding-2) | medium | medium | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Model-generated Python can escape the restricted sandbox

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | high |
| Confidence rationale | The source directly connects streamed model content to code extraction and sandbox execution, and the import hook's allow-by-default behavior leaves a known builtins-recovery route. |
| Category | sandbox-escape |
| CWE | CWE-94, CWE-693 |
| Affected lines | src/custom_benchmark.py:1193-1200, src/custom_benchmark.py:1232-1239, src/custom_benchmark.py:1300-1305, src/custom_benchmark.py:1809-1820 |

#### Summary

The custom benchmark executes model-generated Python in a subprocess with a filtered builtins dictionary, but its replacement import hook permits non-blocked modules such as warnings. That module exposes the interpreter's real builtins, allowing generated code to recover imports and execute host-level operations.

#### Root Cause

The sandbox relies on a denylist import hook and Python namespace filtering rather than an OS-level isolation boundary. Because the hook allows modules outside the list, generated code can recover interpreter capabilities through permitted runtime modules.

#### Validation

The source directly connects streamed model content to code extraction and sandbox execution, and the import hook's allow-by-default behavior leaves a known builtins-recovery route. Validation details were not recorded separately.

Validation method: Static source trace from model response ingestion through code extraction into the generated sandbox script, followed by review of the import policy and subprocess boundary.

Evidence:
- src/custom_benchmark.py:1809-1820 maps model response content into evaluate_code().
- src/custom_benchmark.py:1232-1239 delegates imports not present in the denylist.
- src/custom_benchmark.py:1300-1305 runs the script with the host user's environment and interpreter.

#### Dataflow

The canonical finding records the affected path at src/custom_benchmark.py:1193-1200, src/custom_benchmark.py:1232-1239, src/custom_benchmark.py:1300-1305, src/custom_benchmark.py:1809-1820, but no expanded source-to-sink narrative was recorded.

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

#### Severity

**High** — A malicious or compromised model response can cross the intended code-execution boundary and run with the benchmark user's host privileges. The attacker must influence model output or the evaluated task, so likelihood is lower than a remotely exposed endpoint.

Applies whenever model output or benchmark code is not fully trusted and the custom pipeline evaluates it.

#### Remediation

Do not treat Python namespace filtering as a security sandbox. Execute generated code in a separately isolated worker with OS/container or Windows job/restricted-token controls, a minimal environment, no host filesystem/network access, and explicit resource limits. If an in-process policy remains, use a strict allowlist of immutable operations and treat it as correctness filtering only.

Tests:
- Add a regression test proving generated code cannot import any capability that recovers real builtins or reaches filesystem/process/network APIs.
- Run a Windows integration test in the hardened worker and verify filesystem, process creation, network, and environment access are denied.
- Verify timeout, memory, CPU, and child-process limits are enforced outside the Python interpreter.

Preventive controls:
- Treat all model outputs as untrusted code.
- Use a deny-by-default execution policy only as a secondary control.
- Keep secrets out of the sandbox process environment.

<a id="finding-2"></a>

### [2] Configurable proxy bind exposes unauthenticated LM Studio operations

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | The proxy's missing authentication and arbitrary POST forwarding are direct; actual impact depends on the upstream service's authentication and the chosen deployment bind address. |
| Category | missing-authentication |
| CWE | CWE-306, CWE-284 |
| Affected lines | src/tools/lmeval_proxy.py:88-98, src/tools/lmeval_proxy.py:185-199, src/tools/lmeval_proxy.py:175-180, src/model_manager.py:671-693 |

#### Summary

The optional LM-Eval proxy permits an arbitrary bind address, adds no authentication, forwards every non-chat POST path to the configured upstream, and returns wildcard CORS headers. A non-loopback deployment can therefore expose local inference and model-management operations to unauthenticated network clients.

#### Root Cause

The proxy treats interface selection as the operator's responsibility but does not pair non-loopback binding with authentication, a path allowlist, or a protected upstream connection.

#### Validation

The proxy's missing authentication and arbitrary POST forwarding are direct; actual impact depends on the upstream service's authentication and the chosen deployment bind address. Validation details were not recorded separately.

Validation method: Static review of proxy routing, listener configuration, response headers, and the model-management API paths used by the project.

Evidence:
- src/tools/lmeval_proxy.py:191-199 accepts any bind address.
- src/tools/lmeval_proxy.py:93-98 forwards all non-chat POST paths.
- src/model_manager.py:692-693 documents and calls POST /api/v1/models/load.

#### Dataflow

The canonical finding records the affected path at src/tools/lmeval_proxy.py:88-98, src/tools/lmeval_proxy.py:185-199, src/tools/lmeval_proxy.py:175-180, src/model_manager.py:671-693, but no expanded source-to-sink narrative was recorded.

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

#### Severity

**Medium** — The default bind is loopback, but an operator can select a non-loopback interface. Under that deployment condition, the proxy crosses the local-only trust boundary and forwards sensitive upstream operations.

Applies when tools/lmeval_proxy.py is launched with a non-loopback --bind or otherwise exposed through a network-facing listener.

#### Remediation

Keep the listener loopback-only by default and reject non-loopback binds unless an explicit authentication mode is configured. Restrict routing to the two required endpoints, remove wildcard CORS or use an allowlist, enforce bounded Content-Length and request timeouts, and require authenticated upstream calls for any management-capable endpoint.

Tests:
- Reject --bind values other than loopback unless an auth configuration is supplied.
- Verify unknown POST paths return 404 and never reach the upstream.
- Verify requests without valid credentials are rejected before forwarding.
- Verify oversized Content-Length values are rejected before reading the request body.

Preventive controls:
- Treat LM Studio and TabbyAPI management APIs as privileged local services.
- Document the security boundary for any non-loopback deployment.
- Add an integration test covering CORS and authorization behavior.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Model response parsing and generated-code execution | sandbox-escape | Reported | Reviewed custom_benchmark.py response-to-evaluator flow and sandbox construction. |
| LM Studio and TabbyAPI local model-management boundary | privileged-local-service | No issue found | Reviewed CLI arguments use list-form subprocess calls and model identifiers are validated; proxy exposure is reported separately. |
| Optional LM-Eval HTTP proxy | missing-authentication | Reported | Reviewed bind configuration, request routing, upstream forwarding, and CORS behavior. |
| Registry, JSON/YAML configuration, and filesystem maintenance | configuration-integrity | No issue found | Reviewed parsing, model-key validation, path construction, and destructive command confirmation. |
| Benchmark subprocesses and result/output generation | resource-isolation | Needs follow-up | No additional reportable issue established; resource limits and dependency behavior were not runtime-tested. |

## Open Questions And Follow Up

- Does the deployed LM Studio or TabbyAPI instance require authentication on the upstream endpoint?
- Is the optional proxy ever intentionally bound to a non-loopback interface in production or a shared lab network?
- Large datasets, binary/document artifacts, and excluded legacy/generated trees were not exhaustively reviewed line by line.
  - Follow-up prompt: Review deferred unit deferred-nonruntime-artifacts and close its stated proof gap. Paths: data/, ds1000_official/, human_eval/, human_eval_plus/, simple_evals/, tests/data/, tests/fixtures/. Surfaces: benchmark-data, legacy-and-generated-artifacts.
