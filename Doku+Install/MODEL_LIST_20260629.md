# Modell-Liste (LM Studio, Stand 30.06.2026)

**System:** NVIDIA RTX 5070 Ti (16 GB VRAM) | Windows 11

## Installierte Modelle (lms ls --json)

| #  | Modell-Schlüssel (modelKey)          | Architektur   | Quant   | Parameter | Kontext (max) | Tool-Use | Vision |
| -- | ------------------------------------ | ------------- | ------- | --------- | ------------- | -------- | ------ |
| 1  | `acemath-7b-instruct`                | qwen2         | Q8_0    | 7B        | 4K            | –        | –      |
| 2  | `devstral-small-2-24b-instruct-2512` | mistral3      | IQ3_XXS | 24B       | 392K          | ✅       | ✅      |
| 3  | `ernie-4.5-21b-a3b-pt`              | ernie4_5-moe  | IQ4_NL  | 21B-A3B   | 131K          | –        | –      |
| 4  | `essentialai/rnj-1`                  | gemma3        | Q8_0    | 8.3B      | 32K           | ✅       | –      |
| 5  | `falcon3-10b-instruct`               | llama         | Q8_0    | 10B       | 32K           | –        | –      |
| 6  | `gemma-4-19b-a4b-it-reap-i1`         | gemma4        | IQ4_NL  | 19B-a4B   | 262K          | ✅       | –      |
| 7  | `granite-4.0-h-tiny`                 | granitehybrid | Q8_0    | 64x994M   | 1M            | ✅       | –      |
| 8  | `granite-4.1-8b`                     | granite       | Q8_0    | 8B        | 131K          | ✅       | –      |
| 9  | `lmstudio-community/gpt-oss-20b`     | gpt-oss       | MXFP4   | 20B       | 131K          | ✅       | –      |
| 10 | `mellum2-12b-a2.5b-instruct`         | mellum        | Q4_K_M  | 12B-A2.5B | 131K          | ✅       | –      |
| 11 | `mellum2-12b-a2.5b-instruct_moe`     | mellum        | MXFP4   | 12B-A2.5B | 131K          | ✅       | –      |
| 12 | `ministral-3-14b-instruct-2512`      | mistral3      | Q5_K_M  | 14B       | 262K          | ✅       | –      |
| 13 | `mistralai/codestral-22b-v0.1`       | llama         | IQ4_XS  | 22B       | 32K           | –        | –      |
| 14 | `nerdsking-python-coder-7b-i`        | qwen2         | Q8_0_i  | 7.6B      | 32K           | ✅       | –      |
| 15 | `qwen2.5-14b-instruct-1m`            | qwen2         | Q6_K    | 14B       | 1M            | –        | –      |
| 16 | `qwen2.5-coder-14b-instruct`         | qwen2         | Q5_0    | 14B       | 131K          | –        | –      |
| 17 | `qwen3-30b-a3b-python-coder`         | qwen3moe      | Q3_K_S  | 30B-A3B   | 40K           | ✅       | –      |
| 18 | `qwen3-coder-reap-25b-a3b-i1` (IQ4_XS) | qwen3moe    | IQ4_XS  | 25B-A3B   | 262K          | ✅       | –      |
| 19 | `qwen3-coder-reap-25b-a3b-i1` (Q3_K_M) | qwen3moe    | Q3_K_M  | 25B-A3B   | 262K          | ✅       | –      |
| 20 | `qwen3.6-27b`                        | qwen35        | Q3_K_S  | 27B       | 262K          | ✅       | –      |
| 21 | `unsloth/gpt-oss-20b`                | gpt-oss       | Q6_K    | 20B       | 131K          | ✅       | –      |
| 22 | `unsloth/phi-4`                      | llama         | Q5_K_M  | 15B       | 16K           | –        | –      |

**Gesamt: 22 LLM-Modelle** (+ 1 Embedding: `text-embedding-nomic-embed-text-v1.5`)

## Modelle mit Config aber nicht mehr in lms ls (ehemals installiert)

| Modell                                    | Grund                        |
| ----------------------------------------- | ---------------------------- |
| deepseek-coder-33b-instruct               | gelöscht (zu groß)           |
| deepseek-coder-6.7b-instruct              | gelöscht                     |
| deepseek-coder-v2-lite-instruct            | gelöscht                     |
| deepseek-r1-distill-qwen-14b (3x Quant)   | gelöscht                     |
| deepseek-r1-0528-qwen3-8b                 | gelöscht                     |
| devstral-small-2505/2507 (alt)            | durch 2512 ersetzt           |
| gemma-3-12b                               | gelöscht                     |
| gemma-4-12b / gemma-4-12b-qat             | gelöscht                     |
| gemma-4-26b-a4b-qat                       | gelöscht                     |
| gemma-4-31b-i1 (IQ3_M)                    | gelöscht (lädt nicht)        |
| glm-4.6v-flash                            | gelöscht (Vision)            |
| glm-4.7-flash-reap-23b-a3b                | gelöscht                     |
| google_gemma-4-26b-A4B-it (IQ4_XS)        | gelöscht                     |
| granite-20b-code-instruct                  | gelöscht                     |
| januscoder-14b (3x Quant)                 | gelöscht                     |
| lfm2-24b-a2b / lfm2-24b-a2b-reap         | gelöscht                     |
| lfm2.5-8b-a1b                             | gelöscht                     |
| mathstral-7b-v0.1                         | gelöscht                     |
| mellum2-12b-a2.5b-thinking                | gelöscht                     |
| microsoft/phi-4                           | gelöscht (durch unsloth ersetzt) |
| mistral-nemo-instruct-2407                | gelöscht                     |
| mistral-small-3.2-24b (3x Quant)          | gelöscht                     |
| pandalyst_13b_v1.0                        | gelöscht                     |
| phi-4-reasoning-plus                      | gelöscht                     |
| qwen2.5-coder-32b-instruct                | gelöscht (zu groß)           |
| qwen3-14b                                 | gelöscht                     |
| qwen3.5-9b                                | gelöscht                     |
| qwen3.5-9b-deepseek-v4-flash              | gelöscht                     |
| qwen3.6-28b-reap (IQ3_M / Q3_K_S)        | gelöscht                     |
| starcoder2-15b-instruct                    | gelöscht                     |
| wizardcoder-python-13b                    | gelöscht                     |

## Vom Benchmark ausgeschlossen (Vision/OCR/Embedding)

| Modell                                    | Typ              |
| ----------------------------------------- | ---------------- |
| devstral-small-2-24b-instruct-2512        | Vision (multimodal) |
| glm-4.6v-flash                            | Vision-Language  |
| mimo-vl-7b-rl-2508                        | Vision-Language  |
| nanonets-ocr2-3b                          | OCR              |
| garnet-ocr-7b-0422                        | OCR              |
| text-embedding-nomic-embed-text-v1.5      | Embedding        |

## Steckbriefe verfügbar für

Siehe `Modell_Steckbriefe_20260629.md` – 41 Modelle dokumentiert (22 aktuell installiert + 19 ehemals/getestet/gelöscht).
