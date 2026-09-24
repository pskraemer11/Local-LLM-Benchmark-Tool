# Refactoring: Model Identity and Synchronization Boundaries

## Goal

Reduce silent mismatches between `model_registry.yaml`, LM Studio model/config
records, local GGUF files, Hugging Face names, and llama.cpp runtime arguments.
The canonical persisted identity remains `publisher/model@quant`; existing YAML
keys stay compatible. Ambiguous evidence must be reported and must never be
resolved by iteration order.

## Invariants

1. A normalized exact identity maps to zero or one Registry keys. Collisions are
   blocking validation errors.
2. A runtime or write path may use only a unique artifact or identity match.
   Prefix, suffix, and fuzzy matches are diagnostic evidence, not write/runtime
   decisions.
3. GGUF facts remain technical evidence, Registry fields remain benchmark
   policy, and LM Studio JSON remains a backend-local runtime artifact.
4. Quantization spelling is normalized once, while the original source value is
   retained for diagnostics.
5. Existing public CLI commands and valid unambiguous model selections retain
   their behavior.
6. Parameter translations are declared centrally and tested at each backend
   boundary.

## Smells and affected areas

- `model_identity.py`, `model_registry.py`, and `run_benchmarks.py` previously
  built normalized maps with first-wins semantics.
- `local_model_resolver.py`, `registry_tool.py`, and `run_benchmarks.py` used
  separate GGUF discovery and path-matching rules.
- Quantization patterns were duplicated in `benchmark_config.py`,
  `assemble_blueprint.py`, and `registry_tool.py`.
- Provider mappings were partly described by `field_owner.py`, partly encoded
  in `model_registry.py`, and partly encoded in llama.cpp argument loops.
- `registry_tool.py` combines inventory, matching, synchronization, web
  research, persistence, validation, and CLI orchestration.

## Ordered implementation phases

### Phase 0 — Guardrails and characterization

Add collision detection and regression tests for publisher-sensitive exact
matches, ambiguous base matches, and duplicate quantization identities. Keep
the current Registry data unchanged; validation reports the existing collision
instead of silently changing it.

### Phase 1 — Typed identity resolution

Introduce an explicit resolution result with `unique`, `ambiguous`, and
`unmatched` states. Keep `match_registry_key()` as a compatibility wrapper that
returns a key only for a unique result. Migrate runtime consumers to the typed
result so ambiguity cannot be confused with absence.

### Phase 2 — Shared inventory and identity links

Make the existing per-run inventory the single snapshot for Registry, LMS
records, configs, and GGUF candidates. Add an identity-link contract for
diagnostics and proposals; do not rescan the filesystem independently in a
single workflow.

### Phase 3 — Declarative quant and parameter contracts

Move quantization aliases/patterns into one typed table. Add a declarative
parameter-binding table for canonical Registry fields, LMS fields, llama.cpp
flags, type/range validation, and field ownership. Adapters consume the table;
they do not create competing mappings.

### Phase 4 — One artifact resolver

Centralize GGUF discovery and evidence ranking. The resolver returns unique,
ambiguous, or not-found results with candidate paths and evidence. Exact
relative paths and explicit Hub sources outrank normalized filename matches;
fuzzy matches are never accepted for writes or runtime execution.

### Phase 5 — Strict consumer migration

Migrate Registry reads, config synchronization, preset export, EOS lookup, and
local model enumeration to the shared identity/artifact contracts. Remove
first-wins dictionaries and legacy fuzzy fallback from execution paths while
retaining report-only diagnostics.

### Phase 6 — Boundary consolidation and documentation

Keep `registry_tool.py` as the stable CLI facade while moving reusable contracts
into focused modules. Add the official llama.cpp/Hugging Face metadata mapping
to the architecture documentation. Verify tests, static validation, and
documentation links; live LM Studio/llama.cpp tests remain a separate follow-up.

## Proof and acceptance

- New tests fail on the pre-refactor exact-collision behavior and pass after
  the change.
- `registry_tool.py validate --ci` fails closed on normalized exact collisions.
- Focused identity, resolver, Registry, pipeline, and provider tests pass.
- Full `pytest` and configured Ruff/type checks are run after integration.
- No live model loading, LM Studio mutation, remote search, commit, or push is
  part of this refactor.

## Rollback

Each phase preserves the public YAML and CLI contracts. A phase can be reverted
by removing its new module/adapter and restoring the compatibility call site;
the Registry data is not auto-rewritten. The collision report is intentionally
non-destructive until each affected entry has been reviewed.

## Review focus

Reviewers should check publisher and quant preservation, ambiguity propagation,
artifact candidate ordering, config write boundaries, parameter type/range
validation, and whether any consumer can still select a first match from a
mapping or filesystem scan.
