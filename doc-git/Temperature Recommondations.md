# Temperaturempfehlungen je Modell und Aufgabe

**Stand:** 2026-08-06 · **Methode:** Offizielle Hugging-Face-Model-Cards, Vendor-Docs/Blogs (Mistral, Qwen, DeepSeek, Microsoft, IBM, OpenAI, Google, Zhipu, Moonshot, NVIDIA, Liquid AI, Baidu, JetBrains, Cohere).

## Ausgangslage

Die bisher laufenden Benchmarks nutzen bei Modellen ohne LMS-JSON-Config die `BENCHMARK_CATEGORY_DEFAULTS` (`src/benchmark_config.py:241`):

| Aufgabe   | temp | top_p | max_tokens | thinking |
|-----------|------|-------|------------|----------|
| coding    | 0.0  | 1.0   |   4096     | False    |
| math      | 0.7  | 0.95  |   4096     | False    |
| knowledge | 0.0  | 1.0   |   4096     | False    |
| agentic   | 0.3  | 0.95  |   4096     | False    |

**Befund:** temp=0.0 für Coding/Knowledge ist nur für einen Teil der Modelle angemessen. 

Die offiziellen Empfehlungen reichen von **0.0** (Granite 4, Phi-4, DeepSeek-Coder, Ministral, LFM2) bis **1.0** (GPT-OSS, Gemma-4, Qwen3.6, North-Mini-Code, MiroThinker, Nemotron-3). 
Viele Coding-spezialisierte Modelle empfehlen offiziell 0.15–0.7.

## Neue Empfehlung:
** 1. Reasoning/Thinking-Modelle pauschal t=0.6 (top_p 0.95) für alles — nicht die Kategorie-Werte übernehmen.** 

Begründung:
Offizielle Thinking-Werte sind überall 0.6/0.95, nicht 0.2:**
- DeepSeek-R1-Distill: **0.6/0.95** ("0.6 is recommended", Bereich 0.5–0.7)
- Qwen3-14B Thinking: **0.6/0.95** (Card warnt explizit: *"DO NOT use greedy"*)
- Qwen3.6-27B Coding/WebDev im Thinking-Mode: **0.6/0.95**
- Nemotron-Cascade: **0.6/0.95** · Kimi-K2: **0.6** · GLM-4.7 SWE-bench: **0.7/1.0**

Der Coding-Wert 0.2 aus dem Vorschlag gilt für **Instruct-Coder** (Qwen2.5-Coder, Codestral, Devstral) — Thinking-Modelle werden von den Herstellern im Coding explizit mit 0.6 gefahren. 
Low-temp/greedy ist bei Thinking-Modellen sogar kontraproduktiv (Repetitions-Kollaps im Reasoning-Pfad, daher die "DO NOT use greedy"-Warnung).

**2. Warum 0.6 statt 0.7:** 0.6 ist der Modus der offiziellen Angaben (R1, Qwen3, Cascade, Kimi, Qwen3.6-Coding). 
0.7 (Math) liegt im R1-Bereich, aber 0.6 deckt alle 4 Kategorien ab. 
top_p 0.95 = offizieller Standard bei allen Thinking-Karten.

**Vorschlag für die neuen Defaults (Fallback ohne JSON-Config):**

| Aufgabe   | instruct | thinking |
|-----------|----------|----------|
| coding    |   0.2    | **0.6**  |
| knowledge |   0.6    | **0.6**  |
| agentic   |   0.6    | **0.6**  |
| math      |   0.7    | **0.6**  |
| top_p     |   1.0    | **0.95** |

**Einschränkungen:**
- Ausnahmen: GPT-OSS (1.0/1.0), Gemma-4 (1.0/0.95), MiroThinker (1.0/0.95), Qwen3.6-general (1.0/0.95), Nemotron-3-Reasoning (1.0/1.0) — offiziell höher. 
        0.6 bleibt ein Kompromiss, aber deutlich näher an den Empfehlungen als 0.0.
- **Achtung Kompatibilität:** bisherige Benchmark-Lauf nutzen noch temp=0.0 (category-default) — nach Default-Änderung wären alte Scores mit einem neuen Lauf nicht direkt vergleichbar. 

## Umsetzung & Design-Entscheidung (2026-08-06)

**Architektur:** Seit 2026-08-05 liefert die LMS-JSON-Config die Generations-Parameter
(Single-Source-of-Truth; `MODEL_TEMP_OVERRIDES` wurden entfernt). **Seit 2026-08-06 gilt
das Sampling-Design unten** (Ausnahme-Tabelle > Defaults; JSON-temp/top_p nur noch GUI).

**Grundsätzlicher Konflikt:** Die LMS-JSON-Config kann pro Modell nur **einen**
Temperatur-/top_p-Wert halten (gilt für ALLE Benchmark-Kategorien). Die neuen Defaults
unterscheiden aber pro Kategorie (coding 0.2, knowledge 0.6, agentic 0.6, math 0.7).
Eine Kategorie-Differenzierung ist über die JSON-Config also **nicht abbildbar**.

**Lösung (Entscheidung, Option „Tabelle > Defaults, JSON-temp ignoriert"):**
1. **`MODEL_CATEGORY_SAMPLING`** in `src/benchmark_config.py`: Ausnahme-Tabelle
   Modell × Kategorie (temperature/top_p, ~30 Basis-Modelle, alle mit abweichenden
   oder kategorie-spezifischen Werten). Zellen basieren auf der Übersichtstabelle
   unten (offiziell; sonst BP-Mittelwert der angegebenen Spannen).
2. **Precedence:** Tabellen-Zelle > `BENCHMARK_THINKING_DEFAULTS` (0.6/0.95) bzw.
   `BENCHMARK_CATEGORY_DEFAULTS` (0.2/0.6/0.6/0.7). Gilt für Instruct- **und**
   Thinking-Läufe — so greifen auch die dokumentierten Thinking-Ausnahmen
   (GPT-OSS 1.0/1.0, Gemma-4 1.0/0.95, Nemotron-3-Reasoning 1.0/1.0) als Zellen.
3. **JSON-temp/top_p werden für Benchmarks ignoriert** (gelten nur noch für die
   GUI-Nutzung). Aus den JSON-Configs kommen weiterhin top_k, min_p,
   enable_thinking, reasoning_effort, max_tokens/ctx.
4. `_source` zeigt die Herkunft: `benchmark-table` | `thinking-default` | `category-default`.
5. **Abweichung vom 05.08-Prinzip** („LMS-JSON = einzige Quelle"): begründet, weil
   die JSON-Config keine Kategorie-Differenzierung ausdrücken kann. Die Tabelle ist
   dokumentierte Datenlogik mit Quellen (kein obskures `MODEL_TEMP_OVERRIDES`-Reload);
   alle Nicht-Temperatur-Parameter bleiben JSON-gespeist.
6. **Kompromisse:** MiroThinker (1.0/0.95) und Qwen3.6-general (1.0/0.95) laufen im
   Thinking-Lauf mit flat 0.6/0.95 (s. Einschränkungen; ein Tabellenwert würde auch
   den Instruct-Lauf treffen, dort gilt 0.7/0.8).

**Umsetzungsdetails (2026-08-06, uncommittet):**
- `BENCHMARK_CATEGORY_DEFAULTS`: coding 0.0→0.2, knowledge 0.0→0.6, agentic 0.3→0.6; math 0.7 bleibt
- neu `BENCHMARK_THINKING_DEFAULTS` (0.6/0.95, `enable_thinking: True`); Auswahl in
  `get_model_config` über `is_thinking_enabled` + `REASONING_PATTERNS` (ergänzt um
   Registry-thinking-Modelle: qwen3.5/3.6, mirothinker, kimi, glm-4.7/4.6v, phi-4,
   qwen3-14b, qwen3-coder-reap, `thinking`-Namensbestandteil)
- neu `MODEL_CATEGORY_SAMPLING` (Ausnahme-Tabelle, s. o.); Matching über den
  normalisierten Registry-Key (`_normalized_lms_key`), erste Treffer-Zeile gewinnt
- `get_model_config`: Tabellen-Zelle (Instruct UND Thinking) > Thinking-/Kategorie-
  Defaults; JSON-Merge nur noch für Nicht-Temperatur-Felder
- 55 LMS-JSON-Configs aktualisiert (temp + top_p, Format `{checked, value}` erhalten)
- Matching-Bugfixes in `benchmark_config.py`: `@quant`-Suffixe (z. B. `@q5_0`), Variant-
  Suffixe (`-qat`/`-ud`/`-imatrix`), Publisher-Fallback (Repacks unter anderem Publisher)
- **Bekannt:** LM Studio hält Config-Werte im Speicher; ein einmaliger Revert (GLM-4.7-Flash)
  beobachtet → für dauerhafte Wirkung Werte in LMS-GUI übernehmen oder LMS neu starten.
  Der laufende SS=30-Benchmark wird inkonsistent (bereits gelaufene Evals: alte Werte).


## Verarbeiter-Repacks → Basismodell (Zuordnung)

Viele Registry-Einträge sind keine Hersteller-Modelle, sondern **Quantisierungen/Repacks** (unsloth, bartowski, mradermacher, lmstudio-community, noctrex, vinpix, gabriellarson, intel/AutoRound, quietimpostor) 
oder **nachträgliche Fine-Tunes/REAPs**. Diese Repacks haben meist keine eigene Modellkarte mit Sampling-Empfehlungen. 
Recherchiert wurde daher **immer das Basismodell auf der echten Herstellerseite**; die Werte in der Tabelle gelten für alle Quants eines Basismodells.

| Registry-Eintrag (Verarbeiter)                                        | Verarbeiter               | Basismodell (Hersteller)                  | Hinweis                            |
|-----------------------------------------------------------------------|---------------------------|-------------------------------------------|------------------------------------|
| `unsloth/qwen3-coder-30b-a3b-instruct`                                | Unsloth (GGUF)            | Qwen3-Coder-30B-A3B-Instruct              | offizielle Best Practices 0.7/0.8  |
| `mradermacher/qwen3-coder-reap-25b-a3b(-i1)`                          | MRadermacher (GGUF)       | cerebras/Qwen3-Coder-REAP-25B-A3B         | erbt Qwen3-Coder-Werte             |
| `qwen/qwen2.5-coder-14b-instruct@*`                                   | Qwen (offizielle Quants)  | Qwen2.5-Coder-14B-Instruct                | Familien-Default 0.7/0.8           |
| `unsloth/qwen3-30b-a3b-instruct-2507`, `intel/qwen3-30b-…-autoround`  | Unsloth / Intel AutoRound | Qwen3-30B-A3B-Instruct-2507               | 0.7/0.8                            |
| `Qwen/Qwen3.5-9B-GGUF`, `qwen/qwen3.5-9b`                             | Qwen                      | Qwen3.5-9B                                | Thinking 1.0/0.95, Coding 0.6/0.95 |
| `unsloth/qwen3.6-27b`, `-mtp`; `mradermacher/qwen3.6-27b-i1`,         | Unsloth / MRadermacher    | Qwen3.6-27B (REAP-Varianten: cerebras)    | Thinking 1.0/0.95, Coding 0.6/0.95 |
|        `qwen3.6-28b-reap-i1@*`                                        |
| `intel/mirothinker-v1.5-30b-…`                                        | Intel AutoRound           | miromind-ai/MiroThinker-v1.5-30B          | 1.0/0.95                           |
| `unsloth/phi-4`                                                       | Unsloth (GGUF)            | microsoft/phi-4                           | 0.0                                |
| `unsloth/gemma-4-26b-a4b-it`, `bartowski/google_gemma-4-26b-a4b-it@*`,| Unsloth/Bartowski/...     |google/gemma-4-12B-it bzw. -19B/-26B-A4B-it| 1.0/0.95, top_k 64                 |
|    `mradermacher/gemma-4-26b-a4b-it-i1@*`, `gemma-4-19b-a4b-it-reap-i1@*`,| ...MRadermacher/Google|
|    `google/gemma-4-*-qat`                                             |
| `unsloth/ernie-4.5-21b-a3b-pt`, `noctrex/ernie-4.5-21b-a3b-pt_moe@*`  | Unsloth / Noctrex         | baidu/ERNIE-4.5-21B-A3B-PT                | Qianfan 0.8/1.0                    |
| `unsloth/devstral-small-2-24b-instruct-2512`                          | Unsloth (GGUF)            | mistralai/Devstral-Small-2-24B-Instruct-2512 | 0.15                            |
| `bartowski/mistralai_magistral-small-2509`                            | Bartowski (GGUF)          | mistralai/Magistral-Small-2509            | 0.7/0.95                           |
| `lmstudio-community/ministral-3-14b-instruct-2512`                    | LM Studio                 | mistralai/Ministral-3-14B-Instruct-2512   | <0.1                               |
| `gabriellarson/mamba-codestral-7b-v0.1`                               | Gabriellarson (GGUF)      | mistralai/Mamba-Codestral-7B-v0.1         | kein Wert, Mistral-Bereich         |
| `unsloth/januscoder-14b`                                              | Unsloth (GGUF)            | internlm/JanusCoder-14B (Basis Qwen3-14B) | kein Wert → Qwen3                  |
| `unsloth/north-mini-code-1.0`                                         | Unsloth (GGUF)            | CohereLabs/North-Mini-Code-1.0            | 1.0/0.95                           |
| `nerdsking/nerdsking-python-coder-7b-i`                               | Nerdsking (Fine-Tune)     | Nerdsking-Python-Coder-7B-i               | 0.1 (Eval)                         |
| `mradermacher/deepseek-coder-33b-instruct`                            | MRadermacher (GGUF)       | deepseek-ai/deepseek-coder-33b-instruct   | greedy                             |
| `lmstudio-community/deepseek-coder-v2-lite-instruct`                  | LM Studio                 | deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct | 0.3 (vLLM)                       |
| `lmstudio-community/deepseek-r1-distill-qwen-14b`                     | LM Studio                 | deepseek-ai/DeepSeek-R1-Distill-Qwen-14B  | 0.6/0.95                           |
| `lmstudio-community/internlm2-math-plus-20b`                          | LM Studio                 | internlm/internlm2-math-plus-20b          | greedy + CoT                       |
| `mradermacher/kimi-linear-reap-35b-a3b-instruct.i1`                   | MRadermacher (GGUF)       | moonshotai/Kimi-Linear (REAP: cerebras)   | Kimi-K2: 0.6                       |
| `mradermacher/nemotron-cascade-14b-thinking`                          | MRadermacher (GGUF)       | nvidia/Nemotron-Cascade-14B-Thinking      | 0.6/0.95                           |
| `quietimpostor/nemotron-3-nano-reap-21b-a3b`                          | QuietImpostor (REAP)      | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 | Reasoning 1.0/1.0, Tool 0.6/0.95  |
| `noctrex/lfm2-24b-a2b_moe`                                            | Noctrex (MXFP4)           | LiquidAI/LFM2-24B-A2B                     | 0.1                                |
| `unsloth/glm-4.7-flash`, `-reap-23b-a3b`                              | Unsloth                   | zai-org/glm-4.7-flash (REAP: cerebras)    | 1.0/0.95, SWE 0.7/1.0              |
| `essentialai/essentialai/rnj-1`                                       | (Registry-Name)           | EssentialAI/rnj-1                         | [0, 0.6]                           |

**Korrigierte Registry-Links** (Repo-Namen weichen ab): `essentialai/essentialai/rnj-1` → `EssentialAI/rnj-1`; `google/gemma-4-12b-it-qat` (BF16) existiert nicht → nur QAT-q4_0-Repos; 
        `mradermacher/qwen3.6-27b-i1` existiert als Repo nicht (nur i1-Repacks von Finetunes, Basis Qwen3.6-27B).

## Legende

- **Fett** = offizielle Angabe des Herstellers (Karte/Docs/Beispielcode).
- `(BP)` = keine offizielle Angabe; abgeleiteter Best-Practice-Wert (auf Basis der Familienwerte bzw. üblicher Praxis: Coding 0.2–0.3, Agentic 0.2–0.6, Math 0.2–0.7, Knowledge 0.6–0.7).
- „–" = für diese Aufgabe nicht geeignet / nicht empfohlen.

## Übersichtstabelle (Basis-Modelle, Quants zusammengefasst)

| Modell (Registry-Key)                                                               | Offizielle Empfehlung (temp/top_p)                                       | Coding               | Knowledge      | Agentic           | Math                |
|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------|----------------------|----------------|-------------------|---------------------|
| Qwen3-Coder-30B-A3B (`unsloth/qwen3-coder-30b-a3b-instruct`)                        | *0.7 / 0.8*, top_k 20, rep_pen 1.05                                      | *0.7/0.8*            | *0.7/0.8*      | *0.7/0.8*         | *0.7/0.8*           |
| Qwen3-Coder-REAP-25B (`mradermacher/qwen3-coder-reap-25b-a3b…`)                     | keine eigene Angabe → erbt Qwen3-Coder                                   |  0.7/0.8 (BP)        |  0.7/0.8 (BP)  | 0.7/0.8 (BP)      | 0.7/0.8 (BP)        |
| Qwen2.5-Coder-14B (`qwen/qwen2.5-coder-14b-instruct@*`)                             | Familien-Default *0.7 / 0.8* (Qwen2.5)                                   |  0.2–0.3 (BP)        | *0.7/0.8*      | 0.5–0.7 (BP)      | *0.7/0.8*           |         
| Qwen3-30B-A3B-Instruct-2507 (`unsloth/qwen3-30b-a3b-instruct-2507`, Intel-q2ks)     | *0.7 / 0.8*, top_k 20, min_p 0                                           |  0.7/0.8 (BP)        |  0.7/0.8 (BP)  | 0.7/0.8 (BP)      | 0.7/0.8 (BP)        |
| Qwen3-14B (`qwen/qwen3-14b`)                                                        | Thinking *0.6 / 0.95*; Non-Thinking *0.7 / 0.8*                          | *0.6/0.95*           | *0.6/0.95*     | 0.6/0.95 (BP)     | *0.6/0.95*          |
| Qwen3.5-9B (`qwen/qwen3.5-9b`, `Qwen/Qwen3.5-9B-GGUF`)                              | Thinking *1.0 / 0.95* (pres_pen 1.5); Coding/WebDev *0.6 / 0.95*;        | *0.6/0.95*           | *1.0/0.95*     | 1.0/0.95 (BP)     | *1.0/1.0*           |
                                                                                      |             / Instruct *0.7 / 0.8*; Instruct-Reasoning *1.0 / 1.0*       |                      |                |                   |                     |
| Qwen3.6-27B (`unsloth/qwen3.6-27b`, -mtp, `mradermacher/qwen3.6-27b-i1`, -28b-reap) | Thinking *1.0 / 0.95*; Coding/WebDev *0.6 / 0.95*; Instruct *0.7 / 0.8*  | *0.6/0.95*           | *1.0/0.95*     | *1.0/0.95*        | 0.6–1.0/0.95 (BP)   |
| MiroThinker-v1.5-30B (`intel/mirothinker-v1.5-30b-q2ks-mixed-autoround`)            | *1.0 / 0.95*, rep_pen 1.05, ctx 262144                                   |  1.0/0.95 (BP)       | *1.0/0.95*     | *1.0/0.95*        | 1.0/0.95 (BP)       |
| DeepSeek-R1-Distill-Qwen-14B (`lmstudio-community/deepseek-r1-distill-qwen-14b`)    | *0.5–0.7 (0.6 empfohlen) / 0.95*                                         | *0.6/0.95*           | *0.6/0.95*     | *0.6/0.95*        | *0.6/0.95*          |
| DeepSeek-Coder-33B-Instruct (`mradermacher/deepseek-coder-33b-instruct`)            | Beispiel *greedy* (do_sample=False, top_k 50, top_p 0.95)                | *greedy* (0.0–0.3 BP)|  0.7 (BP)      | 0.2 (BP)          | 0.5 (BP)            |
| DeepSeek-Coder-V2-Lite (`lmstudio-community/deepseek-coder-v2-lite-instruct`)       | vLLM-Beispiel *0.3*; transformers greedy                                 | *0.3*                |  0.7 (BP)      | 0.2–0.3 (BP)      | 0.3–0.5 (BP)        |
| GPT-OSS-20B (`openai/gpt-oss-20b`)                                                  | *1.0 / 1.0* ("recommended sampling parameters", GitHub-README)           | *1.0/1.0*            | *1.0/1.0*      | *1.0/1.0*         | *1.0/1.0*           |
| Phi-4 (`unsloth/phi-4`)                                                             | *0.0* (Card-Metadaten)                                                   | *0.0*                | *0.0*          | 0.0–0.3 (BP)      | *0.0*               |
| Gemma-4 12B/26B-A4B (+QAT, REAP) (`google/gemma-4-*`, `unsloth/gemma-4-*`,          | *1.0 / 0.95*, top_k 64 (standardisiert für alle Aufgaben)                | *1.0/0.95*           | *1.0/0.95*     | *1.0/0.95*        | *1.0/0.95*          |
|      `mradermacher/gemma-4-*`, `bartowski/google_gemma-4-*`)                        |                                                                          |                      |
| rnj-1 (`essentialai/rnj-1`)                                                         | *Bereich [0, 0.6]*; Beispiele 0.2 / 0.95; Tool-Use-Modell                | *0.2/0.95*           |  0.2/0.95 (BP) |  *0.2/0.95*       | 0.2/0.95 (BP)       |
| Granite-4.0-H-Tiny (`ibm-granite/granite-4.0-h-tiny`)                               | *0.0 / 1.0*, top_k 0 (IBM-Docs: „work best with temperature 0")          | *0.0/1.0*            | *0.0/1.0*      | *0.0/1.0*         | *0.0/1.0*           |
| Granite-4.1 8B/30B (`ibm-granite/granite-4.1-8b`, `-30b`)                           | Familienregel *0.0 / 1.0*, top_k 0                                       | *0.0/1.0*            | *0.0/1.0*      | *0.0/1.0*         | *0.0/1.0*           |
| Codestral-22B (`mistralai/codestral-22b-v0.1`)                                      | Beispiele *temp=0.0*; FIM-Docs: Bereich 0.0–0.7                          | *0.0–0.3*            |  0.7 (BP)      | 0.2 (BP)          | 0.3 (BP)            |
| Mamba-Codestral-7B (`gabriellarson/mamba-codestral-7b-v0.1`)                        | keine Angabe → Mistral-Bereich                                           |  0.0–0.3 (BP)        |  0.7 (BP)      | 0.2 (BP)          | 0.3 (BP)            |
| Devstral-Small-2-24B (`unsloth/devstral-small-2-24b-instruct-2512`)                 | Beispiele *0.15*                                                         | *0.15*               |  0.4 (BP)      | *0.15* (SWE-Agent)| 0.3 (BP)            |
| Magistral-Small-2509 (`bartowski/mistralai_magistral-small-2509`)                   | *0.7 / 0.95* (ausdrücklich)                                              | *0.7/0.95*           | *0.7/0.95*     | *0.7/0.95*        | *0.7/0.95*          |
| Ministral-3-14B (`lmstudio-community/ministral-3-14b-instruct-2512`)                | *temp < 0.1* ("daily driver"); Beispiele 0.15                            | *<0.1–0.15*          | *<0.1–0.15*    | *<0.1–0.15*       | *<0.1–0.15*         |
| JanusCoder-14B (`unsloth/januscoder-14b`)                                           | keine Angabe → Qwen3-Familie (0.7/0.8)                                   |  0.2–0.3 (BP)        |  0.7/0.8 (BP)  | 0.2 (BP)          | 0.5 (BP)            |
| North-Mini-Code-1.0 (`unsloth/north-mini-code-1.0`)                                 | *1.0 / 0.95* (ausdrücklich, auch für Benchmarks)                         | *1.0/0.95*           | *1.0/0.95*     | *1.0/0.95*        | *1.0/0.95*          |
| Nerdsking-Python-Coder-7B (`nerdsking/nerdsking-python-coder-7b-i`)                 | HumanEval-Konfig *0.1*, do_sample=False                                  | *0.1*                |  0.7 (BP)      | 0.2 (BP)          | 0.2–0.3 (BP)        |
| GLM-4.7-Flash (`unsloth/glm-4.7-flash`, -reap-23b)                                  | Eval-Default *1.0 / 0.95*; SWE-bench *0.7 / 1.0*; τ²-Bench *0*           | *0.7/1.0* (SWE)      | *1.0/0.95*     | *0* (τ²)          | *1.0/0.95*          |
| GLM-4.6V-Flash (`zai-org/glm-4.6v-flash`)                                           | *0.8 / 0.6*, top_k 2, rep_pen 1.1                                        |  0.8/0.6 (visuell)   | 0.8/0.6        | 0.8/0.6           | 0.8/0.6             |
| ERNIE-4.5-21B-A3B-PT (`unsloth/ernie-4.5-21b-a3b-pt*`,                              | Karte: k.A.; gehostet (Qianfan) *0.8 / 1.0*; Baidu-Tuning: 0.3 für Fokus |  0.2–0.3 (BP)        | *0.8/1.0*      | 0.2–0.8, tool     | 0.2–0.3 (BP)        |
|               ... `noctrex/ernie-4.5-21b-a3b-pt_moe*`)                              |                                                                          |                      |                |   use low (BP)    |                     |
| Falcon3-10B-Instruct (`tiiuae/falcon3-10b-instruct`)                                | keine Angabe (Quickstart greedy)                                         |  0.2/0.95 (BP)       |0.6–0.7/0.9 (BP)| 0.2–0.3 (BP)      | 0.2/0.95 (BP)       |
| Falcon3-Mamba-7B (`tiiuae/falcon3-mamba-7b-instruct`)                               | keine Angabe                                                             |  0.2/0.95 (BP)       |0.6–0.7/0.9 (BP)| 0.2–0.3 (BP)      | 0.2/0.95 (BP)       |
| Mellum2-12B (`jetbrains/mellum2-12b-a2.5b-instruct`, -thinking_moe)                 | Quickstart *0.6 / 0.95*, top_k 20                                        | *0.6/0.95*           | *0.6/0.95*     | *0.6/0.95*        | *0.6/0.95*          |
| Kimi-Linear-REAP-35B (`mradermacher/kimi-linear-reap-35b-a3b-instruct.i1`)          | Karte: keine Angabe; Kimi-K2: *0.6*                                      |  0.6 (BP, von K2)    |  0.6 (BP)      | 0.6 (BP)          | 0.6 (BP)            |
| Nemotron-Cascade-14B-Thinking (`mradermacher/nemotron-cascade-14b-thinking`)        | *0.6 / 0.95* (Thinking-only)                                             | *0.6/0.95*           | *0.6/0.95*     | *0.6/0.95*        | *0.6/0.95*          |
| Nemotron-3-Nano-REAP-21B (`quietimpostor/nemotron-3-nano-reap-21b-a3b`)             | Basis-30B: Reasoning *1.0 / 1.0*; Tool-Calling *0.6 / 0.95*; | *1.0/1.0* | *1.0/1.0*            | *0.6/0.95*     | *1.0/1.0*         |                     |
|                                                                                     |         ... Thinking-off: greedy                                         |                      |                |                   |                     |
| LFM2-24B-A2B (`noctrex/lfm2-24b-a2b_moe`)                                           | Quickstart *0.1*, top_k 50, rep_pen 1.05; „not recommended for coding"   | –                    | *0.1*          | *0.1*             | 0.1 (BP)            |
| InternLM2.5-20B-Chat (`internlm/internlm2_5-20b-chat`)                              | keine Angabe                                                             |  0.6/0.8 (BP)        |  0.6/0.8 (BP)  |  0.6/0.8 (BP)     | 0.6/0.8 (BP)        |
| InternLM2-Math-Plus-20B (`lmstudio-community/internlm2-math-plus-20b`)              | keine Angabe; offizielles Eval: *greedy + CoT*                           | –                    |  0.7 (BP)      | –                 |*greedy* (0.2–0.6 BP)|

(Essential sagt bei RNJ-1 zu Knowledge Segment: „not optimized for factual recovery")

## Kernaussagen

1. **temp=0.0 (aktueller Coding-/Knowledge-Default) ist nur für Granite 4.x, Phi-4, DeepSeek-Coder, Ministral, LFM2 und Codestral (Beispiel) vertretbar.** 
        Alle anderen Hersteller empfehlen höhere Werte.
2. **Explizite 1.0-Empfehlungen** (auch für Coding): GPT-OSS, Gemma-4, Qwen3.5/3.6 (Thinking), North-Mini-Code, MiroThinker, Nemotron-3 (Reasoning). 
        Bei diesen Modellen senkt temp=0.0 die Vielfalt und kann zu repetitiven/leeren Antworten führen — potenziell erklärend für schlechtere Scores.
3. **Reasoning/Thinking-Modelle:** DeepSeek-R1 (0.6/0.95), Nemotron-Cascade (0.6/0.95), Qwen3-Thinking (0.6/0.95) — temp=0.7 (aktueller Math-Default) passt hier gut.
4. **Agentic/Tool-Use:** reicht von 0 (GLM-4.7 τ²-Bench, Granite) über 0.2 (rnj-1, Devstral) bis 1.0 (Qwen3.6, GPT-OSS). Kimi-K2: 0.6.
5. **Konsequenz für die Pipeline (superseded durch das Design oben):** Die saubere Lösung wäre
        pro Modell `temperature` in den JSON-Configs zu setzen (via LMS-GUI) bzw. die Defaults anzuheben;
        umgesetzt wurde stattdessen das Sampling-Design 2026-08-06 (`MODEL_CATEGORY_SAMPLING` > Defaults,
        JSON-temp GUI-only).

## Quellen

**Mistral:** [Codestral-Karte](https://huggingface.co/mistralai/codestral-22b-v0.1) · [FIM-API-Docs](https://docs.mistral.ai/api/endpoint/fim) · [Codestral-Blog](https://mistral.ai/news/codestral) · [Mamba-Codestral-Karte](https://huggingface.co/mistralai/Mamba-Codestral-7B-v0.1) · [Mamba-Blog](https://mistral.ai/news/codestral-mamba) · [Devstral-Karte](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) · [Magistral-Karte](https://huggingface.co/mistralai/Magistral-Small-2509) · [Ministral-3-Karte](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512)

**Qwen:** [Qwen2.5-Coder](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct) · [Qwen2.5-Familie](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-1M) · [Qwen2.5-Coder-Blog](https://qwenlm.github.io/blog/qwen2.5-coder/) · [Qwen3-Coder](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) · [Qwen3-Coder-Blog](https://qwenlm.github.io/blog/qwen3-coder/) · [Qwen3-Coder-REAP](https://huggingface.co/cerebras/Qwen3-Coder-REAP-25B-A3B) · [Qwen3-30B-A3B-2507](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507) · [Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B) · [Qwen3-Quickstart](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html) · [Qwen3-Paper](https://arxiv.org/abs/2505.09388) · [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) · [Qwen3.5-Blog](https://qwen.ai/blog?id=qwen3.5) · [Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) · [Qwen3.6-Blog](https://qwen.ai/blog?id=qwen3.6-27b) · [Alibaba-Cloud-Blog](https://www.alibabacloud.com/blog/qwen3-6-27b-flagship-level-coding-in-a-27b-dense-model_603063) · [Qwen3.6-MTP-Repack](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF) · [Intel-AutoRound-Repacks](https://huggingface.co/Intel/Qwen3-30B-A3B-Instruct-2507-gguf-q2ks-mixed-AutoRound)

**DeepSeek:** [DeepSeek-Coder-33B](https://huggingface.co/deepseek-ai/deepseek-coder-33b-instruct) · [DeepSeek-Coder-GitHub](https://github.com/deepseek-ai/DeepSeek-Coder) · [DeepSeek-Coder-V2](https://huggingface.co/deepseek-ai/deepseek-coder-v2-lite-instruct) · [DeepSeek-Coder-V2-GitHub](https://github.com/deepseek-ai/DeepSeek-Coder-V2) · [R1-Distill-Qwen-14B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B) · [R1-Paper](https://arxiv.org/abs/2501.12948) · [DeepSeek-API](https://api-docs.deepseek.com/api/create-chat-completion)

**Microsoft/OpenAI:** [Phi-4](https://huggingface.co/microsoft/phi-4) · [Phi-4-Paper](https://arxiv.org/pdf/2412.08905) · [GPT-OSS](https://github.com/openai/gpt-oss) · [GPT-OSS-Karte](https://huggingface.co/openai/gpt-oss-20b) · [GPT-OSS-Sampling-Discussion](https://huggingface.co/openai/gpt-oss-120b/discussions/21)

**IBM:** [Granite-Docs](https://www.ibm.com/granite/docs/models/granite) · [Granite-4.1-Docs](https://www.ibm.com/granite/docs/models/granite4-1) · [Granite-4.0-H-Tiny](https://huggingface.co/ibm-granite/granite-4.0-h-tiny) · [Granite-4.1-8B](https://huggingface.co/ibm-granite/granite-4.1-8b) · [Granite-4.1-30B](https://huggingface.co/ibm-granite/granite-4.1-30b) · [Granite-4.1-GitHub](https://github.com/ibm-granite/granite-4.1-language-models) · [Granite-Kitchen](https://github.com/ibm-granite-community/granite-kitchen) · [Unsloth-Granite-4.0](https://unsloth.ai/docs/models/tutorials/ibm-granite-4.0) · [Unsloth-Granite-4.1](https://unsloth.ai/docs/models/ibm-granite-4.1) · [Granite-Code-Paper](https://arxiv.org/html/2405.04324v1)

**Google:** [Gemma-4-12B-it](https://huggingface.co/google/gemma-4-12B-it) · [Gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it) · [Gemma-4-QAT-GGUF](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) · [Gemma-Model-Card-4](https://ai.google.dev/gemma/docs/core/model_card_4) · [Unsloth-Gemma-4](https://unsloth.ai/docs/models/gemma-4)

**EssentialAI:** [rnj-1](https://huggingface.co/EssentialAI/rnj-1) · [rnj-1-instruct](https://huggingface.co/EssentialAI/rnj-1-instruct)

**Zhipu (z.ai):** [GLM-4.7-Flash](https://huggingface.co/zai-org/glm-4.7-flash) · [GLM-4.7-Docs](https://docs.z.ai/guides/llm/glm-4.7) · [GLM-4.7-REAP](https://huggingface.co/cerebras/GLM-4.7-Flash-REAP-23B-A3B) · [GLM-4.6V-Flash](https://huggingface.co/zai-org/glm-4.6v-flash)

**Baidu:** [ERNIE-4.5-Karte](https://huggingface.co/baidu/ERNIE-4.5-21B-A3B-PT) · [Qianfan-API](https://cloud.baidu.com/doc/qianfan/s/6mh4stoyf) · [ERNIE-4.5-Blog](https://ernie.baidu.com/blog/zh/posts/ernie4.5/) · [Baidu-Tuning-Guide](https://cloud.baidu.com/article/3547357)

**TII:** [Falcon3-10B](https://huggingface.co/tiiuae/falcon3-10b-instruct) · [Falcon3-Mamba-7B](https://huggingface.co/tiiuae/falcon3-mamba-7b-instruct) · [Falcon3-Blog](https://huggingface.co/blog/falcon3)

**JetBrains:** [Mellum2-Instruct](https://huggingface.co/JetBrains/Mellum2-12B-A2.5B-Instruct) · [Mellum2-Thinking](https://huggingface.co/JetBrains/Mellum2-12B-A2.5B-Thinking)

**Moonshot:** [Kimi-K2-Instruct](https://huggingface.co/moonshotai/Kimi-K2-Instruct) · [Kimi-Linear-48B](https://huggingface.co/moonshotai/Kimi-Linear-48B-A3B-Instruct) · [Kimi-Linear-REAP-35B](https://huggingface.co/cerebras/Kimi-Linear-REAP-35B-A3B-Instruct) · [Kimi-Linear-Paper](https://huggingface.co/papers/2510.26692)

**NVIDIA:** [Nemotron-Cascade-14B-Thinking](https://huggingface.co/nvidia/Nemotron-Cascade-14B-Thinking) · [Nemotron-3-Nano-30B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16) · [Nemotron-3-Paper](https://arxiv.org/abs/2512.20848) · [Nemotron-3-Nano-REAP-21B-GGUF](https://huggingface.co/QuietImpostor/Nemotron-3-Nano-REAP-21B-A3B-MXFP4-GGUF)

**Liquid AI:** [LFM2-24B-A2B](https://huggingface.co/LiquidAI/LFM2-24B-A2B) · [Liquid-Docs](https://docs.liquid.ai/lfm) · [noctrex-Repack](https://huggingface.co/noctrex/LFM2-24B-A2B-MXFP4_MOE-GGUF)

**InternLM:** [InternLM2.5-20B-Chat](https://huggingface.co/internlm/internlm2_5-20b-chat) · [InternLM2-Math-Plus-20B](https://huggingface.co/internlm/internlm2-math-plus-20b) · [InternLM-Math-GitHub](https://github.com/InternLM/InternLM-Math) · [InternLM-Math-Paper](https://arxiv.org/abs/2402.06332)

**Diverse:** [MiroThinker-v1.5-30B](https://huggingface.co/miromind-ai/MiroThinker-v1.5-30B) · [MiroThinker-Paper](https://arxiv.org/abs/2511.11793) · [North-Mini-Code-1.0](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) · [JanusCoder](https://huggingface.co/internlm/JanusCoder-14B) · [Nerdsking-Python-Coder-7B](https://huggingface.co/Nerdsking/Nerdsking-python-coder-7B-i) · [REAP-Paper](https://arxiv.org/abs/2510.13999) · [Ternary-Bonsai-27B](https://huggingface.co/prism-ml/Ternary-Bonsai-27B-gguf) · [Bonsai-8B](https://huggingface.co/prism-ml/Ternary-Bonsai-8B-gguf) · [vinpix-Bonsai-Repacks](https://huggingface.co/vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF)
