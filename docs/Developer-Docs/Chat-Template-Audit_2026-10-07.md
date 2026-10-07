# Chat-Template Audit (2026-10-07)

## Scope and rule

This audit compares the project's registered model families, local Jinja
overrides, Blueprint mappings and available LM Studio config fields with the
upstream tokenizer/chat-template sources. A custom `promptTemplate` is written
only when the Registry Blueprint explicitly owns that template and the match
to a concrete model/config is unique. Otherwise, the model's GGUF-embedded
template remains the runtime source. Do not apply one generic ChatML Jinja file
to unrelated architectures.

## Gemma 4

- The official Google model repositories for Gemma-4 12B, 26B A4B and 31B
  provide the full Gemma turn/channel/tool template. Their current
  `chat_template.jinja` files use the same template body; the versioned local
  12B and 26B copies were compared against the official sources.
- The Blueprint maps 12B to the 12B-named copy and 19B REAP, 26B A4B and 31B
  to the 26B A4B copy. The 19B REAP is derived from the 26B A4B family; the
  31B upstream template is the shared canonical Gemma-4 template. The 31B map
  is explicit in both Gemma Blueprints and the code-generated defaults.
- The local `gemma4-*-template_minijinja.jinja` Hub overrides are reduced
  compatibility variants. They do not contain the full tool-schema and
  content-part handling of the official template. Registry-managed models
  should use the Blueprint's full template in their concrete LM Studio
  `promptTemplate` field where that field is missing.
- `registry_tool.py sync-templates --model <Registry-Key> ... --dry-run`
  previews only selected model keys. The write invocation omits `--dry-run`;
  populated config templates remain untouched.
- The LM Studio log warning about a stale Gemma template and tokenizer/EOG
  metadata should be tracked separately from prompt-template selection. It is
  not, by itself, proof that a specific custom section tag caused an early end.

## Mistral AI

Mistral does not have one universal ChatML template. The official tokenizer
families use their own spacing and control-token rules; the Instruct templates
use `[INST]`/`[/INST]`, with behavior varying across SentencePiece and Tekken
versions. The local Codestral/Mistral and Mistral-3/Devstral entries have no
project Jinja override, so their embedded GGUF template remains authoritative.
Do not replace it with Phi-4 or Qwen ChatML.

Sources: [Mistral tokenizer and chat-template guide](https://docs.mistral.ai/resources/cookbooks/concept-deep-dive-tokenization-chat_templates)
and [Mistral migration guidance](https://docs.mistral.ai/resources/migration-guides).

## GLM

The local GLM-4.7 Flash path is DeepSeek2-based and its Blueprint owns reasoning
parsing, not a generic ChatML template. GLM-4.6V has a separate `glm4` Blueprint.
The official GLM-4.5 family template uses native role/control markers (including
`[gMASK]` and `<|system|>`), so a generic `<|im_start|>` template would be a
format mismatch. No local Jinja override is present for the registered GLM
models; keep their embedded templates and the separate Blueprint policies.

Source: [Z.ai GLM-4.5 template](https://huggingface.co/zai-org/GLM-4.5-Air/blob/main/chat_template.jinja).

## Phi-4

Microsoft Phi-4 uses the ChatML-style `<|im_start|>`, `<|im_sep|>` and
`<|im_end|>` markers. The local `phi-4_template_unsloth.jinja` matches the
upstream string-message template. The current Registry's base Phi-4 entry uses
the reasoning-coding Blueprint, not `phi4_reasoning`, so the specialized
Phi-4 template is not assigned to that entry. Keep that distinction; do not
attach the Phi-4 template to unrelated ChatML models.

Source: [Microsoft Phi-4 tokenizer configuration](https://huggingface.co/microsoft/phi-4/blob/main/tokenizer_config.json).

## Qwen 2 / 2.5 / 3

- Qwen2.5-Coder uses ChatML message delimiters and Qwen-specific tool-call
  serialization in its official tokenizer template.
- Qwen3 also uses the ChatML message shell, but adds thinking-channel parsing,
  reasoning controls and model-specific tool handling. It is not interchangeable
  with the older Qwen2.5 template.
- The local Qwen2.5-Coder and Qwen3 Registry entries do not declare a custom
  Jinja override in the Blueprint or LM Studio config. Their GGUF-embedded
  templates remain authoritative; no duplicate local ChatML file is added.

Sources: [Qwen2.5-Coder tokenizer configuration](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct/blob/main/tokenizer_config.json)
and [Qwen3 tokenizer configuration](https://huggingface.co/Qwen/Qwen3-14B/blob/main/tokenizer_config.json).
