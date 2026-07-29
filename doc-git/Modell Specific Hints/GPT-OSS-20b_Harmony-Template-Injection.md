# GPT-OSS-20b: Harmony-Jinja-Template-Injection in LM Studio Config JSONs

## Problem
GPT-OSS-20b **benötigt zwingend** das Harmony-Jinja-Template (`llm.prediction.promptTemplate`)
im LM-Studio-Config-JSON. Ohne dieses Template verwendet LM Studio sein Default-ChatML-Template
(`<|im_start|>`, `<|im_end|>`). Das Modell versteht ChatML nicht (erwartet Harmony-Format
`<|start|>channel<|message|>...<|end|>`) und produziert leeren Output.

## Ursache
LM Studio schreibt bei Updates die Config-JSONs ueber. Die Template-Injektion vom 09.07.2026
und 24.07.2026 wurde dadurch mehrfach ueberschrieben.
**Zuletzt erneut ueberschrieben bei unbekanntem LM-Studio-Update vor dem 28.07.2026.**

## Fix (28.07.2026) — Alle bekannten Bugs behoben

### Bug 1: Fehlendes Harmony-Template
Template `doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja` (17221 Zeichen)
wurde in alle Configs injiziert:

| Config | Vorher | Nachher |
|---|---|---|
| `openai/gpt-oss-20b.json` (Default-Load) | **fehlt** (3179 Bytes) | Template + Prompt (20447 Bytes) |
| `lmstudio-community/.../MXFP4.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |
| `unsloth/.../Q6_K.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |
| `unsloth/.../Q8_0.gguf.json` | vorhanden, falscher Prompt | Template korrekt + Prompt aktualisiert |

### Bug 2: Falscher System-Prompt (XML-Tags statt Markdown)
Die `systemPrompt` enthielt `<role>`, `<reasoning>`, `<coding>`, `<output>` XML-Tags.
Diese sind **nicht** Harmony-kompatibel. Der Prompt wurde umgestellt auf Markdown-Headings:

**Vorher:**
```
<role>
You are GPT-OSS, an AI software engineering assistant.
</role>

<reasoning>
- Analyze the problem step by step...
</reasoning>
```

**Nachher:**
```
You are gpt-oss-20b, a GPT-OSS MoE model with 20B parameters...

## Reasoning
- Analyze the problem step by step...

## Safety
...
```

Der Fix erfolgte in `assemble_blueprint.py`: neue Funktion `_harmonify_prompt()`
konvertiert XML-Tag-Prompts in Harmony-Markdown. Nur fuer `gptoss_reasoning`-Blueprint.

### Bug 3: `chat_template_kwargs` wurde fälschlich an gpt-oss gesendet
`run_benchmarks.py:_get_evaluation_parameters()` schickte `chat_template_kwargs`
mit `enable_thinking: False` fuer alle Modelle mit `enable_thinking` im Config.
Dieser Parameter ist nur fuer Qwen-Modelle gueltig. Fix: `chat_template_kwargs`
wird nur noch fuer Nicht-gpt-oss-Modelle gesetzt.

### Bug 4: `max_thinking_tokens` fehlte — Reasoning-Token-Budget unbegrenzt
**Kritischster Bug.** Ohne `max_thinking_tokens` denkt gpt-oss bis `max_tokens`
(4096 bei MATH-500) und produziert `content=""`. Der Parameter musste in 3 Dateien
hinzugefuegt werden:

| Datei | Aenderung |
|---|---|
| `benchmark_config.py` Zeile 283 | `"max_thinking_tokens": 200` in gpt-oss-Override |
| `run_benchmarks.py` Zeilen 625, 996 | `"max_thinking_tokens"` in `generation_parameters_keys` |
| `custom_benchmark.py` Zeilen 763, 779 | `body["max_thinking_tokens"] = 200` fuer gpt-oss |

### Bug 5: `reasoning` statt `reasoning_effort` im API-Body
`squashed in earlier session (24.07.2026)`

## Wirkung der Fixes (Testlauf 3, 28.07.2026)

| Benchmark | Vor Fixes (ChatML, kein Budget) | Nach Fixes (Harmony + max_thinking_tokens=200) |
|---|---|---|
| DS1000 | 0% (leerer Output) | ~33% (sample-size 3, echter Code) |
| MATH-500 | 0% (leerer Output) | 20% (sample-size 5) |
| IFEVAL | 40%/62.5% | 40%/62.5% (stabil) |

## Verifikation
```bash
# Config-JSON auf Template und Prompt pruefen
python -c "import json; d=json.load(open(r'C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\openai\gpt-oss-20b.json')); fields={f['key']: f['value'] for f in d['operation']['fields']}; print('Has template:', 'promptTemplate' in str(list(fields.keys()))); print('Prompt starts:', repr(fields['llm.prediction.systemPrompt'][:80]))"

# Template-Validierung (registry_tool.py)
echo "14" | python registry_tool.py | grep template
# Erwartet: template_missing_config: 0

# Blueprint-Assembly + Validierung
python assemble_blueprint.py assemble
python assemble_blueprint.py validate
```

## Stabilitaet
Das Template wird bei LM-Studio-Updates ueberschrieben. Nach jedem Update:
1. `python assemble_blueprint.py assemble` (stellt Prompt + Template wieder her)
2. Modell neu laden: `lms unload --all && lms load openai/gpt-oss-20b`

## Template-Quelle
`doc-git/Jinja-Chat-Templates/gpt-oss-20b_harmony.jinja`
(identisch mit `gpt-oss-20b-template_unsloth.jinja`, SHA256 bestaetigt)

## Quellen
- https://developers.openai.com/cookbook/articles/openai-harmony
- https://developers.openai.com/cookbook/articles/gpt-oss/run-locally-lmstudio
- https://github.com/openai/gpt-oss/tree/main?tab=readme-ov-file#harmony-format--tools
- https://lmstudio.ai/blog/gpt-oss
