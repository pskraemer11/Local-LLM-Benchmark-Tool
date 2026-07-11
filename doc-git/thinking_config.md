# Thinking/Reasoning Konfiguration

Dokumentiert die Steuerung des Thinking-Modus in `custom_benchmark_v12.py:MODEL_CONFIG`.

## Mechanismus

Das System steuert Thinking auf zwei Ebenen:

1. **MODEL_CONFIG** (`custom_benchmark_v12.py:140-230`): Per-Modell-Defaults
2. **`--thinking` CLI-Flag**: Überschreibt per `REASONING_PATTERNS` auf `True`

### API-Steuerung

Der Parameter `enable_thinking` wird als `extra_body.chat_template_kwargs.enable_thinking` an LM Studio gesendet.

### Gemma 4 Sonderfall

Gemma 4 Modelle ignorieren `enable_thinking=False` über API, weil `<|channel>thought` im GGUF-Jinja-Template fest verdrahtet ist. Zusätzlicher System-Prompt-Override in `generate_answer()` (`custom_benchmark_v12.py:659-663`):
```
"System: Do NOT use thinking or reasoning. Answer directly without <|channel>thought tags."
```

## Aktuelle Patterns (MODEL_CONFIG)

| Pattern | enable_thinking | max_tokens | Besonderheit |
|---------|----------------|------------|-------------|
| default | **False** | 2048 | Default seit 2026-07-11 |
| qwen3.5 | False | 2048 | temperature=0.2, top_p=0.9, no_system_msg |
| qwen3.6 | False | 8192 | Reasoning verbraucht sonst Budget → 0% Score |
| gemma | False | 4096 | + System-Prompt-Override |
| deepseek | **True** | 2048 | Einziger Default mit Thinking=an |
| gpt-oss | False | 4096 | stop: <\|return\|>, <\|call\|> |
| apriel | False | 4096 | |
| nemotron | False | 4096 | |
| falcon3 | False | 2048 | |
| codestral | False | 2048 | |
| devstral | False | 2048 | |
| ernie | False | 2048 | |
| rnj | False | 2048 | |
| python-coder | False | 2048 | Fängt qwen3-*-python-coder u.ä. |

## Historie

### 2026-07-11
- Default `enable_thinking`: None → **False** (vorher: kein extra_body gesendet)
- 8 neue Patterns hinzugefügt (apriel, nemotron, falcon3, codestral, devstral, ernie, rnj, python-coder)
- gpt-oss `enable_thinking`: None → False
- Gemma System-Prompt-Override implementiert
- Diagnose-Warning in `strip_thinking_tokens()` bei komplettem Thinking-Consume

### 2026-07-11 (Bugfixes HellaSwag/MathQA)
- **YAML max_gen_toks**: MathQA `20→512`, HellaSwag `20→100`
- **YAML Regex**: `[ABCDE]` → `[A-Ea-e]` (lowercase auch matchbar), selbiges für HellaSwag
- **HellaSwag YAML**: `>-` (folded) → `|` (literal) für Newlines im Prompt
- **utils.py**: `process_docs()` Regex robuster gegen Komma-Werte in Choices
- **run_benchmarks_v12.py**: lm_eval-Parameter via `--gen_kwargs` statt `--model_args` übergeben
  - Generation-Parameter (max_tokens, temperature, top_p, min_p, extra_body, until)
    landen jetzt im API-Payload statt im (ignorierten) Konstruktor
  - `--model_args` enthält nur noch Konstruktor-Parameter (base_url, model, num_concurrent, max_gen_toks)
  - `eos_string=<|endoftext|>` nur noch für GPT-OSS (nicht mehr für alle Modelle)
- **HellaSwag Limit**: `min_limit=100` pro Benchmark-Konfig, überschreibt `sample_size`
