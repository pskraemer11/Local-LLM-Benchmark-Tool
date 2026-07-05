## Review-Bericht: Gemma-4-Prompt-Formatting & Jinja-Templates ##

Beide Templates sind jetzt repariert. Hier die detaillierte Zusammenfassung:

---

### 1. Offizielles Format (aus `tokenizer_config.json` von `google/gemma-4-12b-it`)

| Struktur   | Offiziell                                                                  | Token                   |
|------------|----------------------------------------------------------------------------|-------------------------|
| Turn Start | `<\|turn>role\n`                                                           | `sot_token`             |
| Turn End   | `<turn\|>`                                                                 | `eot_token`             |
| Tool Call  | `<\|tool_call>call:name{args}<tool_call\|>`                                | `stc_token`/`etc_token` |
| Tool Decl. | `<\|tool>declaration:name{...}<tool\|>`                                    | `std_token`/`etd_token` |
| Tool Resp. | `<\|tool_response>response:name{value:<\|"\|>...<\|"\|>}<tool_response\|>` | `str_token`/`etr_token` |
| Thinking   | `<\|channel>thought\n...<channel\|>` (Response)                            | `soc_token`/`eoc_token` |
| Think Signal | `<\|think\|>` (Prompt)                                                   | `think_token`           |

---

### 2. Gefundene und behobene Fehler

#### **26B-Template – 7 Tag-Fehler behoben:**

|Zeile(n)| Vorher                               | Nachher                           |
|--------|--------------------------------------|-----------------------------------|
|    3   | `<\|turn\|>system`                   | `<\|turn>system`                  |
|   14   | `<\|tool\|>`                         | `<\|tool>`                        |
|   21   | `<\|tool\|>`                         | `<tool\|>`                        |
|   47   | `<\|tool_response\|>`                | `<\|tool_response>`               |
|   49   | `<\|tool_response\|>`                | `<tool_response\|>`               |
|   58   | `<\|turn\|>user`                     | `<\|turn>user`                    |
| 72,89  | `<\|turn\|>model`                    | `<\|turn>model`                   |
|   76   | `<\|tool_call\|>...<\|tool_call\|>`  | `<\|tool_call>...<tool_call\|>`   |

#### **12B-Template – Komplett neu geschrieben:**

- **BOS-Token** hinzugefügt (Zeile 1)
- **Thinking-Mode** implementiert (`enable_thinking`-Parameter, `<\|think\|>`-Signal)
- **Tool-Declarations** hinzugefügt (`<\|tool>...<tool\|>`)
- **tool_call_id-Matching** implementiert (statt `message.get('name')`)
- **Turn-Separator-Logik** aus 26B-Template übernommen (prev_was_model-Prüfung)
- **Content-Typ-Handling** (String vs. multipart `content[]`)

### 3. Python-Code-Änderungen

#### **custom_benchmark_v11.py:**

**a) Gemma-Config in MODEL_CONFIG ergänzt** (nach Zeile 136):
```python
"gemma": {
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 4096,
    "enable_thinking": False,
},
```

**b) `strip_thinking_tokens` erweitert** – erkennt jetzt beide Formate:
- Gemma 4: `<|channel>thought\n...<channel|>`
- Legacy: `<think>...</think>`

#### **run_benchmarks_v11.py:**

**a) `_is_gemma_model()`** hinzugefügt (analog zu `_is_gptoss_model`)

**b) `_get_lmeval_params()`** um Gemma-Branch ergänzt:
```python
if _is_gemma_model(model_key):
    return {"max_tokens": 4096, "temperature": 0.0, "top_p": 1.0, "until": []}
```

### 4. Unveränderte / Noch offene Punkte

| Punkt                              | Status      | Begründung                                                                                                                                   |
|------------------------------------|-------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `enable_thinking=False`            | Absichtlich | Für Code-Benchmarks (DS1000, CoderEval) ist Thinking kontraproduktiv. Für Reasoning-Tasks (MathQA, MMLU-Pro) kann auf `True` gesetzt werden. |
| Kein `reasoning_content`-Streaming | Akzeptiert  | Gemma 4 liefert Thinking in `<\|channel>thought\n...<channel\|>` im `content`-Feld – wird von `strip_thinking_tokens` korrekt extrahiert.    |
| lm_eval `--apply_chat_template`    | Akzeptiert  | lm_eval nutzt HuggingFace-eigenes Template (im Tokenizer), was dem offiziellen Format entspricht.                                            |
                                                        Das MiniJinja-Template wird nur in der Custom-Pipeline verwendet.                                                                         |
| Kein `_is_gemma_model` in `main()` | Akzeptiert  | Gemma wird nicht als Reasoning-Modell klassifiziert (Timeout ×2). Bei Bedarf kann `enable_thinking=True` in der Config gesetzt werden –      |
                                                        dann sollte auch `reasoning=True` in der Pipeline gesetzt werden.                                                                         |

### 5. Empfehlungen für zukünftige Verbesserungen

1. **Gemma-4-19B-Template**: Prüfen ob auch ein Jinja-Template für die 19B-Variante benötigt wird
2. **Thinking-parameterisierbar machen**: Per CLI-Flag (`--thinking`) oder per Benchmark-Konfiguration, sodass MathQA/MMLU-Pro mit `enable_thinking=True` laufen können
3. **Tool-Use-Pipeline**: Die Agentic-Pipeline (`tool_eval_bench`) nutzt eigene Chat-Templates – Konsistenz mit den Gemma-Templates prüfen
4. **Context-Length**: Gemma 4 unterstützt 1M Token – prüfen ob `model_max_length` in LM Studio korrekt konfiguriert ist

---
## Gemma-4-19B-Template
The 19B model (gemma-4-19b-a4b-it-reap-i1) uses gemma4 architecture (same as 26B). The template file gemma4-26b-template_minijinja.jinja is the correct template format for all Gemma 4 models. 
I'll copy it as a reference for 19B.

