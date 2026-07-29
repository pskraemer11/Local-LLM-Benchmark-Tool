# Gemma-4 – Konsolidierte Modell-Hinweise

> Stand: 29.07.2026 
> Quellen: 8 Dokumente aus `doc-git/Modell Specific Hints/`,
> `doc-git/Jinja-Chat-Templates/`, `doc-git/model_registry.yaml`, `doc-git/Architecture-and-Flow.md`

---
## Capabilities

- **Reasoning:** All models in the family are designed as highly capable reasoners, with configurable 
                [thinking modes](https://ai.google.dev/gemma/docs/capabilities/thinking).
- **Extended Multimodalities:** Processes Text, [Image](https://ai.google.dev/gemma/docs/capabilities/vision/image) with variable aspect ratio and resolution support (all models), 
                [Video](https://ai.google.dev/gemma/docs/capabilities/vision/video), and [Audio](https://ai.google.dev/gemma/docs/capabilities/audio) (featured natively on the E2B, E4B and 12B models).
- **Increased Context Window:** Small models feature a 128K context window, while the medium models support 256K.
- **Enhanced Coding \& Agentic Capabilities:** Achieves notable improvements in coding benchmarks alongside built-in 
                [function-calling support](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4), powering highly capable autonomous agents.
- **Native System Prompt Support:** Gemma 4 introduces built-in support for the system role, enabling more structured and controllable conversations.
- **[Multi-Token Prediction] (https://ai.google.dev/gemma/docs/mtp/overview)** 


## 1. Modellvarianten in der Registry

| Variante                            | Publisher    | Quant(s)    | Architektur            | Besonderheit                  |
|-------------------------------------|--------------|-------------|------------------------|-------------------------------|
| `gemma-4-e4b`                       | google       |   –         | Gemma-4 MoE (PLE)      | Embedding-Modell?             |
| `gemma-4-12b-qat@q4_0`              | google       | Q4_0        | Gemma-4 (12B) Unified  | QAT, Audio+Video nativ        |
| `gemma-4-19b-a4b-it-reap-i1@q4_k_s` | mradermacher | Q4_K_S      | Gemma-4 MoE            | REAP-komprimiert, 18 Experts  |
| `gemma-4-26b-a4b-it-quat@q4_0`      | google       | Q4_0        | Gemma-4 MoE            | QAT-gewichtet                 |
| `google_gemma-4-26b-a4b-it@q3_k_s`  | bartowski    |Q3_K_S,IQ4_XS| Gemma-4 MoE            | lm_eval=0%-Problem            |
| `gemma-4-26b-a4b-it@iq4_xs`         | google       | IQ4_XS      | Gemma-4 MoE            | Original Google               |
| `gemma-4-26b-a4b-it-ud@iq3_s`       | unsloth      | IQ3_S       | Gemma-4 MoE            | UD-Version                    |
| `gemma-4-26b-a4b-it-i1`             | mradermacher | IQ4_XS      | Gemma-4 MoE            | i1-Quant                      |
| `gemma-4-31b.i1`                    | mradermacher | IQ3_M       | Gemma-4 Dense          | 31B dense                     |

Alle Gemma-4 IT-Modelle haben `reasoning: thinking` und verwenden `blueprint: gemma_reasoning`.

---

## 2. KV-Cache: KEINE Quantisierung (f16 zwingend)

**Regel:** Bei allen Gemma-4-Modellen MUSS der KV-Cache auf `f16` gesetzt werden – sowohl K als auch V.

- `k_cache: f16` (Default wäre `q8_0`)
- `v_cache: f16` (Default wäre `iq4_nl`)

**Begründung:** Gemma-4 verwendet eine spezielle KV-Cache-Struktur bzw. Attention-Mechanik, die keine quantisierte KV-Cache-Darstellung unterstützt. 
                Wird der KV-Cache quantisiert (z. B. `q8_0`), **lädt das Modell nicht** oder liefert inkorrekte Ergebnisse.

**Auswirkung auf VRAM:** `f16` = 2 Bytes/Element (vs. `q8_0` = 1.0, `q4_0` = 0.5). Der KV-Cache belegt daher theoretisch doppelt bis viermal so viel VRAM wie bei quantisierten Modellen. 
                Die MoE Architektur mindert das teilweise wieder. Durch die "unified KV-Cache" EInstellung in LMS (llama.cpp) kann ebenfalls gegen gewirkt werden.
                Dies ist bei der überschläglichen Berechnung von `context_length` und `useUnifiedKvCache` bereits berücksichtigt.

Alle 9 Gemma-4-Einträge in der `model_registry.yaml` haben korrekt `k_cache: f16` und `v_cache: f16` gesetzt.

---

## 3. System Prompt

### 3.1 Offizielles Format (Google DeepMind)

Gemma-4 IT-Modelle verwenden ein strukturiertes Tokensystem (`<|turn|>`, `<|think|>`, etc.). Der System-Prompt wird im Chat-Template verarbeitet.

### 3.2 Eigene Blueprint-Tags – NICHT in Chat-Template

Die Datei `Gemma-4 - System Prompt Example (ungeprüft).txt` enthält custom XML-Tags:

```
<role>...</role>
<thinking>...</thinking>
<code>...</code>
<math>...</math>
<output>...</output>
```

**Bewertung:** Diese Tags sind **nicht** Teil des offiziellen Gemma-4-Tokenizer-Vokabulars. 
Sie sind weder als `sot_token`, `eot_token` noch als sonstige Kontrolltokens registriert. 
Die Tags gehören in das **Blueprint-System** (`gemma_assistant`/`gemma_reasoning`) und werden als **reiner Text im LM Studio System Prompt Field** abgelegt. 

Sie **dürfen nicht** in das Jinja-Chat-Template eingebaut werden – das Template verarbeitet ausschließlich die offiziellen Tokens (`<|turn>`, `<|think|>`, `<|tool>`, `<|channel>`, etc.).

### 3.3 System Prompt Parameter (empfohlen)

| Parameter                                                 | Wert                               | Begründung                        |
|-----------------------------------------------------------|------------------------------------|-----------------------------------|
| `enable_thinking`                                         | `false` (Code), `true` (Reasoning) | Steuerung per Blueprint/Benchmark |
| Keine Thinking-Tags im Prompt bei `enable_thinking=False` |           –                        | Sonst ignoriert Gemma das Flag    |

---

## 4. Chat-Template (Jinja)

### 4.1 Verwendete Templates

| Modell             | Template-Datei                        |
|--------------------|---------------------------------------|
| 12B (QAT)          | `gemma4_12b_template_minijinja.jinja` |
| 19B (REAP)         | `gemma4-19b-template_minijinja.jinja` |
| 26B (alle Quantis) | `gemma4-26b-template_minijinja.jinja` |
| 31B                | `gemma4-26b-template_minijinja.jinja` |

### 4.2 Token-Referenz (laut Technical Report Appendix Table 11)

| Funktion | Token |
|-----------------------------------|-------------------------------------------------------|
| Turn-Start (System/User/Model)    | `<|turn>role\n`                                       |
| Turn-Ende                         | `<turn|>`                                             |
| Thinking-Signal (Prompt-Seite)    | `<|think|>`                                           |
| Thinking-Trace (Response-Seite)   | `<|channel>thought\n...<channel|>`                    |
| Tool-Deklaration                  | `<|tool>declaration:name{...}<tool|>`                 |
| Tool-Call                         | `<|tool_call>call:name{...}<tool_call|>`              |
| Tool-Response                     | `<|tool_response>response:name{...}<tool_response|>`  |
| BOS                               | `bos_token` (per Tokenizer)                           |

vergleiche "Technischer Report Gemma-4" pdf von Google DeepMind, Appendix, Seite 17.

### 4.3 Template-Divergenz (KRITISCH – Stand 13.07.)

Drei Generationen existieren parallel:

1. **GGUF-eingebettet** (Original im `tokenizer_config.json`) – 270-Zeilen-Makroversion
2. **Hub-Jinja-Override** (`~/.lmstudio/hub/models/google/*.jinja`) – **autoritative Quelle**
3. **doc-git-Kopien** – teilweise veraltet (unconditionales `<|think|>`, `<|channel>thought` enthalten)

**Empfohlene Aktion:** doc-git-Kopien regelmäßig mit Hub-Overrides synchronisieren.

### 4.4 `enable_thinking`-Steuerung im Template

Das Template steuert Thinking über:

```jinja
{%- if enable_thinking is defined and enable_thinking -%}
    {{- '<|think|>\n' -}}
{%- endif -%}
```

- Wird `enable_thinking` auf `false` gesetzt, erscheint **kein** `<|think|>`-Token im Prompt.
- Bei `enable_thinking=True` wird `<|think|>` in den System-Turn eingefügt.
- **Bekanntes Problem (11.07.):** Manche Gemma-ConFig-Instanzen ignorieren `enable_thinking=False` – Workaround: System-Prompt-Override "Do NOT use thinking or reasoning. Answer directly without `<|channel>thought` tags."

---

## 5. Thinking / Reasoning-Effort

### 5.1 Steuerungsmechanismen

| Methode | Wirkung | Einsatz |
|---|---|---|
| `enable_thinking: bool` in JSON-Config (via `extra_body`) | `<|think|>` im Prompt | Code-Benchmarks: `false`; Reasoning: `true` |
| LM Studio GUI: "Enable Thinking" | Gleicher Effekt | Manuelle Konfiguration |
| CLI `--no-think` (tool-eval-bench v2.0.7) | Setzt `enable_thinking=false` | Agentic Pipeline |
| System-Prompt-Override (falls Config ignoriert) | Textuelles Verbot | Notfall-Workaround |

### 5.2 Empfehlung nach Benchmark-Typ

| Benchmark-Typ | `enable_thinking` | Begründung |
|---|---|---|
| DS1000, CoderEval, Coding-Aufgaben | `false` | Thinking kostet Tokens + Zeit, bringt keinen Vorteil |
| MathQA, MMLU-Pro, GPQA | `true` | Reasoning verbessert Genauigkeit |
| Agentic (BFCL) | `false` | Klare Tool-Calls, kein Thinking nötig |
| Generische Chat-Aufgaben | `false` | Direkte Antworten bevorzugt |

### 5.3 Thinking-Trace-Extraktion

Gemma-4 liefert Thinking im `content`-Feld, nicht als `reasoning_content` (OpenAI-Format). Die Funktion `strip_thinking_tokens()` erkennt beide Formate:

- Gemma-4: `<|channel>thought\n...<channel|>`
- Legacy: `<think>...</think>`

Nach der Extraktion wird nur der Antwort-Text (ohne Thinking) in die Benchmark-Auswertung gegeben.

---

## 6. LM Studio Reasoning Parsing MUSS deaktiviert sein

**Wichtig:** LM Studio hat eine globale `reasoning.parsing`-Einstellung (Default: `enabled=true`), die `<think>`/`</think>`-Tags in die Response einfügt – **auch bei Modellen ohne natives Reasoning**. Dies stört die API-gesteuerte Steuerung und erzeugt unnötige Tokens.

**Empfehlung:** Für alle Modelle (inkl. Gemma-4) auf `false` setzen. Die Thinking-Steuerung erfolgt ausschließlich über `enable_thinking` im API-Call, nicht über die GUI.

**Konfiguration (pro Modell):**
```json
// ~/.lmstudio/.internal/user-concrete-model-default-config/<pub>/<model>/<model>.gguf.json
"llm.prediction.reasoning.parsing": {
  "enabled": false,
  "startString": "<think>",
  "endString": "</think>"
}
```

**GUI:** Chat Panel → "..." → Model Settings → "Reasoning Parsing" → Enabled aus.

---

## 7. Modellparameter (Temperatur u. a.)

### 7.1 Empfohlene Defaults (Code-Benchmarks)

| Parameter | Wert | Begründung |
|---|---|---|
| `temperature` | 0.0 | Deterministische Ausgabe für reproduzierbare Benchmarks |
| `top_p` | 1.0 | Kein Nucleus-Sampling |
| `max_tokens` | 4096 | Ausreichend für Code-Antworten |
| `until` | `[]` | Kein Stop-Token (Template steuert Ende) |

### 6.2 Reasoning-Aufgaben

| Parameter | Wert | Begründung |
|---|---|---|
| `temperature` | 0.0 – 0.3 | Minimales Sampling für stabile Reasoning-Ketten |
| `top_p` | 0.95 | Leichte Diversität bei mehreren Lösungswegen |
| `max_tokens` | 8192 | Längere Reasoning-Ketten möglich |

### 6.3 lm_eval-Parameter

```python
# In _get_lmeval_params():
{
    "max_tokens": 4096,
    "temperature": 0.0,
    "top_p": 1.0,
    "until": [],
    "apply_chat_template": True  # lm_eval nutzt HF-Tokenizer-Template
}
```

---

## 7. Sonstige Besonderheiten

### 7.1 Multi-Token Prediction (MTP)

Alle Gemma-4-Modelle haben dedizierte Draft-Modelle für Speculative Decoding:
- Benennung: `<target-model-id>-assistant`
- Vorteil: Deutlich schnellere Inferenz ohne Qualitätsverlust
- **Einschränkung (26B MoE):** Bei Batch-Size 1 kann MTP auf Hardware ohne gute Parallelisierung **geringere** Speedups liefern, da unterschiedliche Experten geladen werden müssen.

### 7.2 QAT-Modelle

Quantization-Aware Training (QAT) minimiert Qualitätsverlust bei Quantisierung:
- `-qat-q4_0-gguf` für LM Studio / llama.cpp (1 File)
- `-qat-w4a16-ct` für vLLM / SGLang
- `-qat-mobile-transformers` für Edge/Mobile

Offizielle HF-Collections: `collections/google/gemma-4-qat-q4-0`, `collections/google/gemma-4-qat-mobile`

### 7.3 Reasoning-Modelle: Timeout ×2

Gemma-4 19B und 26B werden als Reasoning-Modelle geführt (Thinking-Mode). In der Benchmark-Pipeline benötigen sie daher einen **Timeout-Faktor ×2**:

- `gemma-4-19b-A4B-it-REAP-i1` → Timeout ×2
- `gemma-4-26b-A4B-it` (alle Quantis) → Timeout ×2
- `gemma-4-12b-qat` → Timeout ×2 (Thinking-Mode-fähig)

Die Einstellung liegt in `model_manager.py`/`run_benchmarks.py` in der `reasoning_models`-Liste bzw. wird über `reasoning: thinking` in der Registry gesteuert.

### 7.4 Architekturdetails (MoE)

| Modell | Total | Aktiv | Ratio | Experten | Aktiv | Shared | Attention |
|---|---|---|---|---|---|---|---|
| 19B REAP | 19B | ~4B | 4.75:1 | 90 (pruned) | 8 | 1 | Hybrid Sliding/Full (30 Layer) |
| 26B A4B | 26B | ~4B | 4.75:1 | 128 | 8 | 1 | Hybrid Sliding/Full (30 Layer) |

### 7.5 Speicherbedarf (VRAM)

| Modell | BF16 | Q4_0 | f16 KV-Cache (pro Token) |
|---|---|---|---|
| 12B | 26.7 GB | 6.7 GB | ~3.5 MB/token (12B) |
| 26B A4B | 57.7 GB | 14.4 GB | ~2.3 MB/token (26B MoE) |
| 31B | 69.9 GB | 17.5 GB | ~4.2 MB/token (31B) |

KV-Cache in `f16` ist der dominierende VRAM-Faktor bei langen Kontexten.

### 7.4 Kontextlänge

| Modellgruppe | Max. Kontext |
|---|---|
| E2B, E4B | 128K Tokens |
| 12B, 26B A4B, 31B | 256K Tokens |

In LM Studio ist `model_max_length` zu prüfen (nicht automatisch aus GGUF gelesen). Die effektive Kontextlänge in der Registry wird über die VRAM-Formel berechnet (`context_length` in `model_registry.yaml`).

### 7.5 Template-Chronologie (Zeitstrahl)

```
02.07.   12B MiniJinja-Template erstellt
04.07.   Alle 3 Templates in doc-git/; 7 Tag-Korrekturen (<|turn|>system → <|turn>system)
04.07.   thinking parametrisierbar (CLI, extra_body)
05.07.   HTTP 500 durch doppelte GGUF-Instanz; enableThinking=false gesetzt
08.07.   Hub-Templates per Google-Docs aktualisiert (26B: gated <|think|>)
09.07.   12B-Template mit hub synchronisiert; Backup template-config-backups_20260709/
11.07.   Gemma ignoriert enable_thinking=False → System-Prompt-Override als Workaround
13.07.   Blueprint-System: gemma_assistant / gemma_reasoning
```

---

## 8. Benchmark-Performance (Stand 10.07.2026, SS=20)

Gewichtung: Coding 35% | Math 25% | Agentic 25% | Knowledge 15%

| Rang | Modell | VRAM | Overall | Coding | Knowledge | Math | Agentic |
|---|---|---|---|---|---|---|---|
| 1 | Gemma 4 26B UD@IQ3_S | 13.6 GB | **66%** | 70% | 73% | **55%** | 28% |
| 2 | Gemma 4 19B REAP@Q4_K_S | 11.3 GB | **55%** | 68% | 75% | 24% | 22% |
| 7 | Gemma 4 19B REAP (frühere Quant) | 12.5 GB | 50% | 60% | 62% | 28% | 77% |

Hinweis: Agentic-Score der 26B UD (28%) ist niedrig – für Agentic-Aufgaben sind andere Modelle (Devstral, Ministral) besser geeignet.

---

## 9. Fehlerquellen (Review-Erkenntnisse)

1. **Divergenz der Jinja-Templates** (GGUF vs. Hub vs. doc-git vs. JSON-Config) – alle 4 Generationen können parallel existieren.
2. **`promptTemplate` in JSON-Configs** – eingebettete Kopie des damaligen Templates kann Hub-Override überschreiben (LMS-Priorität unklar).
3. **`enable_thinking=False` wird ignoriert** (11.07.) – Workaround per System-Prompt-Override.
4. **lm_eval 0%-Problem** bei `bartowski/google_gemma-4-26b-a4b-it` – kein HF-Eintrag für lm_eval (nur GGUF).


## Links
permit responsible [commercial use](https://ai.google.dev/gemma/terms),
download Gemma 4 models from [Hugging Face](https://huggingface.co/collections/google/gemma-4).

For more technical details on Gemma 4, see the
[Model Card](https://ai.google.dev/gemma/docs/core/model_card_4) 
and
=> [Technical Report](https://goo.gle/Gemma4Report).


