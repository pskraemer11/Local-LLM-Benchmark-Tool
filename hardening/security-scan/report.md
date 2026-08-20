# Security Review: Benchmarks

## Scope

Repository-wide offline static security audit of the dirty Benchmarks Git worktree.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_3f0254c7ba99525d33ea81dc54c1fcb3ac8bc25f4988ed6597ae02d0e3fce0c1
- Revision: bd69619758aaac35358713a50cee566b78d40917
- Snapshot digest: codex-security-snapshot/v1:sha256:53183da47073825a204c56454677bb389f175a0d0b79fb04237212a8893a7f92
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: read-only static review
- Artifacts reviewed: src, tests, lm_eval_tasks, scripts, run specifications, repository configuration

Limitations and exclusions:
- No SECURITY.md was present.
- No application code, network, or external dependencies were executed or fetched.
- The workbench inventory reported 155 files; source review fully covered 153 and keyword-reviewed the remainder.

### Scan Summary

| Field | Value |
| --- | --- |
| Reportable findings | 7 |
| Severity mix | high: 1, medium: 2, low: 4 |
| Confidence mix | high: 7 |
| Coverage | partial |
| Validation mode | source-backed independent baseline and focused investigations |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Attackers may influence model-generated benchmark code, task fixtures, local registry/configuration data, or network clients when optional listeners/endpoints are exposed. Protected assets include the benchmark user's files, credentials, inference resources, and model/server lifecycle state.

### Assets

- host filesystem and native process capabilities
- API bearer credentials and inference payloads
- local inference resources and lifecycle state
- registry and LM Studio model/config files

### Trust Boundaries

- generated code to sandbox worker
- CLI/environment configuration to subprocess and HTTP clients
- proxy clients to local upstream APIs
- registry keys/configuration to destructive filesystem operations

### Attacker Capabilities

- influence benchmark code/tasks
- provide malicious local registry/configuration data
- reach a proxy if exposed beyond loopback
- observe traffic on configured remote HTTP

### Security Objectives

- confine generated code
- enforce resource bounds
- authenticate/protect proxy/provider traffic
- contain destructive filesystem operations
- clean up child processes

### Assumptions

- Default endpoints and proxy binding are loopback-only.
- Repository contents and environment variables are treated as untrusted analysis inputs.
- External dependency internals were not fetched or executed.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [Generated-code sandbox can escape through allowlisted native-loader APIs](#finding-1) | high | high | inline below |
| [LM-Eval proxy leaves request, response, buffering, and concurrency resources unbounded](#finding-2) | medium | high | inline below |
| [Windows EvalPlus execution disables memory enforcement for generated solutions](#finding-3) | medium | high | inline below |
| [Configured bearer credentials can be sent over unencrypted HTTP](#finding-4) | low | high | inline below |
| [Registry model keys can escape deletion roots](#finding-5) | low | high | inline below |
| [LM-Eval proxy can survive abnormal launcher termination](#finding-6) | low | high | inline below |
| [Optional non-loopback binding exposes an unauthenticated model proxy](#finding-7) | low | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Generated-code sandbox can escape through allowlisted native-loader APIs

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | high |
| Confidence rationale | Two independent audits identified the same control failure and the source directly shows the relevant boundary. |
| Category | sandbox-escape |
| CWE | CWE-693 |
| Affected lines | src/sandbox_worker.py:31-46, src/sandbox_worker.py:71-100, src/sandbox_worker.py:103-139, src/custom_benchmark.py:1224-1281, src/windows_job_object.py:104-123 |

#### Summary

The benchmark executes attacker-influenced Python with exec() while allowing NumPy and other native-capable libraries whose public APIs can reach host files or native code.

#### Root Cause

Generated evaluation code must remain inside a narrow scientific API, but the allowlist and AST checks do not constrain capabilities exposed by allowed packages and the OS control is resource-only.

**sandbox-allowlist** — `src/sandbox_worker.py:31-38`

General-purpose scientific packages are exposed instead of a narrow wrapper API.

```python
SANDBOX_ALLOWED_MODULES = frozenset({... "numpy", ... "PIL", ... "scipy", ...})
```

**sandbox-import** — `src/sandbox_worker.py:71-100`

Permitted top-level packages can expose submodules and public native/file APIs.

```python
top_level = name.split(".", 1)[0]
if top_level not in SANDBOX_ALLOWED_MODULES: raise ImportError(...)
```

**sandbox-exec** — `src/sandbox_worker.py:103-139`

Model/task code and tests reach Python execution after filtering.

```python
exec(code, namespace, namespace)
...
exec(test, namespace, namespace)
```

**sandbox-job** — `src/custom_benchmark.py:1236-1249`

The Job Object limits resources but does not deny filesystem, native, or network capabilities.

```python
job = WindowsJobObject(SANDBOX_MEMORY_LIMIT_BYTES)
job.assign(process)
```

#### Validation

A caller-controlled code path reaches exec(), a permissive top-level allowlist, and no filesystem/network isolation. Temporary cwd and Job Object controls do not close that capability boundary.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**sandbox-allowlist** — `src/sandbox_worker.py:31-38`

General-purpose scientific packages are exposed instead of a narrow wrapper API.

```python
SANDBOX_ALLOWED_MODULES = frozenset({... "numpy", ... "PIL", ... "scipy", ...})
```

**sandbox-import** — `src/sandbox_worker.py:71-100`

Permitted top-level packages can expose submodules and public native/file APIs.

```python
top_level = name.split(".", 1)[0]
if top_level not in SANDBOX_ALLOWED_MODULES: raise ImportError(...)
```

**sandbox-exec** — `src/sandbox_worker.py:103-139`

Model/task code and tests reach Python execution after filtering.

```python
exec(code, namespace, namespace)
...
exec(test, namespace, namespace)
```

**sandbox-job** — `src/custom_benchmark.py:1236-1249`

The Job Object limits resources but does not deny filesystem, native, or network capabilities.

```python
job = WindowsJobObject(SANDBOX_MEMORY_LIMIT_BYTES)
job.assign(process)
```

#### Dataflow

Generated solution/test -\> sandbox request -\> safe_import/AST checks -\> exec() -\> allowed scientific library API -\> host capability.

**sandbox-allowlist** — `src/sandbox_worker.py:31-38`

General-purpose scientific packages are exposed instead of a narrow wrapper API.

```python
SANDBOX_ALLOWED_MODULES = frozenset({... "numpy", ... "PIL", ... "scipy", ...})
```

**sandbox-import** — `src/sandbox_worker.py:71-100`

Permitted top-level packages can expose submodules and public native/file APIs.

```python
top_level = name.split(".", 1)[0]
if top_level not in SANDBOX_ALLOWED_MODULES: raise ImportError(...)
```

**sandbox-exec** — `src/sandbox_worker.py:103-139`

Model/task code and tests reach Python execution after filtering.

```python
exec(code, namespace, namespace)
...
exec(test, namespace, namespace)
```

**sandbox-job** — `src/custom_benchmark.py:1236-1249`

The Job Object limits resources but does not deny filesystem, native, or network capabilities.

```python
job = WindowsJobObject(SANDBOX_MEMORY_LIMIT_BYTES)
job.assign(process)
```

#### Reachability

Any actor who can influence benchmark-generated or task-provided code can trigger the path during a custom benchmark run.

#### Severity

**High** — The import allowlist, exec boundary, and absence of OS-level filesystem/network isolation establish a capability escape.

A stronger OS isolation boundary or a narrow wrapped scientific API would lower the severity.

#### Remediation

Do not expose general-purpose native-capable packages directly to hostile code. Use narrowly wrapped APIs and a low-privilege identity with genuine OS filesystem/network isolation.

<a id="finding-2"></a>

### [2] LM-Eval proxy leaves request, response, buffering, and concurrency resources unbounded

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The body read, response read, streaming buffer, threaded server, and timeout are explicit. |
| Category | resource-exhaustion |
| CWE | CWE-400 |
| Affected lines | src/tools/lmeval_proxy.py:38-59, src/tools/lmeval_proxy.py:64-74, src/tools/lmeval_proxy.py:124-169, src/tools/lmeval_proxy.py:185-199 |

#### Summary

The proxy accepts attacker-sized bodies and responses, buffers streaming data without an event limit, and creates unbounded request threads.

#### Root Cause

The proxy has a long upstream timeout but no bounded body, response, SSE event, connection, or concurrency policy.

**proxy-body** — `src/tools/lmeval_proxy.py:64-74`

Client-controlled length is read without a maximum.

```python
length = int(self.headers.get("Content-Length", 0))
return self.rfile.read(length)
```

**proxy-response** — `src/tools/lmeval_proxy.py:38-59`

Non-streaming responses are fully materialized without a size bound.

```python
return resp.status, resp_headers, resp.read()
```

**proxy-stream** — `src/tools/lmeval_proxy.py:124-169`

A malformed or slow stream can grow until a delimiter arrives.

```python
buffer += chunk
while b"\n\n" in buffer: ...
```

**proxy-threading** — `src/tools/lmeval_proxy.py:185-199`

Clients can consume request threads without admission control.

```python
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

#### Validation

Reachable clients can send oversized bodies, induce large responses, or hold streaming connections; loopback default limits this to local clients but does not bound resources.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**proxy-body** — `src/tools/lmeval_proxy.py:64-74`

Client-controlled length is read without a maximum.

```python
length = int(self.headers.get("Content-Length", 0))
return self.rfile.read(length)
```

**proxy-response** — `src/tools/lmeval_proxy.py:38-59`

Non-streaming responses are fully materialized without a size bound.

```python
return resp.status, resp_headers, resp.read()
```

**proxy-stream** — `src/tools/lmeval_proxy.py:124-169`

A malformed or slow stream can grow until a delimiter arrives.

```python
buffer += chunk
while b"\n\n" in buffer: ...
```

**proxy-threading** — `src/tools/lmeval_proxy.py:185-199`

Clients can consume request threads without admission control.

```python
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

#### Dataflow

Client headers/body -\> rfile.read/threaded handler -\> upstream urlopen/read/buffer -\> retained resources.

**proxy-body** — `src/tools/lmeval_proxy.py:64-74`

Client-controlled length is read without a maximum.

```python
length = int(self.headers.get("Content-Length", 0))
return self.rfile.read(length)
```

**proxy-response** — `src/tools/lmeval_proxy.py:38-59`

Non-streaming responses are fully materialized without a size bound.

```python
return resp.status, resp_headers, resp.read()
```

**proxy-stream** — `src/tools/lmeval_proxy.py:124-169`

A malformed or slow stream can grow until a delimiter arrives.

```python
buffer += chunk
while b"\n\n" in buffer: ...
```

**proxy-threading** — `src/tools/lmeval_proxy.py:185-199`

Clients can consume request threads without admission control.

```python
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

#### Reachability

Local by default and network-reachable under optional non-loopback deployment.

#### Severity

**Medium** — A reachable client can exhaust proxy memory, threads, sockets, or upstream inference capacity.

Loopback-only operation limits the attacker to local processes; network exposure raises likelihood.

#### Remediation

Enforce request/response/SSE limits, bounded admission, idle/connection limits, and strict methods/paths.

<a id="finding-3"></a>

### [3] Windows EvalPlus execution disables memory enforcement for generated solutions

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The environment override, Windows shim, generated-solution handoff, and outer subprocess are explicit. |
| Category | resource-exhaustion |
| CWE | CWE-400 |
| Affected lines | src/evalplus_subset_eval.py:27-56, src/evalplus_subset_eval.py:115-145, src/run_benchmarks.py:1274-1281 |

#### Summary

The Windows EvalPlus path explicitly disables EvalPlus memory checks and replaces signal timers with no-ops, leaving only an outer wall-clock timeout.

#### Root Cause

The Windows compatibility workaround removes memory and per-check signal controls without replacing them with equivalent process-level enforcement.

**evalplus-memory** — `src/evalplus_subset_eval.py:27-32`

The Windows evaluator skips the memory query instead of enforcing a bound.

```python
os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")
```

**evalplus-signal** — `src/evalplus_subset_eval.py:41-56`

The signal-based per-check timer becomes a no-op.

```python
class _WindowsSignalTimerShim:
    def setitimer(...): return 0
```

**evalplus-check** — `src/evalplus_subset_eval.py:115-145`

Generated solutions are passed into the evaluator after the guards are disabled.

```python
res = check_correctness(..., solution, ...)
```

**evalplus-outer** — `src/run_benchmarks.py:1274-1281`

Only a wall-clock timeout remains.

```python
subprocess.run([... evalplus_subset_script ...], ..., timeout=eval_timeout)
```

#### Validation

A generated solution can allocate memory in the evaluator child until the outer timeout or system pressure intervenes; no Windows Job Object wraps this subprocess.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**evalplus-memory** — `src/evalplus_subset_eval.py:27-32`

The Windows evaluator skips the memory query instead of enforcing a bound.

```python
os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")
```

**evalplus-signal** — `src/evalplus_subset_eval.py:41-56`

The signal-based per-check timer becomes a no-op.

```python
class _WindowsSignalTimerShim:
    def setitimer(...): return 0
```

**evalplus-check** — `src/evalplus_subset_eval.py:115-145`

Generated solutions are passed into the evaluator after the guards are disabled.

```python
res = check_correctness(..., solution, ...)
```

**evalplus-outer** — `src/run_benchmarks.py:1274-1281`

Only a wall-clock timeout remains.

```python
subprocess.run([... evalplus_subset_script ...], ..., timeout=eval_timeout)
```

#### Dataflow

Generated solution -\> samples JSONL -\> evalplus_subset_eval -\> check_correctness -\> child without memory/timer enforcement -\> excessive allocation.

**evalplus-memory** — `src/evalplus_subset_eval.py:27-32`

The Windows evaluator skips the memory query instead of enforcing a bound.

```python
os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")
```

**evalplus-signal** — `src/evalplus_subset_eval.py:41-56`

The signal-based per-check timer becomes a no-op.

```python
class _WindowsSignalTimerShim:
    def setitimer(...): return 0
```

**evalplus-check** — `src/evalplus_subset_eval.py:115-145`

Generated solutions are passed into the evaluator after the guards are disabled.

```python
res = check_correctness(..., solution, ...)
```

**evalplus-outer** — `src/run_benchmarks.py:1274-1281`

Only a wall-clock timeout remains.

```python
subprocess.run([... evalplus_subset_script ...], ..., timeout=eval_timeout)
```

#### Reachability

Reachable through the repository's EvalPlus pipeline on Windows.

#### Severity

**Medium** — Generated code can consume memory until timeout or system pressure; the impact is availability/resource exhaustion.

A Windows Job Object memory limit around the evaluator would materially reduce impact.

#### Remediation

Launch the evaluator under a Windows Job Object or equivalent memory/process-tree limits and retain a hard wall-clock timeout; do not default memory limits to -1.

<a id="finding-4"></a>

### [4] Configured bearer credentials can be sent over unencrypted HTTP

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Environment-selected URLs, Authorization construction, and urllib transport are explicit. |
| Category | cleartext-transmission |
| CWE | CWE-319 |
| Affected lines | src/model_manager.py:56-68, src/providers/openai_compat_provider.py:29-37, src/providers/base.py:80-109 |

#### Summary

Provider API bases are environment-configurable and bearer tokens are attached without requiring HTTPS for non-loopback endpoints.

#### Root Cause

No control rejects cleartext or non-loopback API URLs when bearer credentials are configured, so transport security is delegated to operator configuration.

**api-base** — `src/model_manager.py:56-68`

The endpoint scheme and host come from environment configuration.

```python
return os.environ.get("LLM_API_BASE", "http://127.0.0.1:1234/v1")
```

**bearer-header** — `src/providers/openai_compat_provider.py:29-37`

Configured credentials are attached to provider requests.

```python
headers = {"Authorization": f"Bearer {key}"} if key else {}
```

**urlopen** — `src/providers/base.py:80-109`

The configured HTTP or HTTPS URL is used without scheme enforcement.

```python
with urllib_request.urlopen(request, timeout=timeout) as response:
```

#### Validation

Default URLs are loopback, but remote HTTP configuration is accepted and credentials are sent in Authorization headers.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**api-base** — `src/model_manager.py:56-68`

The endpoint scheme and host come from environment configuration.

```python
return os.environ.get("LLM_API_BASE", "http://127.0.0.1:1234/v1")
```

**bearer-header** — `src/providers/openai_compat_provider.py:29-37`

Configured credentials are attached to provider requests.

```python
headers = {"Authorization": f"Bearer {key}"} if key else {}
```

**urlopen** — `src/providers/base.py:80-109`

The configured HTTP or HTTPS URL is used without scheme enforcement.

```python
with urllib_request.urlopen(request, timeout=timeout) as response:
```

#### Dataflow

LLM_API_BASE/UNSLOTH_API_BASE -\> provider base_url + Authorization -\> urllib over configured HTTP -\> observer.

**api-base** — `src/model_manager.py:56-68`

The endpoint scheme and host come from environment configuration.

```python
return os.environ.get("LLM_API_BASE", "http://127.0.0.1:1234/v1")
```

**bearer-header** — `src/providers/openai_compat_provider.py:29-37`

Configured credentials are attached to provider requests.

```python
headers = {"Authorization": f"Bearer {key}"} if key else {}
```

**urlopen** — `src/providers/base.py:80-109`

The configured HTTP or HTTPS URL is used without scheme enforcement.

```python
with urllib_request.urlopen(request, timeout=timeout) as response:
```

#### Reachability

Requires operator-supplied remote HTTP configuration.

#### Severity

**Low** — Remote cleartext configuration can expose bearer tokens, but defaults are loopback and HTTPS is supported.

A remote HTTP endpoint carrying privileged credentials would raise impact.

#### Remediation

Require HTTPS for non-loopback endpoints, validate scheme/host policy, and fail closed on cleartext bearer transport.

<a id="finding-5"></a>

### [5] Registry model keys can escape deletion roots

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Key normalization, path construction, and unlink/rmtree sinks are explicit. |
| Category | path-traversal |
| CWE | CWE-22 |
| Affected lines | src/registry_tool.py:1232-1239, src/registry_tool.py:1046-1065, src/registry_tool.py:1091-1102 |

#### Summary

The destructive registry cleanup command joins unchecked registry keys to fixed model roots and deletes resulting paths without containment validation.

#### Root Cause

Cleanup targets must remain beneath exact LM Studio roots, but cmd_rm never resolves and verifies targets before unlinking or recursively deleting.

**registry-key** — `src/registry_tool.py:1232-1239`

Traversal components are not rejected.

```python
s = mk.strip().lower()
...
if "/" not in s: s = f"{pub.lower().strip()}/{s}"
return s
```

**registry-path** — `src/registry_tool.py:1046-1065`

A traversal-containing key is joined into a deletion target without containment checking.

```python
hub_dir = Path.home() / ".lmstudio" / "hub" / "models" / Path(*key.split("/"))
```

**registry-delete** — `src/registry_tool.py:1091-1102`

The unchecked target is deleted when --delete-files is selected.

```python
path.unlink()
...
shutil.rmtree(d)
```

#### Validation

An explicit --delete-files/--yes path can delete a traversal-containing model target; normal keys and confirmation reduce likelihood.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**registry-key** — `src/registry_tool.py:1232-1239`

Traversal components are not rejected.

```python
s = mk.strip().lower()
...
if "/" not in s: s = f"{pub.lower().strip()}/{s}"
return s
```

**registry-path** — `src/registry_tool.py:1046-1065`

A traversal-containing key is joined into a deletion target without containment checking.

```python
hub_dir = Path.home() / ".lmstudio" / "hub" / "models" / Path(*key.split("/"))
```

**registry-delete** — `src/registry_tool.py:1091-1102`

The unchecked target is deleted when --delete-files is selected.

```python
path.unlink()
...
shutil.rmtree(d)
```

#### Dataflow

Model metadata/registry key -\> _canonical_key -\> Path(\*key.split('/')) -\> deletion paths -\> unlink/rmtree.

**registry-key** — `src/registry_tool.py:1232-1239`

Traversal components are not rejected.

```python
s = mk.strip().lower()
...
if "/" not in s: s = f"{pub.lower().strip()}/{s}"
return s
```

**registry-path** — `src/registry_tool.py:1046-1065`

A traversal-containing key is joined into a deletion target without containment checking.

```python
hub_dir = Path.home() / ".lmstudio" / "hub" / "models" / Path(*key.split("/"))
```

**registry-delete** — `src/registry_tool.py:1091-1102`

The unchecked target is deleted when --delete-files is selected.

```python
path.unlink()
...
shutil.rmtree(d)
```

#### Reachability

Local maintenance workflow only; no remote attacker path is established.

#### Severity

**Low** — Traversal requires a malicious registry entry and explicit destructive CLI action; it is a local maintenance boundary.

If registry metadata can be supplied by a less-trusted source, impact would increase.

#### Remediation

Reject traversal/absolute/drive/backslash/reparse components and require resolved containment beneath the exact intended root before deletion.

<a id="finding-6"></a>

### [6] LM-Eval proxy can survive abnormal launcher termination

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Start, normal cleanup, and atexit registration paths are explicit. |
| Category | process-lifecycle |
| CWE | CWE-772 |
| Affected lines | src/run_benchmarks.py:346-357, src/run_benchmarks.py:2162-2166, src/run_benchmarks.py:2200-2205 |

#### Summary

The launcher starts the proxy but registers only lock cleanup with atexit and calls proxy termination only on the normal main path.

#### Root Cause

The child lifetime is not coupled to the parent on abnormal exits; proxy cleanup is not registered in the exit handler or protected by a top-level finally.

**proxy-start** — `src/run_benchmarks.py:346-357`

The launcher creates a separate proxy process.

```python
_lmeval_proxy_proc = subprocess.Popen([... lmeval_proxy.py ...])
```

**proxy-atexit** — `src/run_benchmarks.py:2162-2166`

Exit cleanup releases the lock but does not stop the proxy child.

```python
atexit.register(_release_single_instance_lock)
```

**proxy-normal-stop** — `src/run_benchmarks.py:2200-2205`

Proxy termination occurs on the normal main path, not a guaranteed finally/atexit path.

```python
_stop_lmeval_proxy()
_print_final_summary(all_summary)
```

#### Validation

Normal completion stops the proxy, but interruption or an unhandled exception can leave it listening.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**proxy-start** — `src/run_benchmarks.py:346-357`

The launcher creates a separate proxy process.

```python
_lmeval_proxy_proc = subprocess.Popen([... lmeval_proxy.py ...])
```

**proxy-atexit** — `src/run_benchmarks.py:2162-2166`

Exit cleanup releases the lock but does not stop the proxy child.

```python
atexit.register(_release_single_instance_lock)
```

**proxy-normal-stop** — `src/run_benchmarks.py:2200-2205`

Proxy termination occurs on the normal main path, not a guaranteed finally/atexit path.

```python
_stop_lmeval_proxy()
_print_final_summary(all_summary)
```

#### Dataflow

main -\> Popen(proxy) -\> exception/interruption -\> lock-only atexit cleanup -\> proxy remains alive.

**proxy-start** — `src/run_benchmarks.py:346-357`

The launcher creates a separate proxy process.

```python
_lmeval_proxy_proc = subprocess.Popen([... lmeval_proxy.py ...])
```

**proxy-atexit** — `src/run_benchmarks.py:2162-2166`

Exit cleanup releases the lock but does not stop the proxy child.

```python
atexit.register(_release_single_instance_lock)
```

**proxy-normal-stop** — `src/run_benchmarks.py:2200-2205`

Proxy termination occurs on the normal main path, not a guaranteed finally/atexit path.

```python
_stop_lmeval_proxy()
_print_final_summary(all_summary)
```

#### Reachability

Requires abnormal exit after proxy startup; remote reachability additionally requires non-loopback configuration.

#### Severity

**Low** — An orphan can retain a port and accept requests; default loopback binding limits the consequence to local resources.

A non-loopback proxy or a long-lived parent failure would raise impact.

#### Remediation

Register proxy cleanup with atexit, wrap lifecycle in try/finally, and manage the child under a Windows Job Object or equivalent.

<a id="finding-7"></a>

### [7] Optional non-loopback binding exposes an unauthenticated model proxy

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The listener, forwarding routes, and missing auth are explicit. |
| Category | missing-authentication |
| CWE | CWE-306 |
| Affected lines | src/tools/lmeval_proxy.py:70-98, src/tools/lmeval_proxy.py:171-182, src/tools/lmeval_proxy.py:185-199, src/run_benchmarks.py:354-366 |

#### Summary

The LM-Eval proxy accepts an arbitrary bind address, forwards requests without authentication, and permits wildcard CORS.

#### Root Cause

The proxy's network boundary is configurable but its authorization policy is not; non-loopback deployment creates a reachable inference and arbitrary POST surface.

**proxy-bind** — `src/tools/lmeval_proxy.py:185-199`

An operator can bind the unauthenticated server to a network interface.

```python
parser.add_argument("--bind", type=str, default="127.0.0.1", ...)
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

**proxy-forward** — `src/tools/lmeval_proxy.py:70-98`

POST requests are forwarded without client identity or route authorization.

```python
if path == "/v1/chat/completions": ...
else: _proxy_upstream(..., body)
```

**proxy-cors** — `src/tools/lmeval_proxy.py:171-182`

Any browser origin can read responses when the listener is reachable.

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

#### Validation

Default loopback binding is counterevidence, so severity is conditional low rather than default high; the source still lacks any auth or route policy.

Validation method: Offline source trace plus independent baseline/focused audit cross-check.

**proxy-bind** — `src/tools/lmeval_proxy.py:185-199`

An operator can bind the unauthenticated server to a network interface.

```python
parser.add_argument("--bind", type=str, default="127.0.0.1", ...)
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

**proxy-forward** — `src/tools/lmeval_proxy.py:70-98`

POST requests are forwarded without client identity or route authorization.

```python
if path == "/v1/chat/completions": ...
else: _proxy_upstream(..., body)
```

**proxy-cors** — `src/tools/lmeval_proxy.py:171-182`

Any browser origin can read responses when the listener is reachable.

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

#### Dataflow

--bind -\> ThreadingHTTPServer -\> unauthenticated handler -\> chat/arbitrary POST -\> configured upstream.

**proxy-bind** — `src/tools/lmeval_proxy.py:185-199`

An operator can bind the unauthenticated server to a network interface.

```python
parser.add_argument("--bind", type=str, default="127.0.0.1", ...)
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

**proxy-forward** — `src/tools/lmeval_proxy.py:70-98`

POST requests are forwarded without client identity or route authorization.

```python
if path == "/v1/chat/completions": ...
else: _proxy_upstream(..., body)
```

**proxy-cors** — `src/tools/lmeval_proxy.py:171-182`

Any browser origin can read responses when the listener is reachable.

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

#### Reachability

Reachable only when an operator exposes the proxy beyond loopback.

#### Severity

**Low** — A reachable attacker can use inference or forwarded routes, but default and normal launcher binding are loopback-only.

A non-loopback deployment without upstream auth would raise impact.

#### Remediation

Reject non-loopback binds by default or require authenticated configuration; add token auth, route allowlisting, limits, and explicit CORS origins.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Generated code execution and OS boundary | code-execution | Reported | Fully reviewed by baseline and focused process audits. |
| EvalPlus generated-solution evaluation | resource-exhaustion | Reported | Windows compatibility path and outer subprocess controls reviewed. |
| Provider HTTP, credentials, and lifecycle | transport-and-authentication | Reported | Provider base and concrete providers reviewed. |
| LM-Eval proxy listener and forwarding | network-boundary | Reported | Listener auth, forwarding, buffering, and cleanup reviewed. |
| Registry deletion and generated configuration paths | filesystem | Reported | Registry destructive path reviewed; template path traversal rejected as trusted-local configuration only. |
| CLI and subprocess execution | process-execution | No issue found | Production subprocesses use argument lists; no shell=True path established. |
| Remaining documentation, fixtures, and configuration | coverage | Needs follow-up | Keyword-reviewed but not fully read; no additional issue established. |

## Open Questions And Follow Up

- Whether wrappers expose lmeval_proxy.py beyond loopback.
- Whether remote provider deployments enforce HTTPS.
- Whether external EvalPlus adds an independent memory/process boundary.
- The workbench inventory reported 155 files; baseline fully reviewed 153 and keyword-reviewed the remainder.
  - Follow-up prompt: Review deferred unit remaining-documentation-and-fixtures and close its stated proof gap.
- External evalplus correctness implementation is not present and was not fetched or executed.
  - Follow-up prompt: Review deferred unit external-evalplus-implementation and close its stated proof gap.
