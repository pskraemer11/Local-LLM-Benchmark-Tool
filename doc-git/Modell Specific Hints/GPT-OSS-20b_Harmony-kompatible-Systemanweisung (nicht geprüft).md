# GPT-OSS-20b: Harmony-kompatible Systemanweisung (geprüft 2026-07-28)

## Wichtiges vorab: Template vs. SystemPrompt

Das Harmony-JINJA-Template (`doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja`)
übernimmt folgende Aufgaben **automatisch** – diese gehören NICHT in die `systemPrompt`:

| Aufgabe | Generiert vom Template via |
|---|---|
| System-Identity (`<\|start\|>system<\|message\|>You are ChatGPT...`) | Template hartkodiert |
| Aktuelles Datum | `{{ now() }}` |
| Reasoning-Level (`Reasoning: low/medium/high`) | Parameter `reasoning_effort` |
| Channels (`# Valid channels: analysis, commentary, final`) | Template hartkodiert |
| Developer-Message-Header (`<\|start\|>developer<\|message\|># Instructions`) | Template hartkodiert |
| Channel-Tag am Ende (`<\|end\|>`) | Template hartkodiert |

Die `systemPrompt` in der LM-Studio-Config enthält **nur den Text nach `# Instructions\n\n`**.
Keine Harmony-Tags, kein `reasoning_effort`, kein Datum.

## Korrektes Format

### In der Config (`llm.prediction.systemPrompt`):
```
You are {name}, a {arch} model with {params}B parameters by {publisher}, optimized for {capabilities}.

## Reasoning
- Analyze the problem step by step before answering.
- Consider multiple approaches where relevant.
- Distinguish between established facts, assumptions, and uncertainty.
- Verify your reasoning for logical consistency.

## Safety
- Do not execute code without explicit user confirmation.
- Do not fabricate information or pretend to have capabilities you lack.
- Respect user privacy and data security.

## Coding
- Understand the codebase before making changes.
- Write clean, maintainable, testable code.
- Make minimal necessary changes.
- Prefer reproducible debugging.

## Output Style
- Provide concrete examples where useful.
- Explain design decisions briefly.
- Include error handling and edge cases.
- Prefer clarity over verbosity.
- Respond in the user's language unless it's code.
```

### Was der Renderer daraus macht (via JINJA-Template):
```
<|start|>system<|message|>
You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2026-07-28

Reasoning: low

# Valid channels: analysis, commentary, final. Channel must be included for every message.<|end|>

<|start|>developer<|message|># Instructions

You are gpt-oss-20b, a GPT-OSS MoE model with 20B parameters by openai, optimized for coding, test generation and reasoning features.

## Reasoning
- Analyze the problem step by step before answering.
...

## Safety
...
<|end|>

<|start|>user<|message|>Hallo!<|end|>
```

## Steuerung ueber API (nicht im SystemPrompt)

| Parameter | Effekt | Quelle |
|---|---|---|
| `reasoning_effort: "low"` | Setzt Reasoning-Level im System-Block | `benchmark_config.py` Zeile 282 |
| `max_thinking_tokens: 200` | Begrenzt Reasoning-Token-Budget | `benchmark_config.py` Zeile 283 |
| `enable_thinking: false` | Schaltet Reasoning komplett aus (nur Qwen) | `benchmark_config.py` Zeilen 318-319 |

## Wichtige Erkenntnis 2026-07-28

**Ohne `max_thinking_tokens`** denkt gpt-oss bis zum `max_tokens`-Limit und produziert
`content=""` (leerer Output). Grund: das Modell schaltet nie vom Reasoning-Channel
auf den Output-Channel um, wenn das Reasoning-Token-Budget unbegrenzt ist.

Erst mit `max_thinking_tokens: 200` wird das Reasoning begrenzt und das Modell
generiert sichtbaren Content.
