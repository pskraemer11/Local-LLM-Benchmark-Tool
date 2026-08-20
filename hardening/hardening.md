# Security Hardening Review: Benchmarks

## Evidence Basis

We are working from the completed Codex Security scan `c6fef5c3-f885-4cfb-afd0-b53a34cda5cf`, bound to the dirty-worktree snapshot `codex-security-snapshot/v1:sha256:53183da47073825a204c56454677bb389f175a0d0b79fb04237212a8893a7f92`.
The sealed manifest hash is `56e0ca675bb503af0f3a05e796f7accbeaf2d34aadd1ad64c4903129000c9b66`.
The archived [scan report](security-scan/report.md) and machine-readable scan artifacts are stored under `hardening/security-scan/`.
I inspected the canonical findings and the relevant source around the sandbox worker, EvalPlus subprocess, LM-Eval proxy, and launcher cleanup.
The scan coverage is partial, and the current worktree may have drifted after the snapshot; that must be checked before implementation.

The three selected findings are not three unrelated patches.
The sandbox and EvalPlus findings both show that generated code does not inherit one consistently enforced execution boundary.
The proxy finding shows the same kind of policy drift at a network boundary:
    safety depends on defaults and normal completion rather than on enforced limits and lifecycle ownership.

## Constraints

- Windows compatibility is a hard requirement; POSIX-only signal or fork mechanisms are not an adequate primary solution.
- Direct NumPy, pandas, and matplotlib compatibility is a hard requirement for the coding benchmarks; removing those libraries is not an acceptable security workaround.
- A separate Windows user account is not acceptable; the preferred isolation candidate is an AppContainer/LPAC process identity.
- LM-Eval clients are local only; the proxy should remain loopback-only.
- No performance, memory, or remote-access budget was supplied. We treat all cost claims below as source-derived hypotheses until benchmarked.
- The normal launcher uses the proxy locally. Remote proxy use is therefore an explicit design decision, not a compatibility assumption.
- Proposed work is not a fix. We should mark the findings closed only after the original source paths and adversarial tests pass.

## Opportunity Portfolio

| Opportunity                                     | Evidence                                                              | Options                            | Recommendation                             | Proposal                                      |
| ----------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------ | --------------------------------------------- |
| Enforced boundary for generated evaluation code | `csf_57dcc81118eb3aba784ea723` — sandbox native-loader escape;        | 1. Tactical capability reduction;  | Option 2 for untrusted model/task code;    | [isolated-untrusted-evaluation]               |
|                                                 | `csf_3b9d51bdd18255fa689920a9` — EvalPlus memory enforcement disabled | 2. OS-isolated evaluator           | Option 1 is the immediate containment step | (proposals/isolated-untrusted-evaluation.md)  |
| ----------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------ | --------------------------------------------- |
| Bounded local LM-Eval proxy                     | `csf_93aa4dc792063d79c336499b` — unbounded proxy resources            | 1. Loopback-only bounded proxy;    | Option 1 unless remote clients are a       | [bounded-local-lmeval-proxy]                  |
|                                                 |                                                                       | 2. Authenticated remote gateway    |    confirmed requirement                   | (proposals/bounded-local-lmeval-proxy.md)     |

## Recommendation Summary

We should first make the proxy fail closed and bounded, because that is a small change with immediate operational value.
In parallel, we should put EvalPlus under Windows Job Object enforcement and reduce the sandbox's exposed API surface.
That tactical work lowers risk quickly, but I would not call the sandbox finding closed until generated code runs under a genuine low-privilege OS boundary.
The attractive part of the OS-isolated evaluator is that it gives both evaluator paths one owner for memory, process-tree, filesystem, and network policy;
the cost is startup overhead and Windows deployment complexity.

## Next Decisions

1. **Resolved:** direct NumPy/pandas/matplotlib compatibility is mandatory for coding benchmarks. The AppContainer design must make the approved Scientific stack work; removing it is not an option.

2. **Narrowed:** evaluate AppContainer/LPAC first. Windows Sandbox and the Hyper-V role are not standard options on Windows 11 Home. The next concrete decision is whether the AppContainer spike can launch the current Python/Scientific stack with the required ACLs and acceptable measured budgets.

3. **Resolved:** LM-Eval is local-only. Keep the proxy loopback-only; do not add remote authentication/TLS/gateway complexity.

4. **Next implementation gate:** after the AppContainer/LPAC spike, refresh the source revision and turn the successful design into an implementation work package with compatibility tests, adversarial escape tests, resource benchmarks, rollout and fail-closed rollback.

The detailed AppContainer/LPAC plan is in [proposals/appcontainer-lpac-evaluator.md](proposals/appcontainer-lpac-evaluator.md).
