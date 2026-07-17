# Thinking/Reasoning Konfiguration

Dokumentiert die Steuerung des Thinking-Modus in `custom_benchmark_v13.py:MODEL_CONFIG`.

## Mechanismus

Das System steuert Thinking auf zwei Ebenen:

1. **MODEL_CONFIG** (`custom_benchmark_v13.py:140-230`): Per-Modell-Defaults
2. **`--thinking` CLI-Flag**: Überschreibt per `REASONING_PATTERNS` auf `True`

### API-Steuerung

Der Parameter `enable_thinking` wird als `extra_body.chat_template_kwargs.enable_thinking` an LM Studio gesendet.

### Gemma 4 Sonderfall

Gemma 4 Modelle ignorieren `enable_thinking=False` über API, weil `<|channel>thought` im GGUF-Jinja-Template fest verdrahtet ist. Zusätzlicher System-Prompt-Override in `generate_answer()` (`custom_benchmark_v13.py:659-663`):
```
"System: Do NOT use thinking or reasoning. Answer directly without <|channel>thought tags."
```

## Aktuelle Patterns (MODEL_TEMP_OVERRIDES)

Die `max_tokens` werden seit v13 von der **Benchmark-Kategorie** bestimmt (Variante C+, p6):
- **coding**: 2048 | **math**: 8192 | **knowledge**: 2048 | **agentic**: 4096

Die folgenden Overrides überschreiben nur abweichende Kategorie-Defaults:

| Pattern | enable_thinking | max_tokens (Override) | Besonderheit |
|---------|----------------|----------------------|-------------|
| default | **False** | – | Default seit 2026-07-11 |
| qwen3.5 | False | – | temperature=0.2, top_p=0.9, no_system_msg |
| qwen3.6 | False | 8192 | Thinking verbraucht sonst Budget → 0% Score |
| gemma | False | – | + System-Prompt-Override |
| deepseek | **True** | 2048 | Einziger Default mit Thinking=an |
| gpt-oss | False | 4096 | stop: <\|return\|>, <\|call\|> |
| apriel | False | 4096 | |
| nemotron | False | 4096 | |
| falcon3 | False | – | |
| codestral | False | – | |
| devstral | False | – | |
| ernie | False | – | |
| rnj | False | – | THOUGHT:/RESPONSE: Parsing-Format (hub model.yaml) |
| python-coder | False | – | Fängt qwen3-*-python-coder u.ä. |

> `–` in der max_tokens-Spalte = Kategorie-Default gilt (kein Override).

## --thinking Flag Verhalten (v13 Klarstellung)

Das `--thinking` CLI-Flag hat seit v13 eine eingeschränkte Wirkung:

| Modellgruppe | --thinking Wirkung | Begründung |
|-------------|-------------------|------------|
| **Reasoning-Modelle** (Name enthält "reasoning"/"think"/"r1"/"rnj") | ✅ Aktiviert enable_thinking + Timeout ×2 | Natives Reasoning unterstützt |
| **Gemma 4** | ✅ Aktiviert enable_thinking für MATH-500 | Gemma-4-Template setzt `<|channel>thought` |
| **Qwen3.6** | ❌ Wird ignoriert (enable_thinking=False erzwungen) | Thinking-Tokens blockieren Token-Budget → 0% Score |
| **GPT-OSS** | ❌ Wird ignoriert (kein Thinking-Support) | GPT-OSS Architektur hat kein Thinking |
| **Qwen3.5** | ❌ Wird ignoriert (enable_thinking=False erzwungen) | Kein Thinking-Support |
| **Default (andere Modelle)** | ❌ Hat keine Wirkung | enable_thinking=None (kein extra_body) |

**Praktische Konsequenz:** `--thinking` sollte nur bei Gemma 4 und expliziten Reasoning-Modellen verwendet werden. 
Für alle anderen Modelle ist es ein No-Op.

## MODEL_CONFIG in _get_lmeval_params (v13)

Seit v13 werden die Thinking-Parameter nicht mehr in MODEL_CONFIG (custom_benchmark_v13.py) verwaltet, 
sondern zentral in `_get_lmeval_params()` in `run_benchmarks_v13.py`. Dies vermeidet doppelte Konfiguration 
zwischen Custom-Pipeline und lm_eval-Pipeline.

Die Modell-Klassifizierung (_is_reasoning_model, _is_qwen3_6_model, _is_gptoss_model, _is_gemma_model, 
_is_qwen3_5_model) steuert:
- enable_thinking (True/False/None)
- Kategorie-Defaults: coding=2048, math=8192, knowledge=2048, agentic=4096
- temperature/top_p/min_p
- stop-Strings (until)
- no_system_msg

MODEL_CONFIG in custom_benchmark_v13.py enthält nur noch die Custom-Pipeline-Parameter.

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
- **run_benchmarks_v13.py**: lm_eval-Parameter via `--gen_kwargs` statt `--model_args` übergeben
  - Generation-Parameter (max_tokens, temperature, top_p, min_p, extra_body, until)
    landen jetzt im API-Payload statt im (ignorierten) Konstruktor
  - `--model_args` enthält nur noch Konstruktor-Parameter (base_url, model, num_concurrent, max_gen_toks)
  - `eos_string=<|endoftext|>` nur noch für GPT-OSS (nicht mehr für alle Modelle)
- **HellaSwag Limit**: `min_limit=100` pro Benchmark-Konfig, überschreibt `sample_size`
