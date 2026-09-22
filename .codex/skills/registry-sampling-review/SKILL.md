---
name: registry-sampling-review
description: Review unresolved or conflicting model sampling evidence from Hugging Face and official documentation, then apply only user-approved values through the Benchmarks Registry API.
---

# Registry Sampling Review

Use this skill only for an explicit review of Registry entries whose
`sampling_research_status` is `unresolved`, `not_found`, or `conflict`.
It is a manual escalation path, not part of a benchmark run.

## Boundaries

- Work in `C:\Users\pskra\Python-Projekte\Benchmarks`.
- Treat `doc-git/model_registry.yaml` as the Registry source of truth, but do
  not edit it directly.
- Do not inspect or modify LM Studio JSON configuration files for this task.
- OCR, MTP-drafter and embedding models are outside the Registry benchmark scope.
- Never infer a value from a model family, quantization name, or another model.
- Do not silently resolve contradictory sources. Present the conflict and stop
  for a user decision.

## Review workflow

1. Read the Registry entries and select only the requested unresolved/conflict
   models. Confirm that they pass the existing benchmark-candidate filter.
2. Search in this order: the exact Hugging Face model card, Hugging Face
   `base_model` metadata and linked base cards, official links in the card,
   and the manufacturer's model/inference documentation. Follow only HTTPS
   links and prefer primary sources, including the manufactorer and publisher.
3. Capture an exact excerpt and URL for every accepted field. Distinguish
   `thinking`/`reasoning` versus `non-thinking`/`instruct`, and other general
   or specialised coding/math profiles. A profile must contain at least an
   explicit `temperature` and `top_p` pair, as well as `context_length`,
   `k_cache` and `v_cache` quantization.
4. Check the Registry bounds: temperature 0..2, top_p 0..1, top_k 0..1000
   integer, and min_p 0..1. Reject values outside those ranges.
5. Show the proposed sampling block, source URLs, experts, and any remaining
   ambiguity to the user before writing.
6. After approval, call `src.registry_tool.apply_sampling_review(...)` from a
   Python process. This is the only write path; it validates the block, stores
   source evidence and timestamp, and writes no LM Studio configuration.
7. Run `py -3.12 src/registry_tool.py validate --ci` and the focused sampling
   tests. Report unresolved items rather than inventing defaults.

The automatic onboarding path remains `registry_tool.py add`/`sync`. Use
`--refresh-sampling` only when the user explicitly requests a fresh automatic
attempt for terminal statuses.
