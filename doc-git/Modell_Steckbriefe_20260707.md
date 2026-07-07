# Modell-Steckbriefe (LM Studio, Stand 30.06.2026)

**Hardware:** AMD Ryzen 7 (8 Kerne) | NVIDIA RTX 5070 Ti (16 GB VRAM) | Windows 11

## Legende

| Symbol         | Bedeutung                                                         |
|--------------- |-------------------------------------------------------------------|
| **Dense**      | Alle Parameter pro Token aktiv                                    |
| **MoE**        | Mixture-of-Experts – nur Subset aktiv; passt besser in 16 GB VRAM |
| **Reasoning**  | Explizite Chain-of-Thought vor Antwort; benötigt mehr Zeit/VRAM   |
| **Vision/OCR** | Bild-/Dokumentverarbeitung; von Benchmarks ausgeschlossen         |
| **Excluded**   | Von Benchmark-Auswahl ausgeschlossen (OCR/Vision/Embedding)       |
| **✅ LM**     | Geeignet für lokale LLM-Benchmarks                                |
| **⚠️ LM**     | Bedingt geeignet (z.B. nur mit Quantisierung)                     |

** konservative Formel KV-Cache (pro Slot):** `context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (Ergebnis in MB), nähere Erläuterungen s.u.
LM Studio zeigt niedrigere Werte weil es auto-KV-Quantisierung anwendet (Q8/Q4 ≈ 1.5 Byte statt FP16 = 4 Byte), insbesondere bei VRAM-kritischen Modellen.
BEACHTE: Architekturabhängigkeit der KV-Quantisierungs-Empfindlichkeit, s.u.

"i1" im Dateinamen = Importance Matrix, nicht iMatrix-Quant.

---

## ========================= Zusammenfassung & Empfehlungen ========================================================== ##

## Beste Kandidaten für lokale LLM-Benchmarks (16 GB VRAM) – Stand 28.06.2026

|Rang| Modell                               | MoE  | VRAM    | Overall | Effizienz     | Stärke                                              |
|----|--------------------------------------|------|---------|---------|---------------|-----------------------------------------------------|
| 1  | *gemma-4-19b-a4b-it-reap-i1*         |  ja  | 11.3 GB |  *79%*  |   15.2 %p/h   | Bester Gesamtscore, stark in Coding+Agentic         |
| 2  | *qwen2.5-coder-14b-instruct*         | nein | 10.6 GB |  *71%*  |     —         | 100% HumanEval+/MBPP+, Coding-Sieger                |
| 3  | *phi-4 (unsloth)*                    | nein |  9.5 GB |  *64%*  |   18.0 %p/h   | Bester Coding-Score (93%), schnell                  |
| 4  | *granite-4.0-h-tiny*                 |  ja  |  7.4 GB |  *58%*  |  *60.5 %p/h*  | Extrem effizient, TOP 1 Effizienz, 1M Kontext       |
| 5  | *ernie-4.5-21b-a3b-pt*               |  ja  | 12.5 GB |  *57%*  |     —         | Nur 3B aktiv, starkes Coding+Math (Q4_K_M)          |

Hinweise: Results basieren auf SampleSize=10 (vollständig). Effizienz = Overall-Score / Laufzeit in Stunden. "--" = Modell hat keinen vollständigen 10-Pipeline-Durchlauf (fehlende Benchmarks).
Neue Benchmark-Runs mit SampleSize=100 => Tabelle aktualisieren!


###### MoE-Modelle (besonders VRAM-effizient) -  Architektur-Parameter ######

| Modell                          | Total | Aktiv | Faktor  | Experten/Layer              | Top-k (aktiv)          | Shared| Besonderheit                                                              |
|---------------------------------|-------|-------|---------|-----------------------------|------------------------|-------|---------------------------------------------------------------------------|
| deepseek-coder-v2-lite-instruct | 16B   |  2.4B |  6.7:1  |           8                 |    2                   | Nein  | DeepSeekMoE-Framework; 40 Layer; 128K Kontext                             |
| granite-4.0-h-tiny              |  7B   |  1B   |  7:1    |          64                 | 6 (4 routed + 2 shared)|  2    | Hybrid Mamba2+Attention (9:1); 4 von 40 Layern mit KV-Cache               |
| lfm2.5-8b-a1b                   |  8.3B |  1.5B |  5.5:1  |          32                 |    4                   | Nein  | Hybrid Conv+GQA (3:1); Reasoning-Modell; 6 Attention-Blöcke               |
| lfm2-24b-a2b-reap-i1            | 24B   |  2.3B | 10.4:1  |          64                 |    4                   | Nein  | Hybrid Conv+GQA (3:1); 40 Layer (10 Attention); REAP-compressed           |
| ernie-4.5-21b-a3b-pt            | 21B   |  3B   |  7:1    |   64 (Text) + 64 (Vision)   |    6 (+2 shared)       |  2    | Multimodal Heterogeneous MoE; 28 Layer; Text+Vision-Experten getrennt     |
| qwen3-coder-reap-25b-a3b-i1     | 25B   | ~3B   |  8.3:1  |  103 (REAP-pruned from 128) |    8                   | Nein  | Qwen3-Architektur; 48 Layer; 262K Kontext; REAP-pruned von 30B            |
| qwen3.6-28b-reap-i1             | 28B   | ~3B   |  9.3:1  |  205 (REAP-pruned from 256) |    8 (+1 shared)       |  1    | Hybrid Gated DeltaNet + Attention; 40 Layer; originale 256 Experten/Layer |
| qwen3-30b-a3b-python-coder      | 30.5B |  3.3B |  9.2:1  |         128                 |    8                   | Nein  | Qwen3-MoE; 48 Layer; Python-spezialisiert; 262K Kontext                   |
| gemma-4-19b-a4b-it-reap-i1      | 19B   | ~4B   |  4.75:1 |   90 (REAP-pruned from 128) |    8 (+1 shared)       |  1    | Hybrid Sliding/Full Attention; 30 Layer; ursprünglich 128 Experten/Layer  |
| gemma-4-26b-a4b                 | 26B   | ~4B   |  4.75:1 |         128                 |    8 (+1 shared)       |  1    | Hybrid Sliding/Full Attention; 30 Layer                                   |  
| gpt-oss-20b                     | 20.9B |  3.6B |  5.8:1  |          32                 |    4                   | Nein  | MXFP4-Quant. der MoE-Gewichte; 24 Layer; Alternating Dense+Banded Sparse Attention |


---

## Hinweise aus LM Studio Server-Logs (19.06.2026)

| Fundstelle  | Modell                          | Meldung                                             | Auswirkung                                                   |
|-------------|---------------------------------|-----------------------------------------------------|--------------------------------------------------------------|
| durchgehend | Alle Modelle                    | `thinking = 0` bei Chat-Template-Init               | LM Studio erkennt KEIN Modell als Reasoning/Thinking.        |
|                                                                                                     | "reasoning_content separation"-Einstellung hat keine Wirkung |

---

## Reasoning-Modelle (erhöhtes Timeout nötig); Aufzählung nicht abschliessend

| Modell                                | Erkannt über                      |Timeout-Faktor|
|---------------------------------------|-----------------------------------|--------------|
| acemath-7b-instruct                   | lt. Hersteller (Math CoT)         |      ×2      |
| gemma-4-19b-a4b-it-reap-i1            | Gemma-4-Familie (Thinking-Mode)   |      ×2      |
| gemma-4-26b-a4b-it                    | Gemma-4-Familie (Thinking-Mode)   |      ×2      |
| lfm2.5-8b-a1b                         | lt. Hersteller (kein auto-detect) | ×2 (manuell) |
| magistral-small-24b-2509              | Modell-Steckbrief, s.o.           |       ?      |
| ministral-3-14b-reasoning-2512        | Name enthaelt "reasoning"         |      ×2      |
| nemotron-14b-opencode-reasoning       | Modell-Steckbrief, s.o.           |       ?      |
| numinamath-7b-cot                     | Modell-Steckbrief, s.o.           |       ?      |
| qwen3-coder-reap-25b-a3b              | Qwen3-basiert (Thinking-Mode)     |      ×2      |
| qwen3.6-27b                           | lt. Hersteller (Thinking-Mode)    | ×2 (manuell) |
| qwen3.6-28b-reap-i1                   | log in LM Studio                  |      -       |


---

## LM Studio Reasoning-Parsing (2026-07-07)

**Betrifft: ALLE Modelle**

LM Studio hat eine `reasoning.parsing`-Einstellung (Default: `enabled=true`) mit `<think>`/`</think>`-Tags. 
Diese veranlasst das Modell, vor jeder Antwort eine Gedankenkette in `<think>`-Blöcken zu produzieren – auch bei Modellen, die kein natives Reasoning im Training haben.

**Folge:** 300–500 Tokens zusätzlich pro Generation, hohe Latenz, unnötig bei Tool-Calling.

**Empfehlung:** Für alle Benchmark-Modelle auf `false` setzen.

**Konfiguration (pro Modell):**
```
C:\Users\<user>\.lmstudio\.internal\user-concrete-model-default-config\<publisher>\<model>\<model>.gguf.json
```
```json
"llm.prediction.reasoning.parsing": {
  "enabled": false,
  "startString": "<think>",
  "endString": "</think>"
}
```

**LM Studio GUI:** Chat Panel → "..." → Model Settings → "Reasoning Parsing" → Enabled aus.

**Zusätzlich:** 
`stopStrings` auf `["<|end_of_text|>", "<|endoftext|>"]` setzen, um die Generation exakt am EOS-Token zu stoppen. 
`contextLength` auf max. 16384 senken (reduziert KV-Cache-VRAM). Diese Einstellungen liegen in derselben JSON-Datei.

---

### CPU statt GPU-Usage, langsame Laufzeiten 

**Ursache: 
lms load ohne --gpu max lädt Modelle standardmäßig auf CPU. Die user-concrete-model-default-config-Dateien mit llm.load.llama.gpuOffloadLayers werden von der LM Studio Version nicht an llama.cpp durchgereicht 
 – der KV-Config-Stack übersetzt diese Keys nicht in n_gpu_layers.

Beweis aus den Logs: Jeder Modell-Load zeigte LlamaV4::load config: n_parallel=4 n_ctx=16384 kv_unified=true – nie ein n_gpu_layers. Load dauerte <2s (RAM-only). Erst mit --gpu max (47s, 11,71 GiB VRAM) wurde die GPU genutzt.

**Fix: 
model_manager.py:172 – --gpu max zum lms load-Kommando hinzugefügt.

**Auswirkungen auf den Benchmark: 
Ab jetzt lädt jedes Modell mit GPU-Beschleunigung. Die anderen Änderungen (gpuStrictVramCap: false, contextLength: 8192 in der Config) bleiben bestehen, sind aber sekundär.

Einziger Vorbehalt: Falls ein Modell nicht vollständig in den 16 GB VRAM passt, kann --gpu max fehlschlagen. In dem Fall müsste man --gpu 0.8 oder einen niedrigeren Wert verwenden. 
Für Granite 4.1 30B Q3_K_S passt es (laut Estimate 12,36 GiB).


######## KV-Cache und Slots #########

## KV-Cache Quantisierung (größter Hebel)
Einstellbar sowohl in der LM Studio GUI (Hardware-Tab, Modell-Konfiguration → "Cache Quantization Type") als auch über das Python SDK:
```python

# Python SDK (lmstudio>=1.4.1)
model = lms.llm("modell-key", config={
    "llamaKCacheQuantizationType": "q8_0",   # K-Cache = 1 Byte/value (FP16=2)
    "llamaVCacheQuantizationType": "q4_0",   # V-Cache = 0.5 Byte/value
})
```
- **Empfehlung für die meisten Modelle:** `Q8_K + Q4_V` spart ~62.5% KV-VRAM
- **Empfehlung für Llama/Mistral/Cohere (24B+):** Symmetric `turbo3/turbo3` möglich → 5.1× Kompression bei +3.6–11.4% PPL
- **Achtung Qwen2.5:** Symmetrisches `q4_0` für K+V ist **katastrophal** (PPL >1000). Asymmetrisch `q8_0-K + q4_0-V` ist dagegen safe (+0.26% PPL bei 61% KV-Ersparnis). 
      Qwen3+ ist robuster – selbst `q4_0` K+V ist nutzbar (KL <0.12).
- **Achtung Gemma 4:** Sehr sensitiv auf KV-Quantisierung (`q8_0` schon KL 0.1–0.38). FP16+FP16 empfohlen.
- LM Studio <1.4.1 hatte einen Python-SDK-Bug (falsches Config-Key-Mapping). GUI ging ab v0.3.7 (Jan 2025).

**Hintergrund (Asymmetric K/V):** Der K-Cache bestimmt das Attention-Routing via Softmax – kleine Fehler werden exponentiell verstärkt. Der V-Cache skaliert linear. 
 Daher: K-Cache in hoher Präzision halten (q8_0 oder FP16), V-Cache aggressiv quantisieren (q4_0/turbo3). Das gilt besonders für Qwen2.5 und Modelle mit Q4_K_M-Gewichten.


################### Modellbeschreibungen (alphabetisch) #####################

### acemath-7b-instruct (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | NVIDIA                                                            |
| **Architektur**                   | Dense (Qwen2-Basis)                                               |
| **Reasoning**                     | **Ja** (Chain-of-Thought)                                         |
| **Param. Total / Active**         | 7.6B (100%)                                                       |
| **Quantisierung/Modellgröße**     | Q8_0 (7.54 GB)                                                    |
| **Kontextlänge** (token)          | 32K (original)                                                    |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (7.5 GB)                                                     |
| **Timeout ×2**                    | ✅ Aktivieren (Reasoning)                                          |
| **Benchmark-Typ**                 | Math (spezialisiert)                                              |
| **Lizenz**                        | CC-BY-NC-4.0                                                      |
| **Einschätzung**                  | SFT auf Qwen2.5-Math-Basis, spezialisiert auf englische Mathe-Aufgaben |

**Architektur-Hinweis:** Qwen2-Architektur, GQA (Grouped-Query Attention), SwiGLU, RMSNorm. 28 Layer, 28 Query-Heads, 4 KV-Heads.

**Offizielle Benchmarks (Hersteller):** MATH 500: 92.5%, AIME 2024: 46.7%, OlympiadBench: 42.5%. Spezialisiert auf englische Mathe-Aufgaben mit Chain-of-Thought.
**Achtung**: für allgemeine Coding-/Knowledge-Benchmarks ggf. unterdurchschnittlich.

Paper: https://arxiv.org/abs/2412.15084
HF: https://huggingface.co/nvidia/AceMath-7B-Instruct

---

### codegemma-7b-it

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google DeepMind                                                   |
| **Architektur**                   | Dense (Gemma, decoder-only Transformer, MHA)                      |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 8.5B (100%)                                                       |
| **Quantisierung/Modellgröße**     | Q8_0 (9.1 GB)                                                     |
| **Kontextlänge** (token)          | 8.192 (8K)                                                        |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (9.1 GB)                                                    |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Gemma Terms (bedingt kommerziell)                                 |
| **Einschätzung**                  | Google CodeGemma 7B IT. Älter (04/2024) aber solide. HumanEval 56.1, MBPP 54.2. |

HumanEval: 56.1 | MBPP: 54.2 | GSM8K: 41.2 | MATH: 20.9 | MMLU: ~56

HF: https://huggingface.co/google/codegemma-7b-it
LMS: https://lmstudio.ai/models/codegemma-7b-it

---

### codellama-13b-instruct (13B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Meta                                                              |
| **Architektur**                   | Dense (Llama)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 13B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q8_0 (13.9 GB) / Q6_K (10.7 GB)                                   |
| **Kontextlänge** (token)          | 16K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Nur Q6_K knapp (10.7 GB + KV-Cache)                           |
| **Benchmark-Typ**                 | Coding                                                            |
| **Einschätzung**                  | Meta, spezialisiert auf Code-Synthese, Infilling, Chat. Veraltet (2023) |

---

### codellama-13b-python (13B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Meta                                                              |
| **Architektur**                   | Dense (Llama, Python-spezialisiert)                               |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 13B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (10.7 GB)                                                    |
| **Kontextlänge** (token)          | 16K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (10.7 GB)                                                   |
| **Benchmark-Typ**                 | Coding (Python)                                                   |
| **Einschätzung**                  | Python-spezialisierte CodeLlama-Variante. Veraltet (2023).        |

---

### deepseek-coder-33b-instruct (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | DeepSeek AI                                                       |
| **Architektur**                   | Dense (Llama)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 33B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q3_K_S (13.2 GB)                                                  |
| **Kontextlänge** (token)          | 16K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (13.2 GB + KV-Cache)                                     |
| **Benchmark-Typ**                 | Coding                                                            |
| **Lizenz**                        | DeepSeek License                                                  |
| **Einschätzung**                  | 33B dense = hohe Code-Qualität. Veraltet (2023).                  |

**Architektur-Hinweis:** LlamaForCausalLM-Architektur, GQA (Grouped-Query Attention). Ausschließlich auf Code trainiert (2T Tokens).

---

### deepseek-coder-6.7b-instruct (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | DeepSeek AI                                                       |
| **Architektur**                   | Dense (Llama)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 6.7B (100%)                                                       |
| **Quantisierung/Modellgröße**     | Q8_0 (6.85 GB)                                                    |
| **Kontextlänge** (token)          | 16K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (6.9 GB)                                                    |
| **Benchmark-Typ**                 | Coding                                                            |
| **Lizenz**                        | DeepSeek License                                                  |
| **Einschätzung**                  | 6.7B dense, Q8 viel Reserve. Veraltet (2023).                     |

---

### deepseek-coder-v2-lite-instruct (16B / 2.4B active) (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | DeepSeek AI                                                       |
| **Architektur**                   | **MoE** (DeepSeekMoE, 8 Experts, Top-2)                           |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 16B / 2.4B                                                        |
| **Layers / Heads**                | 40                                                                |
| **Experts**                       | 8 (kein Spielraum)                                                |
| **Quantisierung/Modellgröße**     | Q4_K_M (9.8 GB)                                                   |
| **Kontextlänge** (token)          | 128K                                                              |
| **V-Cache-Quant**                 | Q8_0                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (9.8 GB + KV-Cache Q8 => 12.3 GB)                           |
| **Timeout ×2**                    | Nein                                                              |
| **Benchmark-Typ**                 | Coding                                                            |
| **KV-Cache**                      | ~160 KB/Tok.                                                      |
| **Einschätzung**                  | DeepSeekMoE-Framework, 40 Layer, 128K Kontext. Nur 8 Experten + Top-2 aktiv = effizient. Spezialisiert auf Coding.|

**Architektur-Hinweis:** DeepSeekMoE mit 8 Experten/Layer, Top-2 aktiv. Keine Shared Experts.
HF: https://huggingface.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct

---

### devstral-small-2-24b-instruct-2512 - 2 Varianten: 

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (multimodal, Mistral-basiert)                               |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 24B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q3_K_S (12.2 GB)                                                  |
| **Kontextlänge** (token)          | max 392K / hier: 98K                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ knapp (12.2 GB + KV-Cache Q5_1/IQ4_NL => VRAM 15.4 GB + shared RAM 2.2 GB)  |
| **Benchmark-Typ**                 | Coding + MC (Vision-Tests ausgeschlossen)                         |
| **Lizenz**                        | Mistral MNPL (lizenzpflichtig)                                    |
| **Einschätzung**                  | Vision-Text-Modell. Nur Coding/Math-Benchmarks.                   |

**Offizielle Daten:** Devstral Small 2 ist ein multimodales Modell (Text + Vision) von Devstral (eigenständiges AI-Unternehmen, nicht Mistral AI). Basiert auf Mistral-Architektur. 392K Kontextfenster. 80+ Programmiersprachen.

---

### ernie-4.5-21b-a3b-pt

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Baidu                                                             |
| **Architektur**                   | **MoE** (64 Text + 64 Vision, Top-6 + 2 Shared)                   |
| **Reasoning**                     | Nein (non-thinking)                                               |
| **Param. Total / Active**         | 21.9B / 3B                                                        |
| **Layers / Heads**                | 28 / 20 (4)                                                       |
| **Quantisierung/Modellgröße**     | Neu: PT IQ4_NL (12.5 GB) / alt: Q4K_M (13.5 GB)                   |
| **Kontextlänge** (token)          | 131K                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.5 GB + KV-Cache Q8/Q5_1 => 14.3 GB rechn. / 15.6 GB faktisch)  |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 56 KB/Tok. -> bei 131k Kontext => +7.5 GB rechn. (mit KV-Quant)   |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Nur 3B aktiv → schnell trotz 21B total. Embedding+Attention in BF16. Multilingual (EN/ZH). |

Note: "-Paddle" models use PaddlePaddle weights, while "-PT" models use Transformer-style PyTorch weights.

**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

**key features Ernie-4.5:**
- Multimodal Heterogeneous MoE Pre-Training
- Scaling-Efficient Infrastructure: "We propose a novel heterogeneous hybrid parallelism and hierarchical load balancing strategy for efficient training of ERNIE 4.5 models. 
By using intra-node expert parallelism, memory-efficient pipeline scheduling, FP8 mixed-precision training and finegrained recomputation methods, we achieve remarkable pre-training throughput. 
For inference, we propose multi-expert parallel collaboration method and convolutional code quantization algorithm to achieve 4-bit/2-bit lossless quantization. 
Furthermore, we introduce PD disaggregation with dynamic role switching for effective resource utilization to enhance inference performance for ERNIE 4.5 MoE models.

- Modality-Specific Post-Training: "Our LLMs are optimized for general-purpose language understanding and generation. The VLMs focuses on visuallanguage understanding and supports both thinking and non-thinking modes."

Quelle: https://huggingface.co/baidu/ERNIE-4.5-21B-A3B-PT

---

### essentialai/rnj-1

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Essential AI                                                      |
| **Architektur**                   | Dense (Gemma3)                                                    |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 8.3B (100%)                                                       |
| **Quantisierung/Modellgröße**     | Q8_0 (8.84 GB)                                                    |
| **Kontextlänge** (token)          | 32K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (8.8 GB, mit KV Cache 10.9 GB)                              |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Foundation Model von Essential AI. Basierend auf Gemma3-Architektur. 100% MBPP+, gut für Coding. |

**Architektur-Hinweis:** Gemma3ForCausalLM-Architektur. Apache-2.0-Lizenz. Essential AI wurde von Noam Shazeer (Transformer-Miterfinder) und Daniel De Freitas (ex-Google, LaMDA) gegründet.

**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### gemma-4-19b-a4b-it-reap-i1 - (REAP-pruned from Gemma-4-26B-A4B) 

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google DeepMind                                                   |
| **Architektur**                   | **MoE** (REAP-pruned from Gemma-4-26B-A4B)                        |
| **Reasoning**                     | Ja, see best practise                                             |
| **Param. Total / Active**         | 19B / 4B                                                          |
| **Experts**                       | 90 (REAP-pruned from 128) / 8 (+1 shared)                         |
| **Quantisierung/Modellgröße**     | neu: IQ4_NL (10.6 GB) / alt: Q4_K_S (11.34 GB)                    |
| **Kontextlänge** (token)          | max. 262K / hier Reduktion auf: 64k oder 98K                      |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Nein (10.6 GB + KV-Cache (ohne Quant) => 15.3 GB)             |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0 (Gemma 4 License)                                      |
| **Einschätzung**                  | REAP-compressed von 26B auf 19B, A4B ≈ 4B aktiv.                  |

**Wichtig: #Expertes auf 45, mit 90 (max) lädt das Modell nicht! & Keine KV-Quantisierung einstellen!!!**

**Achtung: keine KV-Cache Quantisierung!** 
Gemma-4 + MOE verträgt keine KV Quantisierung! Problem: Lt. LMS bei 262k Kontext => 32 GB für Modell+LV-Speicher => Kontextlänge reduzuieren

**Best practise: Thinking-Modus konfigurieren**
Im Vergleich zu Gemma 3 verwenden die Modelle die Standardrollen system, assistant und user. 

Verwenden Sie die folgenden Steuerungstokens, um den Denkprozess richtig zu verwalten:
    *Trigger Thinking*: Der Thinking-Modus wird aktiviert, indem das Token <|think|> am Anfang des System-Prompts eingefügt wird. 
        Wenn Sie die Funktion deaktivieren möchten, entfernen Sie das Token.
    *Standardgenerierung*: Wenn die Denkfunktion aktiviert ist, gibt das Modell seine interne Argumentation gefolgt von der 
        endgültigen Antwort in dieser Struktur aus: <|channel>thought\n[Interne Argumentation]<channel|>.
    *Deaktiviertes Denkverhalten*: Wenn das Denken für alle Modelle außer den E2B- und E4B-Varianten deaktiviert ist, generiert 
        das Modell weiterhin die Tags, aber mit einem leeren Denkblock: <|channel>thought\n<channel|>[Final answer]

https://ai.google.dev/gemma/docs/core/model_card_4?hl=de
https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4?hl=de

---

### gemma-4-26B-A4B-it (26B) - 2 Varianten: IQ3_S und qat-Q4_0 (qat-Variante wieder gelöscht, wg. schlechteren Scores)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google DeepMind                                                   |
| **Architektur**                   | Dense (Gemma 4) + **MoE**, Layers 40, Sliding Window 1024 Token   |
| **Reasoning**                     | Ja (optional per Thinking-Budget), see best practise              |
| **Param. Total / Active**         | 26.2B / active 3.8B                                               |
| **Experts**                       | 8 active / 128 total / 1 shared / in LMS eingestellt: 18          |
| **Quantisierung/Modellgröße**     | IQ3_S (13.6 GB) / Quat-Q4_0 (14.4 GB)                             |
| **Kontextlänge** (token)          | max. 256K / hier: 98K                                             |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp IQ3_S: (13.6 GB + KV-Cache) => VRAM 15.1 + shared RAM 2.0 GB) 
                                               qat-Q4_0: (14.4 GB + KV-Cache) => 14.0 + 0.5 GB)         |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0 (Gemma 4 License)                                      |
| **Einschätzung**                  | Größtes Gemma 4-MoE-Modell. Hybrid Attention (Sliding Window 1024 + Global). |

**Architektur-Hinweis:** 40 Layer, Hybrid Sliding/Full Attention mit Unified KV und p-RoPE. Vocabulary 262K, über 140 Sprachen.

**Achtung: keine KV-Cache Quantisierung!** 
Gemma-4 + MOE verträgt keine KV Quantisierung! Problem: Lt. LMS bei 262k Kontext => 32 GB für Modell+LV-Speicher => Kontextlänge reduzuieren

**Best practise: Thinking-Modus konfigurieren**
Im Vergleich zu Gemma 3 verwenden die Modelle die Standardrollen system, assistant und user. 

Verwenden Sie die folgenden Steuerungstokens, um den Denkprozess richtig zu verwalten:
    *Trigger Thinking*: Der Thinking-Modus wird aktiviert, indem das Token <|think|> am Anfang des System-Prompts eingefügt wird. 
        Wenn Sie die Funktion deaktivieren möchten, entfernen Sie das Token.
    *Standardgenerierung*: Wenn die Denkfunktion aktiviert ist, gibt das Modell seine interne Argumentation gefolgt von der 
        endgültigen Antwort in dieser Struktur aus: <|channel>thought\n[Interne Argumentation]<channel|>.
    *Deaktiviertes Denkverhalten*: Wenn das Denken für alle Modelle außer den E2B- und E4B-Varianten deaktiviert ist, generiert 
        das Modell weiterhin die Tags, aber mit einem leeren Denkblock: <|channel>thought\n<channel|>[Final answer]

https://ai.google.dev/gemma/docs/core/model_card_4?hl=de
https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4?hl=de

HF: https://huggingface.co/google/gemma-4-31B

---

### gemma-4-31b-i1 (31B) - lokal größtes Gemma-Modell nach Parametern (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google DeepMind                                                   |
| **Architektur**                   | Dense (Gemma 4), Layers 60, Sliding Window 1024 Token             |
| **Reasoning**                     | Ja (optional per Thinking-Budget), see best practise              |
| **Param. Total / Active**         | 30.7B (100%)                                                      |
| **Quantisierung/Modellgröße**     | IQ3_M (14.43 GB)                                                  |
| **Kontextlänge** (token)          | max. 256K / hier: 64K                                             |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14.4 GB + KV-Cache Quant. Q8/IQ4_NL => 21.7 GB)        |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0 (Gemma 4 License)                                      |
| **Einschätzung**                  | Größtes Gemma 4-Dense-Modell. Hybrid Attention (Sliding Window 1024 + Global). |

**Architektur-Hinweis:** 60 Layer, Hybrid Sliding/Full Attention mit Unified KV und p-RoPE. Vocabulary 262K, über 140 Sprachen.

**KV-Cache:** ~200 KB/Tok. bei FP16 → bei 256K Kontext ~51 GB (mit KV-Quant Q8/Q5 ~19 GB). Daher bei 16 GB VRAM nur mit stark reduzierte Kontextlänge betreibbar.

**Thinking-Modus konfigurieren**
Im Vergleich zu Gemma 3 verwenden die Modelle die Standardrollen system, assistant und user. 

Verwenden Sie die folgenden Steuerungstokens, um den Denkprozess richtig zu verwalten:
    *Trigger Thinking*: Der Thinking-Modus wird aktiviert, indem das Token <|think|> am Anfang des System-Prompts eingefügt wird. 
        Wenn Sie die Funktion deaktivieren möchten, entfernen Sie das Token.
    *Standardgenerierung*: Wenn die Denkfunktion aktiviert ist, gibt das Modell seine interne Argumentation gefolgt von der 
        endgültigen Antwort in dieser Struktur aus: <|channel>thought\n[Interne Argumentation]<channel|>.
    *Deaktiviertes Denkverhalten*: Wenn das Denken für alle Modelle außer den E2B- und E4B-Varianten deaktiviert ist, generiert 
        das Modell weiterhin die Tags, aber mit einem leeren Denkblock: <|channel>thought\n<channel|>[Final answer]

https://ai.google.dev/gemma/docs/core/model_card_4?hl=de
HF: https://huggingface.co/google/gemma-4-31B

---

### glm-4.6v-flash - (gelöscht, Ergebnise enttäuschend)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Zhipu AI (ZAI)                                                    |
| **Architektur**                   | **MoE** + Vision Encoder                                          |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | ~20B (Vision+Text)                                                |
| **Einschätzung**                  | Vision-Language-Modell. Von Benchmarks ausgeschlossen.            |

**Hinweis:** Vision/OCR-Modell → excluded von Benchmark-Auswahl.

---

### glm-4.7-flash-reap-23b-a3b-i1 (23B / 3B active) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Zhipu AI (ZAI)                                                    |
| **Architektur**                   | **MoE** (REAP-pruned, 205 Experten/Layer)                         |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 23B / 3B                                                          |
| **Layers / Heads**                | 40 / 32 Q / 4 KV                                                  |
| **Experts**                       | 205 (LMS: 128–205)                                                |
| **Quantisierung/Modellgröße**     | Q4_K_M (14.0 GB)                                                  |
| **Kontextlänge** (token)          | 131K                                                              |
| **V-Cache-Quant**                 | Q8_0 bei VRAM-Knappheit                                           |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14.0 GB + KV-Cache Q8 => 15.8 GB)                      |
| **Timeout ×2**                    | Nein                                                              |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | ~32 KB/Tok. (4 KV-Heads × 40 Layer Attention)                     |
| **Einschätzung**                  | GLM-4.7-Flash, REAP-compressed. Ähnliche Architektur wie Qwen3.6 MoE. 205 Experten von 256 pruned.|

**Architektur-Hinweis:** Hybrid Gated DeltaNet + Attention, 40 Layer.
HF: https://huggingface.co/ZAI-org/GLM-4.7-Flash-REAP-23B-A3B-I1

---

### google/gemma-4-12b (NEU) (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google DeepMind                                                   |
| **Architektur**                   | Dense (Gemma 4, multimodal), 30 Layer, Sliding Window 1024 Token  |
| **Reasoning**                     | Ja (optional per Thinking-Budget)                                 |
| **Param. Total / Active**         | 12B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q8_0 (12.8 GB)                                                    |
| **Kontextlänge** (token)          | max. 262K / hier: 98K                                             |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.8 GB + KV-Cache => 16.2 GB bei 98K)                |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0 (Gemma 4 License)                                      |
| **Einschätzung**                  | Gemma 4 Dense 12B. Q8_0 = hohe Präzision. Tool-Use-fähig. Multimodal (any-to-any). |

**Architektur-Hinweis:** 30 Layer, GQA (16 Q-Heads / 4 KV-Heads), SwiGLU, RMSNorm. Hybrid Sliding/Full Attention. Apache-2.0-lizenziert.

Quelle: https://ai.google.dev/gemma/docs/core/model_card_4
HF: https://huggingface.co/google/gemma-4-12B

---

### google_gemma-4-26b-a4b-it (Q3_K_S) - bartowski GGUF, gleiches Modell wie gemma-4-26b-a4b-it, andere Quantisierung

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google DeepMind (GGUF von bartowski konvertiert)                  |
| **Architektur**                   | Dense (Gemma 4) + **MoE**, Layers 40, Sliding Window 1024 Token   |
| **Reasoning**                     | Ja (optional per Thinking-Budget)                                 |
| **Param. Total / Active**         | 26.2B / active 3.8B                                               |
| **Experts**                       | 8 active / 128 total / 1 shared  / in LMS eingestellt: 18         |
| **Quantisierung/Modellgröße**     | Q3_K_S (14.4 GB)                                                  |
| **Kontextlänge** (token)          | max. 256K / hier: 98K                                             |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14.4 GB + KV-Cache)                                     |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0 (Gemma 4 License)                                      |
| **Einschätzung**                  | Bartowski-Konvertierung von Gemma 4 26B. In LMS fehlt passendes Template → lm_eval-Scores = 0%. |

**Template-Problem:** Dieses Modell (`google_gemma-4-26b-a4b-it`) hat keinen HuggingFace-Eintrag unter dem Publisher-Namen in LM Studio. Das korrekte Gemma-4-Template kann daher nicht automatisch zugewiesen werden. lm_eval-Benchmarks (ARC, HellaSwag, TruthfulQA, MathQA) liefern 0% Score. Agentic-Tests funktionieren (95%).

HF: https://huggingface.co/bartowski/Gemma-4-26B-A4B-It-GGUF

---

### gpt-oss-20b (20.9B / 3.6B active) (gelöscht)

| Eigenschaft                       | Wert                                                                              |
|-----------------------------------|-----------------------------------------------------------------------------------|
| **Hersteller**                    | Community (Open-Source GPT-4-Reproduktion)                                        |
| **Architektur**                   | **MoE** (24 Layer, Alternating Dense+Banded Sparse Attention, 32 Experts, Top-4)  |
| **Reasoning**                     | Nein                                                                              |
| **Param. Total / Active**         | 20.9B / 3.6B                                                                      |
| **Layers / Heads**                | 24                                                                                |
| **Experts**                       | 32 (LMS: 32 Standard)                                                             |
| **Quantisierung/Modellgröße**     | MXFP4 (12.1 GB)                                                                   |
| **Kontextlänge** (token)          | 128K                                                                              |
| **V-Cache-Quant**                 | Q8_0                                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.1 GB + KV-Cache => ~14.5 GB)                                         |
| **Timeout ×2**                    | Nein                                                                              |
| **Benchmark-Typ**                 | Coding + MC                                                                       |
| **KV-Cache**                      | ~128 KB/Tok. (Attention-Layer zählen)                                             |
| **Einschätzung**                  | Open-Source GPT-4-Architektur (Community-Projekt, nicht von OpenAI). MXFP4-Quant der MoE-Gewichte. 24 Layer mit abwechselnd Dense + Banded Sparse Attention.                                 |

**Architektur-Hinweis:** GPT-4-ähnliche Architektur (Community-Reproduktion). Banded Sparse Attention reduziert KV-Cache. Nicht zu verwechseln mit OpenAI GPT-4.
**Empfohlene Slots:** 4

---

### granite-4.0-h-tiny

| Eigenschaft                       | Wert                                                                          |
|-----------------------------------|-------------------------------------------------------------------------------|
| **Hersteller**                    | IBM                                                                            |
| **Architektur**                   | **Hybrid MoE** (Mamba2 + Transformer)                                         |
| **Reasoning**                     | Nein                                                                          |
| **Param. Total / Active**         | 6.9B / 1B                                                                     |
| **Experts**                       | 64 Experts, Top-6: 4 routed + 2 shared; lädt mit max 24 Experts               |
| **Quantisierung/Modellgröße**     | Q8_0 (7.4 GB)                                                                 |
| **Kontextlänge** (token)          | 1.048.576 (1M!)                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | Modell + Kontext x KV-Quant.Q8/Q5_1 => 11.6 GB gesamt                         |
| **Benchmark-Typ**                 | Coding + MC                                                                   |
| **KV-Cache**                      | 8 KB/Tok. -> bei 1M Kontext rechn. => +8 GB                                   |
| **Lizenz**                        | Apache-2.0                                                                    |
| **Einschätzung**                  | Extrem effizient: 1M Kontext, 1B aktiv. Hybrid-Architektur (9:1 Mamba2:Attention) |

**Experten-Problematik:** Bei vollem Context (1M) und `num_experts=64` verursacht `ggml_new_object: not enough space` einen Ladefehler (ca. 368 Bytes zu wenig). 
Workaround: `num_experts=16` via LM Studio Python SDK (`numExperts`) oder REST API setzen. Der Parameter ist nicht im GUI einstellbar. 
Bereits bei 16 Experten läuft das Modell stabil bei voller Kontextlänge.

**Architektur-Hinweis:** Hybrid MoE: nur 4 Attention-Layer (von 40), 36 Mamba2-Layer (kein KV-Cache)
**Hinweis:MambaCache/SSM-Modelle**: KV-Cache-Quantisierung kann zu Engine-Fehlern führen (`AttributeError: 'MambaCache' object has no attribute 'offset'`). 
  Workaround: KV-Quantisierung deaktivieren!

**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### granite-4.1-30b (NEU) - lokal größtes IBM-Modell (30B)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | IBM                                                               |
| **Architektur**                   | Dense, 60 Layer, Attention heads 32, KV-heads 8, SwiGLU, RoPE     |
| **Reasoning**                     | Nein (?) aber sehr geschwätzig, erzeugt viele Token               |
| **Param. Total / Active**         | 30B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q3_K_S (12.6 GB)                                                  |
| **Kontextlänge** (token)          | 131K, hier 49 k                                                   |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.6 GB + KV-Cache => 13.7 GB VRAM + 0.7 GB shared RAM)|
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | IBM Granite 4.1 30B. Dense. Tool-Use-fähig. erzeugt viele Token   |

**Architektur-Hinweis:** GQA (Grouped-Query Attention) mit 32 Q-Heads und 8 KV-Heads. Granite-Architektur (IBM). Apache-2.0-Lizenz.

Quelle: https://huggingface.co/ibm-granite/granite-4.1-30b-GGUF

---

### granite-4.1-8b

| Eigenschaft                       | Wert                                                                          |
|-----------------------------------|-------------------------------------------------------------------------------|
| **Hersteller**                    | IBM                                                                            |
| **Architektur**                   | **Dense**, 40 Layer, Attention heads 32, KV-heads 8, MLP: 12k SwiGLU, RoPE    |
| **Reasoning**                     | Nein                                                                          |
| **Param. Total / Active**         | 8B (100%)                                                                     |
| **Quantisierung/Modellgröße**     | Q8_0 (9.35 GB)                                                                |
| **Kontextlänge** (token)          | 131K (erweiterbar auf 512K)                                                   |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (9.4 GB) + 131 Kontext x KV-Quant. Q8_0/Q5_1 => 14.3 GB gesamt          |
| **Benchmark-Typ**                 | Coding + MC                                                                   |
| **KV-Cache**                      | 160 KB/Tok. -> bei 131k Kontext rechn. => 21 GB; mit KV-Quant Q8/Q5 => 8 GB   |
| **Lizenz**                        | Apache-2.0                                                                    |
| **Einschätzung**                  | Dense 8B schlägt Granite 4.0 MoE 32B auf vielen Benchmarks. Stark in Tool Calling |

**Architektur-Hinweis:** GQA (Grouped-Query Attention) mit 40 Query-Heads und 8 KV-Heads
**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

Granite-4.1-8B is a 8B parameter long-context instruct model finetuned from Granite-4.1-8B-Base using a combination of open source instruction datasets with permissive license and internally collected synthetic datasets. 
Granite 4.1 models have gone through an improved post-training pipeline, including supervised finetuning and reinforcement learning alignment, resulting in enhanced tool calling, instruction following, and chat capabilities.

Supported Languages: English, German, Spanish, French, Chinese u.a.m. 

Intended use: 
The model is designed to follow general instructions and can serve as the foundation for AI assistants across diverse domains, including business applications, as well as for LLM agents equipped with tool-use capabilities.

Capabilities:
Summarization, Text classification, Text extraction, Question-answering, Retrieval Augmented Generation (RAG), Code related tasks, Function-calling tasks, Multilingual dialog use cases, Fill-In-the-Middle (FIM) code completions

GitHub Repository: ibm-granite/granite-4.1-language-models
https://www.ibm.com/granite/docs/models/granite4-1

---

### januscoder-14b (14B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Unsloth / Janus                                                   |
| **Architektur**                   | Dense (Llama)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 14B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q4_K_M (9.2 GB)                                                   |
| **Kontextlänge** (token)          | 32K                                                               |
| **V-Cache-Quant**                 | Q8_0                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (9.2 GB + KV-Cache Q8 => 11.4 GB)                           |
| **Timeout ×2**                    | Nein                                                              |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | ~128 KB/Tok.                                                      |
| **Einschätzung**                  | Unsloth-optimierte Variante. Gute Coding-Ergebnisse bei niedrigem VRAM. |

**Empfohlene Slots:** 4

---

### lfm2-24b-a2b-reap-i1 (24B / 2.3B active) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Liquid AI                                                         |
| **Architektur**                   | **MoE** (64 Experts, Top-4, Hybrid Conv+GQA 3:1, REAP-pruned)     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 24B / 2.3B                                                        |
| **Layers / Heads**                | 40 (10 Attention)                                                 |
| **Experts**                       | 64 (LMS: 64 Standard)                                             |
| **Quantisierung/Modellgröße**     | IQ4_NL (13.8 GB)                                                  |
| **Kontextlänge** (token)          | 32K                                                               |
| **V-Cache-Quant**                 | Q8_0                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (13.8 GB + KV-Cache Q8 => 15.8 GB)                      |
| **Timeout ×2**                    | Nein                                                              |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | ~40 KB/Tok. (nur 10 Attention-Layer × 4 KV-Heads)                 |
| **Einschätzung**                  | Größeres Liquid-Modell. REAP-compressed. Hybrid Conv+GQA. IQ4_NL spart VRAM.|

**Architektur-Hinweis:** 40 Layer, 10 Attention + 30 Conv. 64 Experts, Top-4 aktiv.
**Empfohlene Slots:** 4

---

### lfm2.5-8b-a1b (8.3B / 1.5B active) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Liquid AI                                                         |
| **Architektur**                   | **MoE** 32 Experts, Top-4, Hybrid Conv+GQA 3:1, Reasoning-Modell  |
| **Reasoning**                     | **Ja**                                                            |
| **Param. Total / Active**         | 8.3B / 1.5B                                                       |
| **Experts**                       | 32 (LMS: 32 Standard)                                             |
| **Quantisierung/Modellgröße**     | Q8_0 (8.8 GB)                                                     |
| **Kontextlänge** (token)          | 32K                                                               |
| **V-Cache-Quant**                 | Q8_0                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (8.8 GB + KV-Cache Q8 => 10.8 GB)                           |
| **Timeout ×2**                    | ✅ Aktivieren (Reasoning)                                         |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | ~64 KB/Tok. (nur 6 Attention-Blöcke von 32)                       |
| **Einschätzung**                  | Liquid AI, Hybrid Conv+GQA. Nur 1.5B aktiv = extrem effizient.    |

**Architektur-Hinweis:** 32 Layer, davon 6 Attention-Blöcke mit KV-Cache, 26 Conv-Blöcke ohne KV-Cache. Hybrid-Architektur (3:1 Conv:Attention).
**Timeout ×2 notwendig** da Reasoning-Modell (laut Hersteller, kein auto-detect durch LM Studio).

---

### llama-3.1-13b-instruct (13B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Meta                                                              |
| **Architektur**                   | Dense (Llama 3.1)                                                 |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 13B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (10.7 GB)                                                    |
| **Kontextlänge** (token)          | 128K                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (10.7 GB + KV-Cache)                                     |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | Llama 3.1 13B. 128K Kontext. Agentic.                             |

---

### llama-3.3-8b-instruct (8B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Meta                                                              |
| **Architektur**                   | Dense (Llama 3.3)                                                 |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 8B (100%)                                                         |
| **Quantisierung/Modellgröße**     | Q8_0 (8.5 GB)                                                     |
| **Kontextlänge** (token)          | 8K                                                                |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (8.5 GB)                                                    |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | Llama 3.3, 8B. Agentic. Durch neuere Modelle abgelöst.            |

---

### magistral-small-24b-2506 (24B) - (gelöscht, älteres Modell ggü. 2509)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (Mistral)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 24B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q4_K_M (14.0 GB)                                                  |
| **Kontextlänge** (token)          | 24K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14 GB + KV-Cache)                                       |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | Mistral AI, 24B dense. Durch Magistral-Small 2509 ersetzt.        |

---

### magistral-small-24b-2509 (24B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (Mistral, Vision+Reasoning)                                 |
| **Reasoning**                     | **Ja**                                                            |
| **Param. Total / Active**         | 24B (100%)                                                        |
| **Quantisierung/Modellgröße**     | IQ4_NL / IQ4_XS / Q4_K_S                                          |
| **Kontextlänge** (token)          | 128K                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (IQ4_XS ~12 GB + KV-Cache)                              |
| **Benchmark-Typ**                 | Coding + MC (Vision-Tests ausgeschlossen)                         |
| **Einschätzung**                  | Mistral AI, Vision+Reasoning. 128K Kontext. Multilingual.         |

**Hinweis:** Vision-Modell → von Benchmark-Auswahl ausgeschlossen.

---

### mathstral-7b-v0.1 - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (Mistral)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 7B (100%)                                                         |
| **Quantisierung/Modellgröße**     | Q8_0 (7.70 GB)                                                    |
| **Kontextlänge** (token)          | 32K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (7.7 GB)                                                    |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 128 KB/Tok.                                                       |

---

### mellum2-12b-a2.5b-instruct (12B / 2.5B active) – Q4_K_M Modell-Quantisierung

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Essential AI                                                      |
| **Architektur**                   | **MoE** (Essential AI)                                            |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 12B / 2.5B                                                        |
| **Layers / Heads**                | 32 / 16 (4 KV)                                                    |
| **Experts**                       | 64 max; LMS: **aktiv 16**                                         |
| **Quantisierung/Modellgröße**     | Q4_K_M (8.1 GB)                                                   |
| **Kontextlänge** (token)          | 131K                                                              |
| **V-Cache-Quant**                 | V-Cache Q8_0 (=> voller Kontext bei 16 Experts)                   |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (8.1 GB + KV-Cache => 9.7 GB gesamt)                       |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | MoE. 16 Experts = gute Balance.                                   |

**Hinweis Experten-Einstellung:** Beim ersten Lauf waren nur 8 Experts aktiv (LM Studio Default). 
Für den zweiten Lauf wurden die Experts auf Maximum 64 erhöht, was bei vollem Kontext (131K) zu `ggml_new_object: not enough space` führte. 
Auch 32 Experten konnten nicht geladen werden. Erst mit 16 Experts + V-Cache Q8_0 läuft das Modell stabil bei voller Kontextlänge.

---

### mellum2-12b-a2.5b-instruct_moe (12B / 2.5B active) – MXFP4 MoE Modell-Quantisierung (gelöscht)

|| Eigenschaft                      | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Essential AI                                                      |
| **Architektur**                   | **MoE** (Essential AI, MXFP4)                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 12B / 2.5B                                                        |
| **Layers / Heads**                | 32 / 16 (4 KV)                                                    |
| **Experts**                       | 64 max; LMS: **aktiv 16**                                         |
| **Quantisierung/Modellgröße**     | MXFP4 (7.0 GB)                                                    |
| **Kontextlänge** (token)          | 131 k Token (max)                                                 |
| **V-Cache-Quant**                 | V-Cache Q8_0 (=> voller Kontext bei 16 Experts)                   |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (7.0 GB + V-Cache Q8_0 => 8.7 GB gesamt)                   |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | Wie Mellum2 12B, aber MXFP4-Quant statt Q4_K_M                    |

**Hinweis Experten-Einstellung:** Beim ersten Lauf waren nur 8 Experts aktiv (LM Studio Default). 
Für den zweiten Lauf wurden die Experts auf Maximum 64 erhöht, was bei vollem Kontext (131K) zu `ggml_new_object: not enough space` führte. 
Auch 32 Experten konnten nicht geladen werden. Erst mit 16 Experts + V-Cache Q8_0 läuft das Modell stabil bei voller Kontextlänge.

---

### microsoft/phi-4 (15B) - gelöscht, siehe unsloth-Modell für phi-4

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Microsoft Research                                                |
| **Architektur**                   | Dense (Phi-3, decoder-only Transformer)                           |
| **Reasoning**                     | Nein (Basis Phi-4)                                                |
| **Param. Total / Active**         | 14.7B (100%)                                                      |
| **Quantisierung/Modellgröße**     | Q6_K (12.03 GB)                                                   |
| **Kontextlänge** (token)          | 16K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.0 GB + Kontext x KV-Cache Quant.)                    |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 25 KB/Tok. rechnerisch                                            |
| **Lizenz**                        | MIT                                                               |
| **Einschätzung**                  | Microsoft, 14.7B dense, 16K Kontext. Solide Allround-Leistung.    |

**Offizielle Daten von Microsoft Research:**
- Training: Okt–Nov 2024, Daten-Cutoff Juni 2024
- Hauptsächlich Englisch, keine Multilingual-Unterstützung vorgesehen
- Fokus auf qualitativ hochwertige Daten und fortgeschrittenes Reasoning
- Code meist Python (typing, math, random, collections, datetime, itertools)
- Architektur: Phi3ForCausalLM, MQA (Multi-Query Attention) – nur 1 KV-Head spart KV-Cache

**Offizielle Benchmarks (Hersteller):** GPQA: 56.1%, MATH: 86.5%, HumanEval: 85.5%, MMLU-Pro: 68.3%

Developers: Microsoft Research
Architecture: 14.7B parameters, dense decoder-only Transformer model
Input/Output: Text, best suited for prompts in the chat format / Generated text in response to input

Dates: October 2024 – November 2024
Status: Static model trained on an offline dataset with cutoff dates of June 2024 and earlier for publicly available data

Quelle: https://huggingface.co/microsoft/phi-4

**Architektur-Hinweis:** MQA (Multi-Query Attention) – nur 1 KV-Head spart KV-Cache
**Formel KV-Cache (pro Slot):** `context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (Ergebnis in MB)
**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### ministral-3-14b-instruct-2512 

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (Mistral3, multimodal)                                      |
| **Reasoning**                     | **Ja** (optional)                                                 |
| **Param. Total / Active**         | 13.9B (100%)                                                      |
| **Quantisierung/Modellgröße**     | Q6_K (12.0 GB)                                                    |
| **Kontextlänge** (token)          | 262K max / hier: 98K                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (~12 GB + Kontext x KV-Quant Q5_1/IQ4_NL => VRAM 14.5 GB + shared RAM 1.7 GB) |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 128 KB/Tok, rechnerisch                                           |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Mistral AI, Mistral3-Architektur (multimodal). FP8-native Training. 262K Kontext.  |

The Ministral 3 14B Instruct model offers the following **capabilities**:

- Vision: Enables the model to analyze images and provide insights based on visual content, in addition to text.
- Multilingual: Supports dozens of languages, including English, French, Spanish, German, Italian, Portuguese, Dutch, Chinese, Japanese, Korean, Arabic.
- System Prompt: strong adherence and support for system prompts.
- Agentic: best-in-class agentic capabilities with native function calling and JSON outputting.
- Edge-Optimized: best-in-class performance at a small scale, deployable anywhere.
- Large Context Window: 256k context window.

**Recommended Settings**
We recommend deploying with the following best practices:
- System Prompt: Define a clear environment and use case, including guidance on how to effectively leverage tools in agentic systems.
- Sampling Parameters: Use a temperature below 0.1 for daily-driver and production environments ; Higher temperatures may be explored for creative use cases - developers are encouraged to experiment with alternative settings.
- Tools: Keep the set of tools well-defined and limit their number to the minimum required for the use case - Avoiding overloading the model with an excessive number of tools.
- Vision: When deploying with vision capabilities, we recommend maintaining an aspect ratio close to 1:1 (width-to-height) for images. Avoiding the use of overly thin or wide images - crop them as needed to ensure optimal performance.

---

### ministral-3-14b-reasoning-2512 - (gelöscht, hat zwar gute Scores, aber sehr langsam)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (Mistral3)                                                  |
| **Reasoning**                     | **Ja**                                                            |
| **Param. Total / Active**         | 14B (100%)                                                        |
| **Quantisierung/Modellgröße**     | ...                                                               |
| **Kontextlänge** (token)          | 131K                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp ( x GB; Kontext + KV-Cache...  => ... GB)               |
| **Timeout ×2**                    | ✅ Aktivieren                                                     |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 128 KB/Tok., rechnrisch                                           |
| **Einschätzung**                  | Guter DS1000-Score (60%). Reasoning → 3× Tokens, starke Ergebnisse, aber sehr langsam |

**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### mistralai/codestral-22b-v0.1

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI                                                        |
| **Architektur**                   | Dense (Mistral)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 22.2B (100%)                                                      |
| **Quantisierung/Modellgröße**     | IQ4_XS (11.9 GB)                                                  |
| **Kontextlänge** (token)          | 32K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (11.9 GB + Kontext x KV-Cache, V-Cache: Q8 => 14.75 GB)    |
| **Benchmark-Typ**                 | Coding                                                            |
| **KV-Cache**                      | 160 KB/Tok. (rechnerisch)                                         |
| **Lizenz**                        | MNPL (Mistral Non-Production License)                             |
| **Einschätzung**                  | Mistral AI, 80+ Programmiersprachen. 22B dense = hohe Qualität, aber VRAM-intensiv |

**Offizielle Infos:** MistralForCausalLM-Architektur. FIM (Fill-in-the-Middle) unterstützt. 80+ Programmiersprachen. 32K Kontext.

**Formel KV-Cache (pro Slot):** `context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (Ergebnis in MB)
**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### mistralai/mistral-nemo-instruct-2407 (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI / NVIDIA                                               |
| **Architektur**                   | Dense (Mistral)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 12.2B (100%)                                                      |
| **Quantisierung/Modellgröße**     | Q6_K (10.1 GB)                                                    |
| **Kontextlänge** (token)          | 184K                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (~10 GB + KV-Cache)                                         |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Mistral AI + NVIDIA. 12.2B, 184K Kontext. Tekken-Tokenizer. Gute Balance. |

**Offizielle Infos:** Nemo-Tokenizer (Tekken), 140+ Sprachen. MistralForCausalLM-Architektur. Apache-2.0-lizenziert.

---

### nemotron-14b-opencode-reasoning (14B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | NVIDIA                                                            |
| **Architektur**                   | Dense (Nemotron)                                                  |
| **Reasoning**                     | **Ja**                                                            |
| **Param. Total / Active**         | 14B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (11.0 GB)                                                    |
| **Kontextlänge** (token)          | 32K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (11 GB + KV-Cache)                                       |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | NVIDIA, OpenCodeReasoning. Reasoning + Agentic Coding.            |

**Timeout ×2:** ✅ Aktivieren (Reasoning)

---

### nerdsking-python-coder-7b-i

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Nerdsking.com                                                     |
| **Architektur**                   | Dense (Qwen2.5-Coder-7B-Basis)                                    |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 7.6B (100%)                                                       |
| **Quantisierung/Modellgröße**     | Q8_0_i (8.1 GB)                                                   |
| **Kontextlänge** (token)          | 32K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (8.1 GB + Kontext x KV-Cache Quant FP16 (keine) => 9.0 GB) |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Python-spezialisiert, Feintuning auf Qwen2.5-Coder-7B. HumanEval 86.99%. Partiell unzensiert  |

HF: https://huggingface.co/Nerdsking/Nerdsking-python-coder-7B-i

---

### north-mini-code-1.0

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Cohere / CohereLabs                                               |
| **Architektur**                   | **MoE** (Cohere2MoE, 128 Experts, Top-8 aktiv, SwiGLU FFN)        |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 30B / 3B (8/128 Experts aktiv)                                    |
| **Quantisierung/Modellgröße**     | Q3_K_M (14.2 GB)                                                  |
| **Kontextlänge** (token)          | 256K (max), 64K (max Output)                                      |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14.2 GB + KV-Cache) => 15.6 GB VRAM + 1.6 GB shared RAM |
| **Benchmark-Typ**                 | Coding + Agentic                                                  |
| **Lizenz**                        | Apache 2.0                                                        |
| **Einschätzung**                  | Cohere North Mini Code 1.0. Starke Agentic-Coding-Werte (SWE-Bench 80%). Apache-2.0. |

SWE-Bench Verified pass@10: 80.2% | Terminal-Bench v2 pass@10: 55.1% | AA Coding Index: 33.4

**ACHTUNG: Modell verträgt keine KV-Cache Quantisierung, lädt mit KV-Quantisierung nicht!

HF: https://huggingface.co/CohereLabs/North-Mini-Code-1.0

---

### numinamath-7b-cot (7B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Mistral AI / AI4Math                                              |
| **Architektur**                   | Dense (DeepSeekMath-Basis)                                        |
| **Reasoning**                     | **Ja** (Chain-of-Thought)                                         |
| **Param. Total / Active**         | 7B (100%)                                                         |
| **Quantisierung/Modellgröße**     | Q8_0 (7.5 GB)                                                     |
| **Kontextlänge** (token)          | —                                                                 |    
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (7.5 GB)                                                    |
| **Benchmark-Typ**                 | Math (spezialisiert)                                              |
| **Einschätzung**                  | Step-1 SFT von DeepSeekMath-7B. Math CoT. Für AMC/AIME etc.       |

**Timeout ×2:** ✅ Aktivieren (Reasoning)

---

### pandalyst_13b_v1.0 (13B) - gelöscht

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Architektur**                   | Dense (Code Llama / WizardCoder)                                  |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 13B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (10.68 GB)                                                   |
| **Kontextlänge** (token)          | Nicht gesetzt                                                     |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (10.7 GB)                                                   |
| **Benchmark-Typ**                 | Pandas/Coding                                                     |
| **Einschätzung**                  | Speziell für Pandas Data Analysis trainiert. Ideal für DS1000/PandasEval. |

**Architektur-Hinweis:** GQA (Grouped-Query Attention) mit 40 Query-Heads und 6 KV-Heads
**Formel KV-Cache (pro Slot):** `context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (Ergebnis in MB)
**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### unsloth/phi-4  (anstelle microsoft/phi-4, das läuft schlechter)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Microsoft / Unsloth / cutoff date June 2024                       |
| **Architektur**                   | Dense (Phi-3)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 15B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q5_K_M (10.4 GB)                                                  |
| **Kontextlänge** (token)          | 16K token                                                         |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (10.4 GB + ohne KV-Cache Quant. => 13.6 GB gesamt)         |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | Unsloth-Quant von Phi 4. Q5_K_M spart VRAM ggü. Microsoft Variante Q6_K |

Läuft mit geringfügig besseren Benchmark-Ergebnissen als die Microsoft-Variante, Grund dafür unklar. 
Evtl. Finetuning durch Unsloth? Oder fehlende KV-Quant., weil Modell selber kleiner?
Hinsichtlich der Quantisierung müsste das Microsoft Modell mit Q6_K eigentlich besser sein.

Achtung: BugFixes s.a. https://unsloth.ai/blog/phi4 

---

### pythia-12b (12B) - (gelöscht)

| Eigenschaft                       | Wert                                                               |
|-----------------------------------|--------------------------------------------------------------------|
| **Hersteller**                    | EleutherAI                                                         |
| **Architektur**                   | Dense (GPT-NeoX)                                                   |
| **Reasoning**                     | Nein                                                               |
| **Param. Total / Active**         | 12B (100%)                                                         |
| **Quantisierung/Modellgröße**     | Q6_K (9.8 GB)                                                      |
| **Kontextlänge** (token)          | 2K (sehr kurz!)                                                    |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (9.8 GB)                                                    |
| **Benchmark-Typ**                 | Coding + MC                                                        |
| **Einschätzung**                  | EleutherAI, GPT-NeoX-Architektur. Nur 2K Kontext – stark limitiert.|

---

### qwen/qwen3.5-9b (9B) (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                              |
| **Architektur**                   | Dense (Qwen3.5)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 9B (100%)                                                         |
| **Quantisierung/Modellgröße**     | Q? (8.28 GB)                                                      |
| **Kontextlänge** (token)          | 262K                                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (8.3 GB)                                                    |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 168 KB/Tok.                                                       |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Kein System-Message-Support → User-Prompt-Einbettung.             |

**Architektur-Hinweis:** GQA (Grouped-Query Attention) mit 40 Query-Heads und 8 KV-Heads
**Formel KV-Cache (pro Slot):** `context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (Ergebnis in MB)
**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

HF-Modellkarte: https://huggingface.co/Qwen/Qwen3.5-9B

---

### qwen3.5-9b-deepseek-v4-flash (9B) - gelöscht

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba)                                                    |
| **Architektur**                   | Dense (Qwen3.5)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 9B (100%)                                                         |
| **Quantisierung/Modellgröße**     | Q8_0 (9.5 GB)                                                     |
| **Kontextlänge** (token)          | 128K                                                              |    
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (9.5 GB)                                                    |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **Einschätzung**                  | DeepSeek-v4-Flash-Version von Qwen3.5 9B. Q8 = hohe Präzision     |

---

### qwen2.5-14b-instruct-1m (gelöscht)

| Eigenschaft                       | Wert                                                                                      |
|-----------------------------------|-------------------------------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                                                      |
| **Architektur**                   | Dense (Qwen2.5, 1M-kontextoptimiert), 48 Layer, GQA (40 Q / 8 KV), Sparse Attention + Length Extrapolation |
| **Reasoning**                     | Nein                                                                                      |
| **Param. Total / Active**         | 14.7B (100%)                                                                              |
| **Quantisierung/Modellgröße**     | Q6_K (12.1 GB)                                                                            |
| **Kontextlänge** (token)          | 1.010.000 (1M!) max. / hier: 98K                                                          |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.1 GB + Kontext x KV-Qaunt Q5_1/IQ4_NL => 15.4 GB + 2.3 GB shared GPU-mem)    |
| **Benchmark-Typ**                 | very Long-Context + MC                                                                    |
| **Lizenz**                        | Apache-2.0                                                                                |
| **Einschätzung**                  | Long-Context-Version von Qwen2.5-14B. 48 Layer, GQA (40 Q / 8 KV).                        |

**Achtung**: In LM Studio nur mit stark reduzierter Kontextlänge in 16 GB VRAM betreibbar (vLLM mit 320 GB empfohlen). 

**Architektur-Hinweis:** Gleiche Architektur wie Qwen2.5-14B-instruct, aber für 1M-Kontext optimiert (Sparse Attention, Length Extrapolation).
=> Eigentlich unnötig, die Kontextlänge kann ich sowieso nicht ausnutzen!

**KV-Cache:** ~200 KB/Tok. rechnerisch → bei 1M ~200+ GB (ohne KV-Quant). In LM Studio nur mit stark reduziertem Kontext auf 16 GB nutzbar.

Paper: https://arxiv.org/abs/2501.15383
HF: https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-1M

---

### qwen2.5-coder-14b-instruct -> Bester Coding-Score!

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                              |
| **Architektur**                   | Dense (Qwen2.5)                                                   |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 14.8B (100%)                                                      |
| **Quantisierung/Modellgröße**     | Q5_0 (10.6 GB)                                                    |
| **Kontextlänge** (token)          | 131K max / hier: 98K                                              |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (10.6 GB + KV-Cache Quant. Q5_1/IQ4_NL => 15.4 GB + 1.2 GB shared GPU-mem)  |
| **Benchmark-Typ**                 | Coding                                                            |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | 5.5T Trainings-Tokens, GPT-4o-matched Coding. 89+ Programmiersprachen. |

**Architektur-Hinweis:** GQA (Grouped-Query Attention), SwiGLU, RMSNorm. Hidden Size 5120, 48 Layer, 40 Query-Heads, 8 KV-Heads, Head Size 128, Intermediate Size 13824.

**KV-Cache:** rechnerisch: ~160 KB/Tok. → bei 32K ~5.1 GB, bei 128K ~20.5 GB (mit KV-Quant reduzierbar).

**Benchmark-Ergebnisse (SampleSize=10):** HumanEval+ 100%, MBPP+ 100%.

HF: https://huggingface.co/Qwen/Qwen2.5-Coder-14B

---

### qwen3-coder-reap-25b-a3b-i1 - REAP pruned Base Model: Qwen3-Coder-30B-A3B-Instruct 

| Eigenschaft                       | Wert                                                                                    |
|-----------------------------------|-----------------------------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                                                    |
| **Architektur**                   | **MoE**, Qwen2.5-Architektur; Sparse Mixture-of-Experts (SMoE) Causal Language Model    |
| **Reasoning**                     | Nein                                                                                    |
| **Total / Active** Parameter      | 25B / 3B, REAP-pruned von 30B auf 25B                                                   |
| **Layers / Heads**                | 48 Layers, Number of Attention Heads (GQA): 32 for Q and 4 for KV                       |    
| **Experts**                       | Architektur # 103 (REAP-pruned from 128); Top-k (aktiv): 8; shared: Nein                |
                                        => mit 16GB VRAM in LMS: #experts = max 16 (je nach Kontextlänge)                     |
| **Quantisierung/Modellgröße**     | Q3_K_M (12.0 GB), IQ4_XS (13.4 GB), Q4_K_S (14.2 GB), imatrix und static                |
| **Kontextlänge** (token)          | 262 k Token max. bei Q3_K_M möglich / hier: 131 k bei allen Modellen bzw. in Benchmark: 16k             |
| **GPU-Tauglichkeit (16 GB VRAM)** | Q3_K_M: ⚠️ knapp (12.0 GB + KV-Cache Quant. Q5_1/IQ4_NL => 12.9 GB (16 k Kontext) + 0.2 shared GPU mem  |
|                                   | IQ4_XS: ⚠️ knapp (13.4 GB + KV-Cache Quant. Q5_1/IQ4_NL => 15.5 GB + 4.9 shared GPU mem |
|                                   | Q4_K_S: ⚠️ knapp (14.2 GB + KV-Cache Quant. Q5_1/IQ4_NL => 14.8 GB + 3.9 shared GPU bei 98k Kontextlänge |
| **Benchmark-Typ**                 | code generation, code reasoning and code fixing, Code Agents, mathematics and general   |
| **Lizenz**                        | Apache-2.0                                                                              |

**ACHTUNG** läuft nicht mit mehr als 24 / 32 Experten, je nach Kontextlänge und KV-Quant. (max Einstellung 103).

Qwen3 bietet folgende Hauptmerkmale:
- Unterstützung für nahtlosen Wechsel zwischen dem „Denkmodus“ [Reasoning] (für komplexe logische Schlussfolgerungen, Mathematik und Programmierung) und dem „Nicht-Denkmodus“ (für effiziente, allgemeine Dialoge) innerhalb eines einzigen Modells, 
    wodurch eine optimale Leistung in verschiedenen Szenarien gewährleistet wird.
- Schlussfolgerungsfähigkeiten, die die bisherigen Modelle QwQ (im Denkmodus) und Qwen2.5 (im Nicht-Denkmodus) in den Bereichen Mathematik, Codegenerierung und logisches Schlussfolgern auf der Grundlage von Allgemeinwissen übertreffen.
- Anpassung an menschliche Präferenzen, insbesondere bei kreativem Schreiben, Rollenspielen, mehrrundigen Dialogen und der Befolgung von Anweisungen, um ein natürlicheres, fesselndes und immersives Gesprächserlebnis zu bieten.
- Fachkompetenz im Bereich der Agentenfähigkeiten, die eine präzise Integration mit externen Tools sowohl im Denk- als auch im Nicht-Denk-Modus ermöglicht.
- Unterstützung von über 100 Sprachen und Dialekten mit starken Fähigkeiten zur mehrsprachigen Befehlsausführung und Übersetzung.

(https://huggingface.co/cerebras/Qwen3-Coder-REAP-25B-A3B

---

### qwen3.6-27b (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                              |
| **Architektur**                   | Dense (Qwen3.6, Hybrid Gated DeltaNet + Attention)                |
| **Reasoning**                     | **Ja** (Thinking-Mode via CoT)                                    |
| **Param. Total / Active**         | 27.8B (100%)                                                      |
| **Layers / Heads**                | 64 Layers                                                         |    
|                                   |  Gated DeltaNet: # Linear Attention Heads 48 for V + 16 for QK    |
|                                   |  Gated Attention # Heads 24 for Q and 4 for KV                    |
| **Quantisierung/Modellgröße**     | Q3_K_S (12.4 GB)                                                  |
| **Kontextlänge** (token)          | 262K natively, extensible up to 1M / hier: 98K                    | 
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (12.4 GB + Kontext x KV-Cache Q8/IQ4_NL => 15.8 GB)     |
| **Timeout ×2**                    | ✅ Aktivieren (Thinking)                                         |
| **Benchmark-Typ**                 | Coding + MC (Flagship-Level)                                      |
| **Lizenz**                        | Apache-2.0                                                        |


**New cpabilities**
This release delivers substantial upgrades, particularly in:
- *Agentic Coding*: the model now handles frontend workflows and repository-level reasoning with greater fluency and precision.
- *Thinking Preservation*: there is a new option to retain reasoning context from historical messages, streamlining iterative development and reducing overhead.

**Critical issue** Benchmark-Test für Coding: The model generates reasoning tokens instead of code. "0.0 tok/s" and "≈0% Thinking" 
indicates the model is producing thinking tokens that aren't being counted. The model is a reasoning model that outputs thinking first,  
then the actual answer. The benchmark harness can't parse the code because it's buried in reasoning.

Parameter: "max_tokens": 8192,       # ← Erhöht von 2048
           "enable_thinking": False,  # ← Thinking (für Coding) deaktivieren; wo???

**Architektur-Details:**
- Language Model: 27B, Hidden Size 5120, Token Embedding 248320, 64 Layer
- Hidden Layout: 16 × (3 × (Gated DeltaNet → FFN) → 1 × (Gated Attention → FFN))
- Gated DeltaNet: 48 V-Heads / 16 QK-Heads, Head Dim 128
- Gated Attention: 24 Q-Heads / 4 KV-Heads, Head Dim 256, RoPE Dim 64
- FFN: Intermediate Size 17408
- MTP: trained with multi-steps

**KV-Cache:** ~128 KB/Tok. (nur 4 KV-Heads bei Attention-Blöcken × 16 Attention-Layer) → bei 262K ~33 GB (mit KV-Quant). Nur mit stark reduziertem Kontext auf 16 GB.

**Achtung:** Q3_K_S = starke Quantisierung. Für volle Qualität Q5_K_M empfohlen (~19 GB), dann nicht auf 16 GB VRAM.

Blog: https://qwen.ai/blog?id=qwen3.6-27b
HF: https://huggingface.co/Qwen/Qwen3.6-27B

---

### qwen3.6-28b-reap-i1 (28B) - REAP-pruned from Qwen/Qwen3.6-35B-A3B (gelöscht) => 2 Quantisierungen!

| Eigenschaft                       | Wert                                                                              |
|-----------------------------------|-----------------------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                                              |
| **Architektur**                   | **MoE**, qwen35moe, A3B-Active-Architektur, REAP-pruned from Qwen3.6-35B-A3B      |
| **Reasoning**                     | Ja                                                                                |
| **Layers / Heads**                | Hybrid Gated DeltaNet + Attention; 40 Layer.                                      |
| **Experts**                       | original 256 Experten/Layer auf 205 pruned (REAP-Methode)                         |      
                                        Experten, aktiv: 8 (+ 1 shared) => #experts >= 9                                |
                                        LMS: #205 laden auch, selbst mit 262k Kontext, aber dann extrem langsam!        |
| **Param. Total / Active**         | 28B (pruned from 35B)                                                             |
| **Quantisierung/Modellgröße**     | IQ3_K_M (12.63 GB) und Q3_K_S (12.4 GB)                                           |
| **Kontextlänge** (token)          | 262K max.; hier: 131 k                                                            |
| **Lizenz**                        | Apache-2.0                                                                        |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ knapp mit 262k Kontext u. 205 experts (sehr langsam):                         |
                                        VRAM = 12.6 GB + KV-Cache Q8_0/IQ4_NL => 15.6 GB VRAM + 3.1 GB shared GPU-RAM   |
                                      ✅ ja mit 131k Kontext u. 18 experts (sehr viel schneller!):                     |
                                        VRAM = 12.6 GB + KV-Cache Q5_1/IQ4_NL => 13.8 GB VRAM + 0.5 GB shared GPU-RAM   |
| **Benchmark-Typ**                 | Coding + MC                                                                       |
| **Einschätzung**                  | Große Kontextlänge 262 k möglich & selbst mit 205 experts lädt das Modell.        | 
                                        ABER: dann sehr langsam ~5 t/s / besser: 18 experts => 30-250 t/s               |
                                        Known limitations
**Bekannte Einschränkungen**:
    Refusal behavior follows the base model plus Opus SFT; no explicit abliteration was applied in this release. 
    The model will refuse straight adversarial probes at roughly base-model rates.
    Reasoning quality on GSM8K-style problems depends on the <think> chain-of-thought; short max-tokens limits hurt accuracy.
    Structured-output calibration is oversampled vs. base mix (JSON/Mermaid experts preferentially retained).
                                        
**Critical issue** Benchmark-Test für Coding: The model generates reasoning tokens instead of code. "0.0 tok/s" and "≈0% Thinking" 
indicates the model is producing thinking tokens that aren't being counted. The model is a reasoning model that outputs thinking first,  
then the actual answer. The benchmark harness can't parse the code because it's buried in reasoning.

Parameter: "max_tokens": 8192,       # ← Erhöht von 2048
           "enable_thinking": False,  # ← Thinking (für Coding) deaktivieren
           
---

### qwen3-30b-a3b-python-coder - fine-tuned version of Qwen/Qwen3-30B-A3B (gelöscht)

| Eigenschaft                       | Wert                                                                              |
|-----------------------------------|-----------------------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                                              |
| **Architektur**                   | **Qwen3-MoE**; 48 Layer; 128 Experts, Top-8 aktiv; Python-spezialisiert           |
| **Reasoning**                     | Nein                                                                              |
| **Total / Active** Parameter      | 30.5B / 3.3B                                                                      |
| **Layers / Heads**                | Layers: 48 / heads: 32 Q + 4 KV                                                   |
| **Experts**                       | 128 Experts, Top-8 aktiv, shared 0. Empfohlene `num_experts` in LMS:  24 (64–128) |
                                    |   Halbierung mit Qualitätseinbußen bei Coding, aber mehr als 24 experts           |
                                    |   (ohne KV-QUant.) laden nicht bei Kontextlänge 41k                               |  
| **Quantisierung/Modellgröße**     | Q3_K_S (13.3 GB)                                                                  |
| **Kontextlänge** (token)          | 41 k Token (max.)                                                                 |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (13.3 GB + Kontext x KV-Cache Quant FP16 (ohne) => 14.3 GB)                 |
| **Benchmark-Typ**                 | Coding + Agentic                                                                  |
| **Einschätzung**                  | Python-spezialisiertes Qwen3-MoE. eher kleine bis mittlere Kontextlänge           |
| **Lizenz**                        | Apache-2.0 (Basis Qwen3-30B-A3B)                                    |

This model is a fine-tuned version of Qwen/Qwen3-30B-A3B on the burtenshaw/tulu-3-sft-personas-code-no-prompt dataset. It has been trained using TRL.

**Architektur-Hinweis:** Qwen3-MoE-Architektur, 48 Layer, 32 Query-Heads, 4 KV-Heads. Fine-grained Expert Segmentation. Keine Shared Experts.
**KV-Cache:** ~32 KB/Tok. rechernisch. (nur 4 KV-Heads + 48 Layer, aber nur Attention-Layer zählen) → bei 262K ~8.4 GB (mit KV-Quant).

**Empfehlung (ggf. nur die Angabe, mit welchen Parametern trainiert wurde???):** Sampling mit temperature=0.7, top_p=0.8, top_k=20, repetition_penalty=1.05, max_tokens=65536.

HF: https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct

---

### qwen2.5-coder-32b-instruct (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Qwen (Alibaba Cloud)                                              |
| **Architektur**                   | Dense (Qwen2.5, 64 Layer)                                        |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 32.5B (100%)                                                      |
| **Quantisierung/Modellgröße**     | Q3_K_S (14.40 GB)                                                 |
| **Kontextlänge** (token)          | 32K (128K via YaRN)                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14.4 GB + KV-Cache Quant. Q8/IQ4_NL => 16.1 GB)        |
| **Benchmark-Typ**                 | Coding                                                            |
| **Lizenz**                        | Apache-2.0                                                        |
| **Einschätzung**                  | Größter Qwen2.5-Coder. 64 Layer, 32.5B. Hohe Coding-Qualität.    |

**Architektur-Hinweis:** 64 Layer, Hidden Size 5120, 40 Query-Heads, 8 KV-Heads, Intermediate Size 27648. Kein Embedding Tying.

**KV-Cache:** ~160 KB/Tok. → bei 32K ~5.1 GB rechnerisch.

**Achtung:** Q3_K_S = starke Quantisierung. Qualitätsverluste möglich. Idealer Q5_K_M (~22 GB) passt nicht auf 16 GB.

instruction-tuned 32B Qwen2.5-Coder model, which has the following features:
    Type: Causal Language Models
    Training Stage: Pretraining & Post-training

HF: https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct


---

### starcoder2-15b-instruct-v0.1 (15B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Architektur**                   | Dense (Starcoder2)                                                |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 15B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (13.10 GB)                                                   |
| **Kontextlänge** (token)          | 16K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (13.1 GB + KV-Cache)                                     |
| **Benchmark-Typ**                 | Coding                                                            |
| **KV-Cache**                      | 120 KB/Tok.                                                       |
| **Einschätzung**                  | BigCode, Python-Code mit Ausführungsverifikation.                 |
                                        Q6_K = hohe Genauigkeit aber VRAM-intensiv.                     |

**Architektur-Hinweis:** GQA (Grouped-Query Attention) mit 40 Query-Heads und 6 KV-Heads
**Formel KV-Cache (pro Slot):** `context_len × layers × KV_heads × head_dim × (bytes_per_K + bytes_per_V) / 1024²` (Ergebnis in MB)
**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

---

### tiiuae/Falcon3-10B-Instruct

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | TII (Technology Innovation Institute, UAE)                        |
| **Architektur**                   | Dense (Llama, 40 Layer)                                           |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 10.3B (100%)                                                      |
| **Quantisierung/Modellgröße**     | Neu: Q8_0 (11 GB) / alt: Q6_K (8.46 GB)                           |
| **Kontextlänge** (token)          | 32K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (11 GB + KV-Cache Q8/Q5_1 => 13.2 GB)                      |
| **Benchmark-Typ**                 | Coding + MC                                                       |
| **KV-Cache**                      | 160 KB/Tok., bei 32K Kontext, rechn. => +5.1 GB (mit KV-Quant)    |
| **Lizenz**                        | Falcon LLM License (TII)                                          |
| **Einschätzung**                  | 40 Layer, LlamaForCausalLM-Architektur, GQA (12 Q / 4 KV), SwiGLU, RMSNorm. |

**Architektur-Hinweis:** TII, Falcon3-Familie. LlamaForCausalLM-Architektur (nicht Falcon-1/2-Architektur). GQA (Grouped-Query Attention) mit 12 Query-Heads und 4 KV-Heads, head_dim=256. Hoher RoPE-Wert (1000042) für Long-Context.

**Offizielle Benchmarks (Hersteller, Open LLM Leaderboard):** IFEval: 78.17%, BBH: 44.82%, MATH Lvl 5: 25.91%, GPQA: 10.51%, MMLU-PRO: 38.1%

**Empfohlene Slots:** 4 (LM Studio Unified KV-Cache teilt den Speicher zwischen Slots → kein extra VRAM durch mehrere Slots)

Quelle: https://huggingface.co/tiiuae/Falcon3-10B-Instruct-GGUF
Blog: https://huggingface.co/blog/falcon3


---

### translategemma-12b-it (12B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google                                                            |
| **Architektur**                   | Dense (Gemma)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 12B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (10.2 GB)                                                    |
| **Kontextlänge** (token)          | 98K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (10.2 GB + KV-Cache)                                     |
| **Benchmark-Typ**                 | Übersetzung (Translation)                                         |
| **Einschätzung**                  | Google, spezialisiert auf hochpräzise Übersetzung. ISO 17100-konform.                                 |

**Hinweis:** Übersetzungs-Modell – kein allgemeiner Coding/MC-Benchmark.

---

### translategemma-27b-it (27B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Hersteller**                    | Google                                                            |
| **Architektur**                   | Dense (Gemma)                                                     |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 27B (100%)                                                        |
| **Quantisierung/Modellgröße**     | IQ4_XS (14.5 GB)                                                  |
| **Kontextlänge** (token)          | 49K                                                               |
| **GPU-Tauglichkeit (16 GB VRAM)** | ⚠️ Knapp (14.5 GB + KV-Cache)                                     |
| **Benchmark-Typ**                 | Übersetzung (Translation)                                         |
| **Einschätzung**                  | Google, spezialisiert auf hochpräzise Übersetzung. 27B = höhere Qualität.                                 |

**Hinweis:** Übersetzungs-Modell – kein allgemeiner Coding/MC-Benchmark.


---

### wizardcoder-python-13b-v1.0 (13B) - (gelöscht)

| Eigenschaft                       | Wert                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| **Architektur**                   | Dense (Code Llama)                                                |
| **Reasoning**                     | Nein                                                              |
| **Param. Total / Active**         | 13B (100%)                                                        |
| **Quantisierung/Modellgröße**     | Q6_K (10.68 GB)                                                   |
| **Kontextlänge** (token)          | Nicht gesetzt                                                     |
| **GPU-Tauglichkeit (16 GB VRAM)** | ✅ Ja (10.7 GB)                                                   |
| **Benchmark-Typ**                 | Coding                                                            |
| **Einschätzung**                  | WizardLM, 09/2023. Code Llama Basis. Veraltet aber solide.        |
                                        i1-optimierte Quantisierung.                                    |

======================================================================================================================

## Anhang mit allgemeinen Hinweisen LMS-Einstellungen, Quellen, etc.

### Blacklist - von Benchmark ausgeschlossen (Vision/OCR/Embedding) 

| Eigenschaft                           | Wert                                               |
|---------------------------------------|----------------------------------------------------|
| deepseek-ocr                          | OCR-Spezialist                                     |
| garnet-ocr-7b-0422-i1                 | OCR-Spezialist (Dokumente, Fraktura, Sütterlin)    |
| glm-4.6v-flash                        | Vision-Language (Multimodal)                       |
| glm-ocr                               | OCR-Spezialist (GLM-basiert)                       |
| mimo-vl-7b-rl-2508                    | Vision-Language (Multimodal, Xiaomi)               |
| mimo-vl-7b-sft-2508                   | Vision-Language (Multimodal, Reasoning on/off)     |
| nanonets-ocr2-3b                      | OCR-Spezialist (Dokument-zu-Markdown, LaTeX)       |
| qwen2.5-vl-8b-ocr                     | OCR/Vision-Language (Qwen-basiert)                 |
| text-embedding-nomic-embed-text-v1.5  | Embedding-Modell                                   |

---

### ACHTUNG! Architekturabhängigkeit der KV-Quantisierungs-Empfindlichkeit 

| Modellfamilie                 | KV-Empfindlichkeit     | Hinweis                                                                                                      |
|-------------------------------|------------------------|--------------------------------------------------------------------------------------------------------------|
| **Qwen** (2.5/3/3.5)          | **Hoch** (dense + MoE) | Qwen2.5/3/3.5 reagieren generell empfindlich auf symetrische KV-Quantisierung, unabhängig von der Architektur.|
                                                         | Symmetrisches Q4+K/Q4+V kann katastrophale Qualitätsverluste verursachen. Neuere Versionen weniger betroffen.|
| **Gemma 4**                   | **Hoch**               | Gemma 4 26B A4B (MoE) ist 3,5× empfindlicher als Gemma 4 31B (dense). => keine KV-Quant.                     |
| **Llama / Mistral / Cohere**  | **Niedrig**            | Tolerieren KV-Quantisierung gut.                                                                             |
| **Small Models** (< 4B aktiv) | **Höher**              | Kleine effektive Modellgrößen reagieren empfindlicher auf numerische Fehler durch Quantisierung.             |
| **Layer-Position**            | Erste + letzte 5 Layer ≈ 10× empfindlicher als mittlere Layer. Per-Layer Mixed-Precision kann optimieren.                             |

---

### Formel (K- und V-Cache getrennt) 
KV-Cache pro Slot = `context_len × layers × KV_heads × head_dim × (bytes_per_K_value + bytes_per_V_value)`
Vereinfacht (bei gleicher Quantisierung für K und V): `... × 2 (K+V) × bytes_per_value`

Bytes per value (Quantisierung des KV-Cache, getrennt für K und V):

| K-Quant | V-Quant | K-Bytes/value | V-Bytes/value | Hinweis                                                                       |
|---------|---------|---------------|---------------|-------------------------------------------------------------------------------|
| FP16    | FP16    | 2 Byte        | 2 Byte        | **LM Studio Default** – fast lossless                                         |
| Q8      | Q8      | 1 Byte        | 1 Byte        |  einfachste Stufe der Quantisierung, am wenigsten Qualitätsverlust nach FP16  |
| Q8      | Q4      | 1 Byte        | 0,5 Byte      | **Empfohlen bei VRAM-Knappheit** – K behält Präzision, V komprimiert          |
| Q4      | Q4      | 0,5 Byte      | 0,5 Byte      | Maximal komprimiert – deutliche Qualitätseinbußen möglich                     |
| Q8      | FP16    | 1 Byte        | 2 Byte        | bei Modellen/Layern die keine V-Quantisierung vertragen                       |

**Asymmetrie:** K-Cache ist qualitätsempfindlicher als V-Cache. K-Fehler werden durch Softmax (Exponentiation) verstärkt, V-Fehler skalieren linear. 
Empfehlung daher: K höher auflösen, V stärker komprimieren (z.B. `Q8_K + Q4_V`).

---

### LM Studio `num_experts`-Parameter 

LM Studio unterstützt den Parameter `num_experts` (via REST API `load_config` oder Python SDK `llm.load.model()`), um die Anzahl der **geladenen Experten** für MoE-Modelle zu begrenzen. 
Dies unterscheidet sich vom modellinternen `top-k` (aktive Experten pro Token):

| Aspekt                        | Erklärung                                                                                 |
|-------------------------------|-------------------------------------------------------------------------------------------|
| **`num_experts`** (LM Studio) | Begrenzt wie viele Experten insgesamt geladen werden. Niedriger Wert → weniger VRAM,      |
                                |     aber weniger Experten zur Auswahl → potenziell geringere Qualität                     |
| **`top-k`** (Modell-intern)   | Wie viele der geladenen Experten pro Token aktiv sind.                                    |
                                |    Wird vom Modell festgelegt (z.B. Top-4, Top-8)                                         |

**Empfehlungen für `num_experts`:**

| Modell                    |  Experten     | Empfohlenes   | Begründung                                                                                                                        |
|                           |   gesamt      | `num_experts` |                                                                                                                                   |
|---------------------------|---------------|---------------|-----------------------------------------------------------------------------------------------------------------------------------|
| ernie-4.5-21b-a3b-pt      | 130 (64+64+2) | 64 (Standard) | Bei VRAM-Knappheit auf 32 reduzierbar; dann nur Text-Experten                                                                     |
| gemma-4-19b-a4b-it        |  90 (REAP)    | 90 (Standard) | Nicht reduzieren – REAP hat bereits optimiert                                                                                     |
                                                                => Problem: Modell lädt nicht mit sovielen Experten! Mit 45 Experten und ohen KV-Quant. lädt es!                                |
| granite-4.0-h-tiny        |  64           | **16**        | ⚠️ 64 Experts → `ggml_new_object: not enough space` bei 1M Context. Erst mit 16 Experts stabil.                                   |
| lfm2.5-8b-a1b             |  32           | 32 (Standard) | Kleines Modell, kein VRAM-Druck                                                                                                   |
| lfm2-24b-a2b              |  64           | 64 (Standard) | 24B total, expertenabhängiger VRAM                                                                                                |
| qwen3-30b-a3b-python-coder| 128           | 24 (64–128)   | Halbierung möglich, aber Qualitätseinbußen bei Coding <=> mehr als 24 experts (ohne LV-QUant.) laden nicht bei Kontextlänge 41k   |
| qwen3-coder-reap-25b-a3b  | 103 (128)     | 24 (64–128)   | Halbierung möglich, aber Qualitätseinbußen bei Coding <=> mehr als 24 experts (ohne LV-QUant.) laden nicht bei Kontextlänge 131k  |
| qwen3.6-28b (REAP)        | 205           | 128–205       | Stark pruned – Reduzierung nur wenn VRAM kritisch                                                                                 |
| deepseek-coder-v2-lite    |   8           |  8 (Standard) | Nur 8 Experten – kein Spielraum                                                                                                   |
| gpt-oss-20b               |  32           | 32 (Standard) | MXFP4-Quant. hält VRAM niedrig                                                                                                    |

**Hinweis:** Der Parameter wird über die LM Studio Python SDK gesetzt (`numExperts`) oder im REST-API-Load-Request (`"num_experts": N`). 
Im LM Studio GUI ist er nicht direkt einstellbar. Ein zu niedriger Wert kann die Modellqualität deutlich beeinträchtigen, da der Router nur aus den geladenen Experten wählen kann.

---

### Structured Output (JSON response_format): 

Das OpenAI-kompatible API von LM Studio unterstützt response_format: {"type": "json_object"}. Dies könnte helfen:

Modell wird gezwungen, valides JSON auszugeben
Reasoning-Tokens werden in das JSON-Format integriert
Code-Extraktion wird zuverlässiger
ABER: Das erfordert größere Änderungen am Benchmark-Harness:

extract_code() müsste JSON-Parsing statt Markdown-Block-Extraktion verwenden
Das System-Prompt müsste angepasst werden
Alle Benchmarks (DS1000, CoderEval) müssten JSON-Ausgabe erwarten
Empfehlung: Zuerst enable_thinking=false + max_tokens=8192 testen. Structured Output als optionale Erweiterung für einen zweiten Lauf.

===================================================

---



## Modell-Quellen

| Modell                               | LM Studio                                                                  | HuggingFace                                                                       | 
|--------------------------------------|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| acemath-7b-instruct                  | [lmstudio.ai](https://lmstudio.ai/models/acemath-7b-instruct)                                                           | [huggingface.co](https://huggingface.co/nvidia/AceMath-7B-Instruct)               |
| codegemma-7b-it                      | [lmstudio.ai](https://lmstudio.ai/models/codegemma-7b-it)                  | [huggingface.co](https://huggingface.co/google/codegemma-7b-it)                   |
| deepseek-coder-33b-instruct          | [lmstudio.ai](https://lmstudio.ai/models/deepseek-coder-33b-instruct)      | [huggingface.co](https://huggingface.co/deepseek-ai/DeepSeek-Coder-33B-Instruct)  |
| deepseek-coder-6.7b-instruct         | [lmstudio.ai](https://lmstudio.ai/models/deepseek-coder-6.7b-instruct)     | [huggingface.co](https://huggingface.co/deepseek-ai/DeepSeek-Coder-6.7B-Instruct) |
| ernie-4.5-21b-a3b-pt                 | [lmstudio.ai](https://lmstudio.ai/models/ernie-4.5-21b-a3b-pt)             | [huggingface.co](https://huggingface.co/nvidia/ERNIE-4.5-21B-A3B-PT)              |
| essentialai/rnj-1                    | [lmstudio.ai](https://lmstudio.ai/models/rnj-1)                            | [huggingface.co](https://huggingface.co/EssentialAI/rnj-1)                        |
| tiiuae/Falcon3-10B-Instruct          | [lmstudio.ai](https://lmstudio.ai/models/falcon3-10b-instruct)                                                           | [huggingface.co](https://huggingface.co/tiiuae/Falcon3-10B-Instruct-GGUF)         |
| gemma-4-19b-a4b-it-reap-i1           | [lmstudio.ai](https://lmstudio.ai/models/gemma-4-19b-a4b-it-reap-i1)       | [huggingface.co](https://huggingface.co/google/gemma-4-19b-a4b-it)                |
| gemma-4-31b-i1                       | — (wird geladen)                                                           | [huggingface.co](https://huggingface.co/google/gemma-4-31B)                       |
| granite-4.0-h-tiny                   | [lmstudio.ai](https://lmstudio.ai/models/granite-4.0-h-tiny)               | [huggingface.co](https://huggingface.co/ibm-granite/granite-4.0-h-tiny)           |
| granite-4.1-8b                       | [lmstudio.ai](https://lmstudio.ai/models/granite-4.1-8b)                   | [huggingface.co](https://huggingface.co/ibm-granite/granite-4.1-8b-sft)           |
| januscoder-14b                       | [lmstudio.ai](https://lmstudio.ai/models/januscoder-14b)                   | [huggingface.co](https://huggingface.co/unsloth/JanusCoder-14B-GGUF)              |
| lfm2.5-8b-a1b                        | [lmstudio.ai](https://lmstudio.ai/models/lfm2.5-8b-a1b)                    | [huggingface.co](https://huggingface.co/LiquidAI/LFM2-8B-A1B)                     |
| lfm2-24b-a2b-reap-i1                 | [lmstudio.ai](https://lmstudio.ai/models/lfm2-24b-a2b-reap-i1)             | [huggingface.co](https://huggingface.co/LiquidAI/LFM2-24B-A2B)                    |
| mathstral-7b-v0.1                    | [lmstudio.ai](https://lmstudio.ai/models/mathstral-7b-v0.1)                | [huggingface.co](https://huggingface.co/mistralai/Mathstral-7B-v0.1)              |
| microsoft/phi-4                      | [lmstudio.ai](https://lmstudio.ai/models/phi-4)                            | [huggingface.co](https://huggingface.co/microsoft/phi-4)                          |
| mistralai/codestral-22b-v0.1         | [lmstudio.ai](https://lmstudio.ai/models/codestral-22b-v0.1)               | [huggingface.co](https://huggingface.co/mistralai/Codestral-22B-v0.1)             |
| mistralai/mistral-nemo-instruct-2407 | [lmstudio.ai](https://lmstudio.ai/models/mistral-nemo-instruct-2407)       | [huggingface.co](https://huggingface.co/mistralai/Mistral-Nemo-Instruct-2407)     |
| ministral-3-14b-reasoning-2512       | [lmstudio.ai](https://lmstudio.ai/models/ministral-3-14b-reasoning-2512)   | [huggingface.co](https://huggingface.co/mistralai/Ministral-3-14B-Reasoning)      |
| ministral-3-14b-instruct-2512        | [lmstudio.ai](https://lmstudio.ai/models/ministral-3-14b-instruct-2512)    | [huggingface.co](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512)  |
| devstral-small-2-24b-instruct-2512   | [lmstudio.ai](https://lmstudio.ai/models/devstral-small-2-24b-instruct-2512) | [huggingface.co](https://huggingface.co/Devstral/Devstral-Small-2-24B-Instruct-2512) |
| nerdsking-python-coder-7b-i          | [lmstudio.ai](https://lmstudio.ai/models/nerdsking-python-coder-7b-i)                                                           | [huggingface.co](https://huggingface.co/Nerdsking/Nerdsking-python-coder-7B-i)    |
| north-mini-code-1.0                  | [lmstudio.ai](https://lmstudio.ai/models/north-mini-code-1.0)              | [huggingface.co](https://huggingface.co/CohereLabs/North-Mini-Code-1.0)           |
| qwen/qwen2.5-coder-14b               | [lmstudio.ai](https://lmstudio.ai/models/qwen2.5-coder-14b)                | [huggingface.co](https://huggingface.co/Qwen/Qwen2.5-Coder-14B)                   |
| qwen/qwen2.5-coder-32b-instruct      | [lmstudio.ai](https://lmstudio.ai/models/qwen2.5-coder-32b-instruct)                                                           | [huggingface.co](https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct)          |
| qwen/qwen2.5-14b-instruct-1m         | [lmstudio.ai](https://lmstudio.ai/models/qwen2.5-14b-instruct-1m)                                                           | [huggingface.co](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-1M)             |
| qwen/qwen3.5-9b                      | [lmstudio.ai](https://lmstudio.ai/models/qwen3.5-9b)                       | [huggingface.co](https://huggingface.co/Qwen/Qwen3.5-9B)                          |
| qwen3-14b                            | [lmstudio.ai](https://lmstudio.ai/models/qwen3-14b)                        | [huggingface.co](https://huggingface.co/Qwen/Qwen3-14B)                           |
| qwen3-30b-a3b-python-coder           | [lmstudio.ai](https://lmstudio.ai/models/qwen3-30b-a3b-python-coder)                                                           | [huggingface.co](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)        |
| qwen3-coder-reap-25b-a3b-i1          | [lmstudio.ai](https://lmstudio.ai/models/qwen3-coder-reap-25b-a3b-i1)      | [huggingface.co](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)        |
| qwen3.5-9b-deepseek-v4-flash         | [lmstudio.ai](https://lmstudio.ai/models/qwen3.5-9b-deepseek-v4-flash)     | [huggingface.co](https://huggingface.co/Qwen/Qwen3.5-9B-DeepSeek-v4-Flash)        |
| qwen3.6-27b                          | [lmstudio.ai](https://lmstudio.ai/models/qwen3.6-27b)                                                           | [huggingface.co](https://huggingface.co/Qwen/Qwen3.6-27B)                         |
| qwen3.6-28b-reap-i1                  | [lmstudio.ai](https://lmstudio.ai/models/qwen3.6-28b-reap-i1)              | [huggingface.co](https://huggingface.co/Qwen/Qwen3.6-28B)                         |
| starcoder2-15b-instruct-v0.1         | [lmstudio.ai](https://lmstudio.ai/models/starcoder2-15b-instruct-v0.1)     | [huggingface.co](https://huggingface.co/bigcode/starcoder2-15b-instruct-v0.1)     |
| wizardcoder-python-13b-v1.0          | [lmstudio.ai](https://lmstudio.ai/models/wizardcoder-python-13b-v1.0)      | [huggingface.co](https://huggingface.co/WizardLM/WizardCoder-Python-13B-V1.0)     |
| pandalyst_13b_v1.0                   | [lmstudio.ai](https://lmstudio.ai/models/pandalyst-13b-v1.0)               | [huggingface.co](https://huggingface.co/LazarusNLP/Pandalyst-13B-v1.0)            |
| glm-4.7-flash-reap-23b-a3b-i1        | [lmstudio.ai](https://lmstudio.ai/models/glm-4.7-flash-reap-23b-a3b-i1)    | https://huggingface.co/ZAI-org/GLM-4.7-Flash-REAP-23B-A3B-I1                      |
| devstral-small-2-24b-instruct-2512@q3_k_s | [lmstudio.ai](https://lmstudio.ai/models/devstral-small-2-24b-instruct-2512) | [huggingface.co](https://huggingface.co/Devstral/Devstral-Small-2-24B-Instruct-2512) |
| gemma-4-26b-a4b-it-qat                | [lmstudio.ai](https://lmstudio.ai/models/gemma-4-26b-a4b-it-qat)               | [huggingface.co](https://huggingface.co/google/gemma-4-26b-a4b-it)                |
| qwen3-coder-reap-25b-a3b-i1@q4_k_s    | [lmstudio.ai](https://lmstudio.ai/models/qwen3-coder-reap-25b-a3b-i1)           | [huggingface.co](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)        |
| google_gemma-4-26b-a4b-it             | — (bartowski GGUF, kein LMS-Eintrag)                                            | [huggingface.co](https://huggingface.co/bartowski/Gemma-4-26B-A4B-It-GGUF)        |
| zai-org/glm-4.6v-flash               | [lmstudio.ai](https://lmstudio.ai/models/glm-4.6v-flash)                   | https://huggingface.co/ZAI-org/GLM-4.6V-Flash                                     |

---
### Bekannte Einschränkungen

- **MambaCache/SSM-Modelle** (z.B. Qwen 3 Next): KV-Cache-Quantisierung kann zu Engine-Fehlern führen (`AttributeError: 'MambaCache' object has no attribute 'offset'`). Workaround: KV-Quantisierung deaktivieren.
- **LM Studio Engine-Versionen**: Vor 1.4.1 (Juni 2025) war die KV-Quantisierungs-Konfiguration im Python-SDK fehlerhaft (`llamaKCacheQuantizationType`/`llamaVCacheQuantizationType` wurden ignoriert). Seit 1.4.1 behoben.
- **MLX-Backend (macOS)**: Version-abhängige Bugs mit `tree_reduce`-Import bei KV-Quantisierung (Qwen3.6). Meist durch Update des MLX-Extensions-Pakets behebbar.
- **LM Studio GUI**: KV-Quantisierungseinstellungen sind aktuell NUR über LM Studio Python SDK konfigurierbar, nicht über die Desktop-Oberfläche.

---
### Unified KV-Cache (LM Studio Standard)
LM Studio verwendet Unified KV-Cache: Der KV-Speicher wird zwischen allen Slots geteilt, nicht pro Slot dupliziert.
→ Die Anzahl Slots (`n_slots`) beeinflusst den VRAM-Verbrauch NICHT.
→ Empfehlung: `n_slots = 4` für alle Modelle (maximale Parallelität ohne VRAM-Nachteil).