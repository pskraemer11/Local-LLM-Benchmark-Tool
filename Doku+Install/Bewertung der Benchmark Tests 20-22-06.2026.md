### Bewertung der Benchmark Tests 20. bis 22.06.2026 ###

**Hinweis:** Dieses Dokument beschreibt historische Ergebnisse vom alten Benchmark-System (v21/v22). 
Das aktuelle System (v10) verwendet `run_benchmarks_v10.py` als Launcher mit 10 Benchmarks und 4 Pipelines (Custom, LM-Eval, EvalPlus, Agentic). 
Siehe `Architektur+Flow_Python-Benchmark-Skript_v24.md` fur die aktuelle Architektur.

## 1. Durchschnittliche Laufzeit pro Benchmark

**Wichtig:** evalplus (HEval+, MBPP+) und lmeval nutzen SampleSize=8, d. h. **nur 8 Aufgaben pro Benchmark** (nicht 164/378/~350). 
Siehe Tabelle rechts für die tatsächliche Anzahl Inference-Calls.

Geschätzte Zeiten pro Modell (SS=8, Tokens ≈ 1500/Task):

| Modell            | tok/s| DS1000 (8) | HEval+ (8) | MBPP+ (8) | lmeval ×6 (6×8) | **Total** |
|-------------------|-----:|-----------:|-----------:|----------:|----------------:|----------:|
| Mistral 7B        |  45  |    4 min   |    4 min   |    4 min  |     24 min      |    ~1 h   |
| Granite 4 H Tiny  |  92  |    2 min   |    2 min   |    2 min  |     12 min      |    ~0.5 h |
| GPT-OSS 20B       |  98  |    2 min   |    2 min   |    2 min  |     12 min      |    ~0.5 h |
| Mathstral 7B      |  43  |    5 min   |    4 min   |    4 min  |     24 min      |    ~1 h   |
| ERNIE 4.5         |  29  |    7 min   |    7 min   |    7 min  |     42 min      |    ~1.5 h |
| **Qwen2.5 Coder** |   7  |   30 min   |   30 min   |   30 min  |    180 min      |  **~5 h** |

**Kernerkenntnis:** Alle Benchmarks laufen mit SampleSize=8 → **nur 8 Inference-Calls pro Benchmark** (lmeval = 6 Benchmarks × 8 = 48 Calls). 
Die Totzeit pro Modell liegt in der Praxis bei 15–60 min – die längeren Zeiten entstehen durch LM-Studio-Latenz (große Modelle), Python-Testausführung (evalplus.evaluate) und Timeout-Reserven.
DS1000+PandasEval sind mit SS=8 in <30 min erledigt.

---

## 2. Korrelation: Langsame/ineffiziente Modelle ↔ Hohe CPU-Last

Klare Muster aus den gemessenen Daten:

| Modell              | tok/s | CPU%  | GPU%  | VRAM      | VRAM-Frei| Architektur          |
|---------------------|------:|------:|------:|----------:|---------:|:--------------------:|
| *GPT-OSS 20B*       |  98   |  32%  | *88%* |  15.6 GB  |  0.4 GB  | Dense (Q6_K)         |
| *Granite 4 H Tiny*  |  92   |  45%  | *82%* |  14.5 GB  |  1.5 GB  | *MoE* (1B aktiv)     |
| *LFM2.5 8B A1B*     |  82   |  47%  |  76%  |  10.7 GB  | *5.3 GB* | *MoE* (1.5B aktiv)   |
| *ERNIE 4.5*         |  29   | *75%* | --38% | *15.0 GB* |  1.0 GB  | *MoE* (3B aktiv)     |
| *Phi 4*             |  11   | *66%* |  58%  |  13.4 GB  |  2.6 GB  | Dense (12.1 GB Q6_K) |
| *Qwen2.5 Coder 14B* |   7   |  48%  |  58%  | *14.8 GB* |  1.2 GB  | Dense (12.1 GB + KV) |
| *Pandalyst 13B*     |   6   | *71%* | *77%* | *15.8 GB* |  0.2 GB  | Dense                |
| *Mistral 7B*        |  45   |  20%  | *96%* |  12.3 GB  | *3.7 GB* | Dense                |

**Klare Korrelationen:**

**a) Hohe CPU-Last = VRAM-Engpass + Swapping**
- Modelle mit <2 GB VRAM-Reserve zeigen CPU% > 60% (ERNIE 75%, Pandalyst 71%, Phi 4 66%) => aber nicht immer! Gegenbeispiele: GPT-OSS 20B, Granite 4H Tiny und Qwen2.5 Coder 14B.
- Wenig VRAM → LM Studio muss K/V-Cache oder Layer auf CPU auslagern → CPU-Last steigt
- *Gegenbeispiel:* DeepSeek Coder v2 Lite: 13% CPU, 99% GPU bei 15.6 GB (weil MoE mit nur 2.4B aktiv → KV-Cache klein)

**b) Hohe GPU% ≠ hohe tok/s**
- Starcoder2: 98% GPU aber nur 17 tok/s (inkomplette GPU-Auslastung durch Bandbreitenlimit)
- Mistral 7B: 96% GPU und 45 tok/s (optimale Nutzung)
- Gemma 4 12B: 95% GPU, 36 tok/s

**c) MoE-Modelle sind NICHT automatisch CPU-lastig**
- Granite 4 H Tiny (MoE, 1B aktiv): 45% CPU, 82% GPU, 92 tok/s ✅
- LFM2.5 (MoE, 1.5B aktiv): 47% CPU, 76% GPU, 82 tok/s ✅
- ERNIE 4.5 (MoE, 3B aktiv): **75% CPU, 38% GPU** ❌ → *weil 21B total bei Q4_K_M = 13.5 GB + große KV-Heads*

**d) Hauptbremsen pro Modell:**

| Engpass                         | Modelle                                             | Symptom                                     |
|---------------------------------|-----------------------------------------------------|---------------------------------------------|
| **VRAM-Kollaps** (<0.5 GB frei) | Pandalyst (0.2 GB), Qwen2.5 (1.2 GB)                | CPU% ~50-70%, GPU% <80%                     |
| **Model-GGUF zu groß**          | Codestral (13.3 GB + KV), Granite 4.1 (9.4 GB + KV) | Hohe Latenz trotz mittlerer tok/s           |
| **KV-Cache unquantisiert**      | Alle mit >32k Kontext                               | Quadratischer VRAM-Zuwachs mit Kontextlänge |
| **Ineffiziente Architektur**    | Qwen2.5 Coder 14B (dense, 12.1 GB)                  | 7 tok/s bei 58% GPU – Bandbreitenlimit      |

---

## 3. Verbesserungsmöglichkeiten in LM Studio

Aktuell nutzt das Projekt **keinerlei** LM Studio-Optimierungsparameter. Alle Einstellungen sind LM-Standard. Hier die Hebel:

### a) KV-Cache Quantisierung (größter Hebel)
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

### b) Context Length reduzieren (`n_ctx`)
Per Modell anpassbar. Aktuell wird immer die volle Kontextlänge geladen:
- phi-4: nur 16K nötig, aber viel größere Standardeinstellung
- starcoder2: 16K reichen
- mathstral/mistral-7b: 32K reichen
- **Spareffekt:** Halbe Kontextlänge = halber KV-Cache = mehr VRAM für schnellere Inference

### c) GPU Offloading (`n_gpu_layers`)
Standardmäßig lädt LM Studio alle Layer auf GPU wenn VRAM reicht. Bei Modellen nahe VRAM-Limit:
- Automatische Layer-Verteilung auf CPU (langsamer)
- Manuell prüfbar: `lms ps --json` zeigt GPU/CPU-Layer-Verteilung

### d) Flash Attention
LM Studio aktiviert Flash Attention automatisch wenn die GPU es unterstützt (RTX 5070 Ti = Ada Lovelace/Blackwell → ja).
- Spart VRAM bei langen Kontexten
- Keine manuelle Konfiguration nötig

### e) Threading
`num_concurrent=1` in lm_eval ist korrekt (VRAM-Limit). Parallelisierung würde Swapping auslösen.
- `lms server --threads N` könnte CPU-bound Modelle (ERNIE, Phi 4) um 10-20% beschleunigen

### f) Prioritäten-Ranking

| Maßnahme                              | Wirkung                                   | Aufwand | Modell-Zielgruppe               |
|---------------------------------------|-------------------------------------------|---------|---------------------------------|
| **KV-Quant Q8_K+Q4_V**                | VRAM↓ 62% → mehr Reserve → min. 20% Speed↑| Gering  | Alle (außer Gemma 4)            |
| **KV-Quant Q8_K+FP16_V**              | VRAM↓ 25%, kein Qualitätsverlust          | Gering  | Gemma 4, Qwen2.5-kritisch       |
| **Context Length optimieren**         | VRAM↓ proportional                        | Gering  | Alle mit >32k Kontext           |
| **Threads erhöhen**                   | CPU↓ 10-20%                               | Gering  | CPU-bound (ERNIE, Phi 4)        |
| **Niedrigere GGUF-Stufe** (Q4 statt Q6)| VRAM↓ 30-40%, leichter Qualitätsverlust  | Mittel  | VRAM-kritisch (Codestral, Granite 4.1) |
| **Flash Attention aktivieren**        | VRAM↓ bei langem Kontext                  | Keiner  | Standard seit LM Studio 1.4+    |

### g) Quick-Win für den nächsten Lauf
Höchste Priorität: **KV-Quantisierung aktivieren** (GUI: Hardware-Tab → Cache Quantization Type oder Python SDK: `llamaKCacheQuantizationType="q8_0"`, `llamaVCacheQuantizationType="q4_0"`) 
 → spart sofort ~2-4 GB VRAM bei Modellen mit langem Kontext. Qwen2.5 Coder hätte dann mehr Reserve, weniger CPU-Swapping → von 7 auf geschätzt 10-12 tok/s.