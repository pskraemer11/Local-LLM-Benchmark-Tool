PS C:\Users\pskra\Python-Projekte\Benchmarks> python run_benchmarks_v10.py --sample-size 5 --model "1,2,3,6,7,8,9,15" --benchmarks all
============================================================
  Unified Benchmark Launcher v10
  SampleSize: 5
  Pipelines: Custom (DS1000/CoderEval), EvalPlus, LM-Eval (ARC/HS/TQA/MQA/MMLU-Pro-mod), Agentic (tool-eval-bench)
  CSV-Format: csv_writer (; Delimiter, utf-8)
============================================================
  Modelle: Qwen3.6 28B REAP I1, Qwen3 Coder REAP 25B A3B I1, Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m), Qwen2.5 14B Instruct 1M, Qwen3 30B A3B Python Coder, AceMath 7B Instruct, Qwen3.6 27B, Qwen2.5 Coder 14B Instruct
  Benchmarks: DS1000, CoderEval, HumanEval+, MBPP+, ARC-Challenge, HellaSwag, TruthfulQA, MMLU-Pro, MathQA, Agentic

============================================================
  Modell 1/8: Qwen3.6 28B REAP I1
  * Reasoning-Modell (erkannt) – Timeout ×2
============================================================

  [INFO] Lade 'qwen3.6-28b-reap-i1'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen3.6-28b-reap-i1
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen3.6 28B REAP I1
 Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  [RETRY] API-Fehler (Versuch 2/3): Fallback ebenfalls fehlgeschlagen

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  Score: 0% (Timeout/API-Fehler (120.0s)) | Latenz: 120.0s | 0.0 tok/s | ≈0% Thinking | CPU: 63% | RAM: 12.7 GB | GPU: 100% | VRAM: 15.8 GB

  [3/5] Problem: I'm looking to map the value in a dict to one column in a Dat...

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  [RETRY] API-Fehler (Versuch 1/3): Fallback ebenfalls fehlgeschlagen

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  [RETRY] API-Fehler (Versuch 2/3): Fallback ebenfalls fehlgeschlagen

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  Score: 0% (Timeout/API-Fehler (120.0s)) | Latenz: 120.0s | 0.0 tok/s | ≈0% Thinking | CPU: 61% | RAM: 12.4 GB | GPU: 100% | VRAM: 15.8 GB

  [4/5] Problem: I simulate times in the range 0 to T according to a Poisson p...
  Score: 0% (Kein Code generiert) | Latenz: 25.4s | 0.0 tok/s | ≈0% Thinking | CPU: 51% | RAM: 12.4 GB | GPU: 100% | VRAM: 15.8 GB

  [5/5] Problem:  Is there any way for me to preserve punctuation marks of !, ...
  Score: 0% (Kein Code generiert) | Latenz: 11.2s | 0.0 tok/s | ≈0% Thinking | CPU: 61% | RAM: 9.7 GB | GPU: 70% | VRAM: 14.1 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_110302_DS1000_Qwen3.6 28B REAP I1.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_110302_Qwen3.6 28B REAP I1.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (2492s)

  >>> Custom: CoderEval / Qwen3.6 28B REAP I1
==============================
  LM Studio Benchmark-Tool v10
  DS1000 + CoderEval
  Subsampling: 5 Aufgaben pro Benchmark
============================================================
  Python: 3.14.6 (C:\Users\pskra\AppData\Local\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen3.6 28B REAP I1
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen3.6 28B REAP I1
  Aufgaben:  5
============================================================

  [1/5] Check whether the obj class has the fill and compute methods....
  Score: 0% (Kein Code generiert) | Latenz: 5.6s | 0.0 tok/s | ≈0% Thinking | CPU: 50% | RAM: 9.7 GB | GPU: 70% | VRAM: 14.1 GB

  [2/5] Round a floating-point number....
  Score: 0% (Kein Code generiert) | Latenz: 23.7s | 0.0 tok/s | ≈0% Thinking | CPU: 53% | RAM: 9.7 GB | GPU: 81% | VRAM: 14.1 GB

  [3/5] For the given node, returns the first match in the pubdate_xpaths list...
  Score: 0% (Kein Code generiert) | Latenz: 25.6s | 0.0 tok/s | ≈0% Thinking | CPU: 57% | RAM: 9.7 GB | GPU: 71% | VRAM: 14.1 GB

  [4/5] Return every response with the length of max_results     Args:     res...
  Score: 0% (Kein Code generiert) | Latenz: 6.9s | 0.0 tok/s | ≈0% Thinking | CPU: 56% | RAM: 9.7 GB | GPU: 70% | VRAM: 14.1 GB

  [5/5] Check whether the obj class has the run method....
  Score: 0% (Kein Code generiert) | Latenz: 10.6s | 0.0 tok/s | ≈0% Thinking | CPU: 53% | RAM: 9.7 GB | GPU: 72% | VRAM: 14.1 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_110424_CoderEval_Qwen3.6 28B REAP I1.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_110424_Qwen3.6 28B REAP I1.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (81s)

  >>> EvalPlus: HumanEval+ / Qwen3.6 28B REAP I1
  [codegen] humaneval [0,5] ...
)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3.6-28b-reap-i1\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 0.150
humaneval+ (base + extra tests)
pass@1: 0.150

  [OK] HumanEval+ done (47s)

  >>> EvalPlus: MBPP+ / Qwen3.6 28B REAP I1
  [codegen] mbpp [0,5] ...
is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3.6-28b-reap-i1\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 0.214
mbpp+ (base + extra tests)
pass@1: 0.214

  [OK] MBPP+ done (28s)

  >>> LM-Eval: ARC-Challenge / Qwen3.6 28B REAP I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-28b-reap-i1', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (150s)

  >>> LM-Eval: HellaSwag / Qwen3.6 28B REAP I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-28b-reap-i1', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |    0|±  |     0|


  [OK] HellaSwag done (76s)

  >>> LM-Eval: TruthfulQA / Qwen3.6 28B REAP I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-28b-reap-i1', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   |Value|   |Stderr|
|--------------|------:|------|-----:|-----------|---|----:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  |    0|±  |     0|
|              |       |none  |     0|bleu_diff  |↑  |    0|±  |     0|
|              |       |none  |     0|bleu_max   |↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_max |↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_max |↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_max |↑  |    0|±  |     0|


  [OK] TruthfulQA done (91s)

  >>> MMLU-Pro (modifiziert): Qwen3.6 28B REAP I1
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_economics: 100.0% (91s)
    [OK] mmlu_pro_computer_science: 0.0% (70s)
    [OK] mmlu_pro_other: 100.0% (80s)
    [OK] mmlu_pro_health: 100.0% (93s)
    [OK] mmlu_pro_chemistry: 100.0% (93s)
  [OK] MMLU-Pro (mod.) done (426s) – Subsets: 5/5, avg: 80.0%

  >>> LM-Eval: MathQA / Qwen3.6 28B REAP I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-28b-reap-i1', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |    0|±  |     0|


  [OK] MathQA done (33s)

  >>> Agentic (tool-eval-bench): Qwen3.6 28B REAP I1
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (238s)

[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen3.6-28b-reap-i1.csv (15 Eintraege)

============================================================
  Modell 2/8: Qwen3 Coder REAP 25B A3B I1
  * MoE-Modell (erkannt)
============================================================
  [INFO] Anderes Modell geladen (Qwen3.6 28B REAP I1) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'qwen3-coder-reap-25b-a3b-i1@iq4_xs'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen3-coder-reap-25b-a3b-i1@iq4_xs
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen3 Coder REAP 25B A3B I1
/5] import matplotlib.pyplot as plt import pandas as pd import numpy as np...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: '(' was never closed (<string>, line 15)
  Score: 0% (Harness-Fehler: failed: '(' was never closed (<string>, line 15)) | Latenz: 18.3s | 4.1 tok/s | ≈0% Thinking | CPU: 52% | RAM: 13.2 GB | GPU: 100% | VRAM: 15.8 GB

  [2/5] Problem: I could not find a built-in function in Python to generate a ...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: BESTANDEN
  Score: 100% (OK (DS1000-Harness)) | Latenz: 10.0s | 2.3 tok/s | ≈0% Thinking | CPU: 50% | RAM: 13.2 GB | GPU: 61% | VRAM: 15.8 GB

  [3/5] Problem: Let's say I have 5 columns. pd.DataFrame({ 'Column1': [1, 2, ...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: 0
  Score: 0% (Harness-Fehler: failed: 0) | Latenz: 71.8s | 2.7 tok/s | ≈0% Thinking | CPU: 78% | RAM: 13.9 GB | GPU: 85% | VRAM: 15.9 GB

  [4/5] Problem: I have an array of experimental values and a probability dens...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: 'result'
  Score: 0% (Harness-Fehler: failed: 'result') | Latenz: 47.3s | 3.5 tok/s | ≈0% Thinking | CPU: 58% | RAM: 13.9 GB | GPU: 41% | VRAM: 15.8 GB

  [5/5] Problem:  I have a csv file which looks like  date                    ...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: name 'load_data' is not defined
  Score: 0% (Harness-Fehler: failed: name 'load_data' is not defined) | Latenz: 20.7s | 1.8 tok/s | ≈0% Thinking | CPU: 59% | RAM: 14.0 GB | GPU: 77% | VRAM: 15.8 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_112630_DS1000_Qwen3 Coder REAP 25B A3B I1.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_112630_Qwen3 Coder REAP 25B A3B I1.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (218s)

  >>> Custom: CoderEval / Qwen3 Coder REAP 25B A3B I1
Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen3 Coder REAP 25B A3B I1
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen3 Coder REAP 25B A3B I1
  Aufgaben:  5
============================================================

  [1/5] Return every response with the length of max_results     Args:     res...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 10.4s | 4.8 tok/s | ≈0% Thinking | CPU: 48% | RAM: 13.8 GB | GPU: 99% | VRAM: 15.8 GB

  [2/5] Convert a script to one line command with the given seperator.        ...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 3.4s | 1.8 tok/s | ≈0% Thinking | CPU: 46% | RAM: 13.8 GB | GPU: 51% | VRAM: 15.8 GB

  [3/5] For the given node, returns the first match in the pubdate_xpaths list...
    [EVAL] Direkte Tests: 0/2 bestanden
  Score: 0% (Tests: 0/2) | Latenz: 10.0s | 5.8 tok/s | ≈0% Thinking | CPU: 54% | RAM: 13.8 GB | GPU: 47% | VRAM: 15.8 GB

  [4/5] Round a floating-point number....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 13.5s | 6.9 tok/s | ≈0% Thinking | CPU: 50% | RAM: 13.8 GB | GPU: 41% | VRAM: 15.8 GB

  [5/5] Creates a configuration with some simple parameters, the key parameter...
    [EVAL] Direkte Tests: 0/2 bestanden
  Score: 0% (Tests: 0/2) | Latenz: 15.5s | 3.4 tok/s | ≈0% Thinking | CPU: 52% | RAM: 13.7 GB | GPU: 50% | VRAM: 15.8 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_112734_CoderEval_Qwen3 Coder REAP 25B A3B I1.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_112734_Qwen3 Coder REAP 25B A3B I1.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (63s)

  >>> EvalPlus: HumanEval+ / Qwen3 Coder REAP 25B A3B I1
  [codegen] humaneval [0,5] ...
nEval/162 as it is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3-coder-reap-25b-a3b-i1@iq4_xs\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 0.950
humaneval+ (base + extra tests)
pass@1: 0.950

  [OK] HumanEval+ done (47s)

  >>> EvalPlus: MBPP+ / Qwen3 Coder REAP 25B A3B I1
  [codegen] mbpp [0,5] ...
)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3-coder-reap-25b-a3b-i1@iq4_xs\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 0.857
mbpp+ (base + extra tests)
pass@1: 0.714

  [OK] MBPP+ done (29s)

  >>> LM-Eval: ARC-Challenge / Qwen3 Coder REAP 25B A3B I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@iq4_xs', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (116s)

  >>> LM-Eval: HellaSwag / Qwen3 Coder REAP 25B A3B I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@iq4_xs', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |  0.8|±  |   0.2|


  [OK] HellaSwag done (71s)

  >>> LM-Eval: TruthfulQA / Qwen3 Coder REAP 25B A3B I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@iq4_xs', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   | Value |   |Stderr|
|--------------|------:|------|-----:|-----------|---|------:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|bleu_diff  |↑  | 0.6257|±  |1.0628|
|              |       |none  |     0|bleu_max   |↑  | 9.9008|±  |4.6849|
|              |       |none  |     0|rouge1_acc |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|rouge1_diff|↑  | 1.9976|±  |2.3907|
|              |       |none  |     0|rouge1_max |↑  |27.9395|±  |5.6620|
|              |       |none  |     0|rouge2_acc |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|rouge2_diff|↑  |-0.9013|±  |2.8413|
|              |       |none  |     0|rouge2_max |↑  |17.7693|±  |5.1007|
|              |       |none  |     0|rougeL_acc |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|rougeL_diff|↑  | 2.0319|±  |2.3905|
|              |       |none  |     0|rougeL_max |↑  |25.4785|±  |6.2653|


  [OK] TruthfulQA done (84s)

  >>> MMLU-Pro (modifiziert): Qwen3 Coder REAP 25B A3B I1
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_chemistry: 0.0% (201s)
    [OK] mmlu_pro_other: 100.0% (111s)
    [OK] mmlu_pro_economics: 100.0% (151s)
    [OK] mmlu_pro_biology: 0.0% (187s)
    [OK] mmlu_pro_law: 0.0% (162s)
  [OK] MMLU-Pro (mod.) done (813s) – Subsets: 5/5, avg: 40.0%

  >>> LM-Eval: MathQA / Qwen3 Coder REAP 25B A3B I1
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@iq4_xs', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |  0.6|±  |0.2449|


  [OK] MathQA done (44s)

  >>> Agentic (tool-eval-bench): Qwen3 Coder REAP 25B A3B I1
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (208s)

[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen3-coder-reap-25b-a3b-i1@iq.csv (10 Eintraege)

============================================================
  Modell 3/8: Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
  * MoE-Modell (erkannt)
============================================================
  [INFO] Anderes Modell geladen (Qwen3 Coder REAP 25B A3B I1) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'qwen3-coder-reap-25b-a3b-i1@q3_k_m'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen3-coder-reap-25b-a3b-i1@q3_k_m
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
35.6s | 2.1 tok/s | ≈0% Thinking | CPU: 78% | RAM: 12.2 GB | GPU: 100% | VRAM: 15.8 GB

  [2/5] Problem: What I am trying to achieve is a 'highest to lowest' ranking ...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: 'result'
  Score: 0% (Harness-Fehler: failed: 'result') | Latenz: 12.7s | 3.1 tok/s | ≈0% Thinking | CPU: 48% | RAM: 12.3 GB | GPU: 54% | VRAM: 15.8 GB

  [3/5] Problem: Example import pandas as pd import numpy as np d = {'l':  ['l...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: unterminated string literal (detected at line 10) (<string>, line 10)
  Score: 0% (Harness-Fehler: failed: unterminated string literal (detected at line 10) (<string>, line 10)) | Latenz: 21.5s | 1.9 tok/s | ≈0% Thinking | CPU: 46% | RAM: 12.3 GB | GPU: 54% | VRAM: 15.8 GB

  [4/5] Problem: I have been trying to get the arithmetic result of a lognorma...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: name 'expected_value' is not defined
  Score: 0% (Harness-Fehler: failed: name 'expected_value' is not defined) | Latenz: 17.5s | 2.5 tok/s | ≈0% Thinking | CPU: 54% | RAM: 12.3 GB | GPU: 60% | VRAM: 15.8 GB

  [5/5] Problem:  I would like to apply minmax scaler to column A2 and A3 in d...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: incompatible index of inserted column with frame index
  Score: 0% (Harness-Fehler: failed: incompatible index of inserted column with frame index) | Latenz: 57.0s | 1.9 tok/s | ≈0% Thinking | CPU: 50% | RAM: 12.3 GB | GPU: 83% | VRAM: 15.8 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_115410_DS1000_Qwen3 Coder REAP 25B A3B I1 (qwen3-coder.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_115410_Qwen3 Coder REAP 25B A3B I1 (qwen3-coder.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (161s)

  >>> Custom: CoderEval / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
===================================================
  Modell 1/1: Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
  Aufgaben:  5
============================================================

  [1/5] Get 3 points for each vertex of the polygon.     This will include the...
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 12.7s | 4.7 tok/s | ≈0% Thinking | CPU: 48% | RAM: 12.1 GB | GPU: 56% | VRAM: 15.8 GB

  [2/5] Return every response with the length of max_results     Args:     res...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 4.7s | 3.0 tok/s | ≈0% Thinking | CPU: 46% | RAM: 12.1 GB | GPU: 55% | VRAM: 15.8 GB

  [3/5] Round a floating-point number....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 32.6s | 6.6 tok/s | ≈0% Thinking | CPU: 50% | RAM: 12.1 GB | GPU: 57% | VRAM: 15.8 GB

  [4/5] Check whether the obj class has the fill and request attributes....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 2.8s | 3.2 tok/s | ≈0% Thinking | CPU: 52% | RAM: 12.1 GB | GPU: 56% | VRAM: 15.8 GB

  [5/5] Combine multiple lists in the sequence of occurrence into a list with ...
    [EVAL] Direkte Tests: 0/1 bestanden
  Score: 0% (Tests: 0/1) | Latenz: 10.9s | 6.3 tok/s | ≈0% Thinking | CPU: 99% | RAM: 12.4 GB | GPU: 57% | VRAM: 15.8 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_115523_CoderEval_Qwen3 Coder REAP 25B A3B I1 (qwen3-coder.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_115523_Qwen3 Coder REAP 25B A3B I1 (qwen3-coder.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (73s)

  >>> EvalPlus: HumanEval+ / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
  [codegen] humaneval [0,5] ...
nEval/162 as it is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3-coder-reap-25b-a3b-i1@q3_k_m\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 0.950
humaneval+ (base + extra tests)
pass@1: 0.950

  [OK] HumanEval+ done (46s)

  >>> EvalPlus: MBPP+ / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
  [codegen] mbpp [0,5] ...
)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3-coder-reap-25b-a3b-i1@q3_k_m\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 1.000
mbpp+ (base + extra tests)
pass@1: 0.714

  [OK] MBPP+ done (28s)

  >>> LM-Eval: ARC-Challenge / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@q3_k_m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (74s)

  >>> LM-Eval: HellaSwag / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@q3_k_m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |  0.8|±  |   0.2|


  [OK] HellaSwag done (66s)

  >>> LM-Eval: TruthfulQA / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@q3_k_m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   | Value |   |Stderr|
|--------------|------:|------|-----:|-----------|---|------:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|bleu_diff  |↑  | 0.8596|±  |0.8407|
|              |       |none  |     0|bleu_max   |↑  |10.7673|±  |4.4780|
|              |       |none  |     0|rouge1_acc |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|rouge1_diff|↑  | 3.1326|±  |3.1586|
|              |       |none  |     0|rouge1_max |↑  |31.6766|±  |4.5762|
|              |       |none  |     0|rouge2_acc |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|rouge2_diff|↑  | 1.6518|±  |3.4260|
|              |       |none  |     0|rouge2_max |↑  |21.2136|±  |4.1188|
|              |       |none  |     0|rougeL_acc |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|rougeL_diff|↑  | 2.1003|±  |1.7281|
|              |       |none  |     0|rougeL_max |↑  |28.1973|±  |5.6362|


  [OK] TruthfulQA done (78s)

  >>> MMLU-Pro (modifiziert): Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_philosophy: 100.0% (113s)
    [OK] mmlu_pro_other: 100.0% (98s)
    [OK] mmlu_pro_computer_science: 0.0% (196s)
    [OK] mmlu_pro_business: 100.0% (107s)
    [OK] mmlu_pro_economics: 100.0% (134s)
  [OK] MMLU-Pro (mod.) done (649s) – Subsets: 5/5, avg: 80.0%

  >>> LM-Eval: MathQA / Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-coder-reap-25b-a3b-i1@q3_k_m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |  0.2|±  |   0.2|


  [OK] MathQA done (42s)

  >>> Agentic (tool-eval-bench): Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m)
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (259s)

[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen3-coder-reap-25b-a3b-i1@q3.csv (10 Eintraege)

============================================================
  Modell 4/8: Qwen2.5 14B Instruct 1M
============================================================
  [INFO] Anderes Modell geladen (Qwen3 Coder REAP 25B A3B I1) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'qwen2.5-14b-instruct-1m'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen2.5-14b-instruct-1m
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen2.5 14B Instruct 1M
tead.) | Latenz: 33.6s | 2.6 tok/s | ≈0% Thinking | CPU: 65% | RAM: 14.9 GB | GPU: 48% | VRAM: 15.7 GB

  [4/5] Problem: I have a table of measured values for a quantity that depends...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: `interp2d` has been removed in SciPy 1.14.0.

For legacy code, nearly bug-for-bug compatible replacements are
`RectBivariateSpline` on regular grids, and `bisplrep`/`bisplev` for
scattered 2D data.

In new code, for regular grids use `RegularGridInterpolator` instead.
For scattered data, prefer `LinearNDInterpolator` or
`CloughTocher2DInterpolator`.

For more details see
https://scipy.github.io/devdocs/tutorial/interpolate/interp_transition_guide.html

  Score: 0% (Harness-Fehler: failed: `interp2d` has been removed in SciPy 1.14.0.

For legacy code, nearly bug-for-bug compatible replacements are
`RectBivariateSpline` on regular grids, and `bisplrep`/`bisplev` for
scattered 2D data.

In new code, for regular grids use `RegularGridInterpolator` instead.
For scattered data, prefer `LinearNDInterpolator` or
`CloughTocher2DInterpolator`.

For more details see
https://scipy.github.io/devdocs/tutorial/interpolate/interp_transition_guide.html
) | Latenz: 39.1s | 2.1 tok/s | ≈0% Thinking | CPU: 50% | RAM: 14.9 GB | GPU: 48% | VRAM: 15.7 GB

  [5/5] Problem:  Given a list of variant length features:  features = [     [...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: name 'load_data' is not defined
  Score: 0% (Harness-Fehler: failed: name 'load_data' is not defined) | Latenz: 22.9s | 2.6 tok/s | ≈0% Thinking | CPU: 47% | RAM: 15.0 GB | GPU: 48% | VRAM: 15.7 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_121923_DS1000_Qwen2.5 14B Instruct 1M.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_121923_Qwen2.5 14B Instruct 1M.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (172s)

  >>> Custom: CoderEval / Qwen2.5 14B Instruct 1M
cal\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen2.5 14B Instruct 1M
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen2.5 14B Instruct 1M
  Aufgaben:  5
============================================================

  [1/5] Get 3 points for each vertex of the polygon.     This will include the...
    [EVAL] Direkte Tests: 0/1 bestanden
  Score: 0% (Tests: 0/1) | Latenz: 10.8s | 3.1 tok/s | ≈0% Thinking | CPU: 48% | RAM: 14.9 GB | GPU: 50% | VRAM: 15.7 GB

  [2/5] Convert a string to a regex pattern object      Args:             patt...
    [EVAL] Direkte Tests: 0/2 bestanden
  Score: 0% (Tests: 0/2) | Latenz: 8.4s | 2.9 tok/s | ≈0% Thinking | CPU: 44% | RAM: 14.9 GB | GPU: 50% | VRAM: 15.7 GB

  [3/5] Convert a script to one line command with the given seperator.        ...
    [EVAL] Direkte Tests: 0/2 bestanden
  Score: 0% (Tests: 0/2) | Latenz: 4.1s | 2.4 tok/s | ≈0% Thinking | CPU: 44% | RAM: 14.8 GB | GPU: 59% | VRAM: 15.7 GB

  [4/5] Check whether the obj class has the run method....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 3.3s | 2.7 tok/s | ≈0% Thinking | CPU: 46% | RAM: 14.8 GB | GPU: 50% | VRAM: 15.7 GB

  [5/5] Return every response with the length of max_results     Args:     res...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 5.6s | 2.5 tok/s | ≈0% Thinking | CPU: 54% | RAM: 14.8 GB | GPU: 49% | VRAM: 15.7 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_122004_CoderEval_Qwen2.5 14B Instruct 1M.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_122004_Qwen2.5 14B Instruct 1M.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (42s)

  >>> EvalPlus: HumanEval+ / Qwen2.5 14B Instruct 1M
  [codegen] humaneval [0,5] ...
ipping HumanEval/162 as it is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen2.5-14b-instruct-1m\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 1.000
humaneval+ (base + extra tests)
pass@1: 0.900

  [OK] HumanEval+ done (26s)

  >>> EvalPlus: MBPP+ / Qwen2.5 14B Instruct 1M
  [codegen] mbpp [0,5] ...
ot in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen2.5-14b-instruct-1m\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 1.000
mbpp+ (base + extra tests)
pass@1: 0.714

  [OK] MBPP+ done (29s)

  [OK] ARC-Challenge done (124s)

  >>> LM-Eval: HellaSwag / Qwen2.5 14B Instruct 1M
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-14b-instruct-1m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |    1|±  |     0|


  [OK] HellaSwag done (70s)

  >>> LM-Eval: TruthfulQA / Qwen2.5 14B Instruct 1M
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-14b-instruct-1m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   | Value |   |Stderr|
|--------------|------:|------|-----:|-----------|---|------:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  | 0.8000|±  |0.2000|
|              |       |none  |     0|bleu_diff  |↑  | 1.6006|±  |1.0253|
|              |       |none  |     0|bleu_max   |↑  |10.3772|±  |2.2772|
|              |       |none  |     0|rouge1_acc |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|rouge1_diff|↑  | 9.3479|±  |4.3687|
|              |       |none  |     0|rouge1_max |↑  |36.1521|±  |3.6927|
|              |       |none  |     0|rouge2_acc |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|rouge2_diff|↑  | 4.5380|±  |3.7501|
|              |       |none  |     0|rouge2_max |↑  |23.0782|±  |4.0626|
|              |       |none  |     0|rougeL_acc |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|rougeL_diff|↑  | 6.0442|±  |2.7619|
|              |       |none  |     0|rougeL_max |↑  |31.8316|±  |4.1408|


 [OK] TruthfulQA done (89s)

  >>> MMLU-Pro (modifiziert): Qwen2.5 14B Instruct 1M
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_computer_science: 0.0% (186s)
    [OK] mmlu_pro_history: 100.0% (248s)
    [OK] mmlu_pro_law: 0.0% (170s)
    [OK] mmlu_pro_philosophy: 0.0% (121s)
    [OK] mmlu_pro_business: 100.0% (113s)
  [OK] MMLU-Pro (mod.) done (838s) – Subsets: 5/5, avg: 40.0%

  >>> LM-Eval: MathQA / Qwen2.5 14B Instruct 1M
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-14b-instruct-1m', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |  0.6|±  |0.2449|


  [OK] MathQA done (44s)

  >>> Agentic (tool-eval-bench): Qwen2.5 14B Instruct 1M
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (105s)
  [OK] Bereits vollstaendig in: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen2.5-14b-instruct-1m.csv

============================================================
  Modell 5/8: Qwen3 30B A3B Python Coder
  * MoE-Modell (erkannt)
============================================================
  [INFO] Anderes Modell geladen (Qwen2.5 14B Instruct 1M) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'qwen3-30b-a3b-python-coder'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen3-30b-a3b-python-coder
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen3 30B A3B Python Coder
ampling: 5 Aufgaben pro Benchmark
============================================================
  Python: 3.14.6 (C:\Users\pskra\AppData\Local\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen3 30B A3B Python Coder
============================================================

  Lade data_science.jsonl (5 Aufgaben)

============================================================
  Benchmark: DS1000
  Modell:    Qwen3 30B A3B Python Coder
  Aufgaben:  5
============================================================

  [1/5] import numpy as np import pandas as pd import matplotlib.pyplot as plt...
  Score: 0% (Kein Code generiert) | Latenz: 9.8s | 2.0 tok/s | ≈0% Thinking | CPU: 47% | RAM: 11.3 GB | GPU: 100% | VRAM: 15.8 GB

  [2/5] Problem: Similar to this answer, I have a pair of 3D numpy arrays, a a...
  Score: 0% (Kein Code generiert) | Latenz: 6.2s | 3.4 tok/s | ≈0% Thinking | CPU: 46% | RAM: 11.3 GB | GPU: 100% | VRAM: 15.8 GB

  [3/5] Problem: I have a Pandas DataFrame that looks something like: df = pd....
  Score: 0% (Kein Code generiert) | Latenz: 7.0s | 1.1 tok/s | ≈0% Thinking | CPU: 47% | RAM: 11.3 GB | GPU: 100% | VRAM: 15.8 GB

  [4/5] Problem: Is there a simple and efficient way to make a sparse scipy ma...
  Score: 0% (Kein Code generiert) | Latenz: 2.0s | 5.5 tok/s | ≈0% Thinking | CPU: 46% | RAM: 11.3 GB | GPU: 100% | VRAM: 15.8 GB

  [5/5] Problem:  I have encountered a problem that, I want to get the interme...
  Score: 0% (Kein Code generiert) | Latenz: 2.0s | 7.4 tok/s | ≈0% Thinking | CPU: 49% | RAM: 11.3 GB | GPU: 99% | VRAM: 15.8 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_124308_DS1000_Qwen3 30B A3B Python Coder.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_124308_Qwen3 30B A3B Python Coder.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (36s)

  >>> Custom: CoderEval / Qwen3 30B A3B Python Coder
.14.6 (C:\Users\pskra\AppData\Local\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen3 30B A3B Python Coder
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen3 30B A3B Python Coder
  Aufgaben:  5
============================================================

  [1/5] Check whether the obj class has the run method....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 1.7s | 11.4 tok/s | ≈0% Thinking | CPU: 46% | RAM: 11.3 GB | GPU: 70% | VRAM: 15.8 GB

  [2/5] Creates a configuration with some simple parameters, the key parameter...
    [EVAL] Direkte Tests: 0/2 bestanden
  Score: 0% (Tests: 0/2) | Latenz: 1.6s | 12.4 tok/s | ≈0% Thinking | CPU: 44% | RAM: 11.3 GB | GPU: 64% | VRAM: 15.8 GB

  [3/5] Round a floating-point number....
    [EVAL] Direkte Tests: 0/1 bestanden
  Score: 0% (Tests: 0/1) | Latenz: 1.5s | 17.2 tok/s | ≈0% Thinking | CPU: 51% | RAM: 11.3 GB | GPU: 66% | VRAM: 15.8 GB

  [4/5] Check whether the obj class has the fill and compute methods....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 1.2s | 11.2 tok/s | ≈0% Thinking | CPU: 46% | RAM: 11.3 GB | GPU: 75% | VRAM: 15.8 GB

  [5/5] Check if the type of the given filename is 'doxyfile'      Args:      ...
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 0.7s | 8.5 tok/s | ≈0% Thinking | CPU: 45% | RAM: 11.3 GB | GPU: 76% | VRAM: 15.8 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_124323_CoderEval_Qwen3 30B A3B Python Coder.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_124323_Qwen3 30B A3B Python Coder.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (14s)

  >>> EvalPlus: HumanEval+ / Qwen3 30B A3B Python Coder
  [codegen] humaneval [0,5] ...
ing HumanEval/162 as it is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3-30b-a3b-python-coder\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 0.800
humaneval+ (base + extra tests)
pass@1: 0.800

  [OK] HumanEval+ done (26s)

  >>> EvalPlus: MBPP+ / Qwen3 30B A3B Python Coder
  [codegen] mbpp [0,5] ...
in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3-30b-a3b-python-coder\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 0.857
mbpp+ (base + extra tests)
pass@1: 0.571

  [OK] MBPP+ done (29s)

  >>> LM-Eval: ARC-Challenge / Qwen3 30B A3B Python Coder
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-30b-a3b-python-coder', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (63s)

  >>> LM-Eval: HellaSwag / Qwen3 30B A3B Python Coder
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-30b-a3b-python-coder', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |    0|±  |     0|


  [OK] HellaSwag done (74s)

  >>> LM-Eval: TruthfulQA / Qwen3 30B A3B Python Coder
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-30b-a3b-python-coder', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   |Value|   |Stderr|
|--------------|------:|------|-----:|-----------|---|----:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  |    0|±  |     0|
|              |       |none  |     0|bleu_diff  |↑  |    0|±  |     0|
|              |       |none  |     0|bleu_max   |↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_max |↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_max |↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_max |↑  |    0|±  |     0|


  [OK] TruthfulQA done (77s)

  >>> MMLU-Pro (modifiziert): Qwen3 30B A3B Python Coder
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_philosophy: 100.0% (50s)
    [OK] mmlu_pro_computer_science: 100.0% (64s)
    [OK] mmlu_pro_history: 0.0% (72s)
    [OK] mmlu_pro_health: 100.0% (62s)
    [OK] mmlu_pro_physics: 0.0% (62s)
  [OK] MMLU-Pro (mod.) done (311s) – Subsets: 5/5, avg: 60.0%

  >>> LM-Eval: MathQA / Qwen3 30B A3B Python Coder
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3-30b-a3b-python-coder', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |    0|±  |     0|


  [OK] MathQA done (27s)

  >>> Agentic (tool-eval-bench): Qwen3 30B A3B Python Coder
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (70s)
  [OK] Bereits vollstaendig in: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen3-30b-a3b-python-coder.csv

============================================================
  Modell 6/8: AceMath 7B Instruct
============================================================
  [INFO] Anderes Modell geladen (Qwen3 30B A3B Python Coder) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'acemath-7b-instruct'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: acemath-7b-instruct
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / AceMath 7B Instruct
..
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed:
  Score: 0% (Harness-Fehler: failed: ) | Latenz: 1.2s | 13.8 tok/s | ≈0% Thinking | CPU: 15% | RAM: 9.9 GB | GPU: 93% | VRAM: 8.3 GB

  [2/5] Problem: I have the following text output, my goal is to only select v...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: 'result'
  Score: 0% (Harness-Fehler: failed: 'result') | Latenz: 2.4s | 20.3 tok/s | ≈0% Thinking | CPU: 20% | RAM: 9.8 GB | GPU: 97% | VRAM: 8.3 GB

  [3/5] Problem: I have the following dataframe: index = range(14) data = [1, ...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: NDFrame.replace() got an unexpected keyword argument 'method'
  Score: 0% (Harness-Fehler: failed: NDFrame.replace() got an unexpected keyword argument 'method') | Latenz: 5.8s | 20.9 tok/s | ≈0% Thinking | CPU: 23% | RAM: 9.8 GB | GPU: 95% | VRAM: 8.3 GB

  [4/5] Problem: I have a sparse 988x1 vector (stored in col, a column in a cs...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: name 'boxed' is not defined
  Score: 0% (Harness-Fehler: failed: name 'boxed' is not defined) | Latenz: 2.3s | 18.6 tok/s | ≈0% Thinking | CPU: 22% | RAM: 9.8 GB | GPU: 95% | VRAM: 8.3 GB

  [5/5] Problem:  I'm trying to find the best hyper-parameters using sklearn f...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: No module named 'xgboost'
  Score: 0% (Harness-Fehler: failed: No module named 'xgboost') | Latenz: 4.8s | 20.7 tok/s | ≈0% Thinking | CPU: 21% | RAM: 9.7 GB | GPU: 95% | VRAM: 8.3 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_125530_DS1000_AceMath 7B Instruct.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_125530_AceMath 7B Instruct.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (31s)

  >>> Custom: CoderEval / AceMath 7B Instruct
3.14.6 (C:\Users\pskra\AppData\Local\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: AceMath 7B Instruct
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    AceMath 7B Instruct
  Aufgaben:  5
============================================================

  [1/5] Return every response with the length of max_results     Args:     res...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 0.9s | 15.4 tok/s | ≈0% Thinking | CPU: 30% | RAM: 9.7 GB | GPU: 96% | VRAM: 8.3 GB

  [2/5] Convert a string to a regex pattern object      Args:             patt...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 1.2s | 20.7 tok/s | ≈0% Thinking | CPU: 16% | RAM: 9.7 GB | GPU: 94% | VRAM: 8.3 GB

  [3/5] Round a floating-point number....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 0.4s | 12.4 tok/s | ≈0% Thinking | CPU: 13% | RAM: 9.7 GB | GPU: 87% | VRAM: 8.3 GB

  [4/5] For the given node, returns the first match in the pubdate_xpaths list...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 1.0s | 19.9 tok/s | ≈0% Thinking | CPU: 15% | RAM: 9.7 GB | GPU: 94% | VRAM: 8.3 GB

  [5/5] Check if the type of the given filename is 'doxyfile'      Args:      ...
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 0.5s | 15.5 tok/s | ≈0% Thinking | CPU: 15% | RAM: 9.7 GB | GPU: 94% | VRAM: 8.3 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_125542_CoderEval_AceMath 7B Instruct.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_125542_AceMath 7B Instruct.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (11s)

  >>> EvalPlus: HumanEval+ / AceMath 7B Instruct
  [codegen] humaneval [0,5] ...
)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:47
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_acemath-7b-instruct\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 0.800
humaneval+ (base + extra tests)
pass@1: 0.600

  [OK] HumanEval+ done (73s)

  >>> EvalPlus: MBPP+ / AceMath 7B Instruct
  [codegen] mbpp [0,5] ...
is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:34
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_acemath-7b-instruct\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 1.000
mbpp+ (base + extra tests)
pass@1: 1.000

  [OK] MBPP+ done (63s)

  >>> LM-Eval: ARC-Challenge / AceMath 7B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'acemath-7b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (52s)

  >>> LM-Eval: HellaSwag / AceMath 7B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'acemath-7b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |  0.4|±  |0.2449|


  [OK] HellaSwag done (63s)

  >>> LM-Eval: TruthfulQA / AceMath 7B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'acemath-7b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   | Value |   |Stderr|
|--------------|------:|------|-----:|-----------|---|------:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  | 0.2000|±  |0.2000|
|              |       |none  |     0|bleu_diff  |↑  |-0.0085|±  |1.0651|
|              |       |none  |     0|bleu_max   |↑  |12.6544|±  |5.4123|
|              |       |none  |     0|rouge1_acc |↑  | 0.2000|±  |0.2000|
|              |       |none  |     0|rouge1_diff|↑  |-2.4128|±  |2.3678|
|              |       |none  |     0|rouge1_max |↑  |36.2833|±  |9.1117|
|              |       |none  |     0|rouge2_acc |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|rouge2_diff|↑  |-1.8391|±  |2.1172|
|              |       |none  |     0|rouge2_max |↑  |25.4533|±  |8.4355|
|              |       |none  |     0|rougeL_acc |↑  | 0.4000|±  |0.2449|
|              |       |none  |     0|rougeL_diff|↑  |-1.5319|±  |2.5188|
|              |       |none  |     0|rougeL_max |↑  |34.4976|±  |9.2264|


  [OK] TruthfulQA done (59s)

  >>> MMLU-Pro (modifiziert): AceMath 7B Instruct
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_other: 100.0% (46s)
    [OK] mmlu_pro_math: 0.0% (52s)
    [OK] mmlu_pro_physics: 0.0% (53s)
    [OK] mmlu_pro_philosophy: 0.0% (79s)
    [OK] mmlu_pro_chemistry: 0.0% (58s)
  [OK] MMLU-Pro (mod.) done (288s) – Subsets: 5/5, avg: 20.0%

  >>> LM-Eval: MathQA / AceMath 7B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'acemath-7b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |  0.2|±  |   0.2|


  [OK] MathQA done (27s)

  >>> Agentic (tool-eval-bench): AceMath 7B Instruct
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (18s)

[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_acemath-7b-instruct.csv (10 Eintraege)

============================================================
  Modell 7/8: Qwen3.6 27B
  * Reasoning-Modell (erkannt) – Timeout ×2
============================================================
  [INFO] Anderes Modell geladen (AceMath 7B Instruct) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'qwen3.6-27b'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen3.6-27b
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen3.6 27B
as as pd import matplotlib.pyplot as plt...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: BESTANDEN
  Score: 100% (OK (DS1000-Harness)) | Latenz: 19.1s | 0.5 tok/s | ≈660% Thinking | CPU: 61% | RAM: 11.1 GB | GPU: 64% | VRAM: 14.8 GB

  [2/5] Problem: I have an array : a = np.array([[ 0,  1,  2,  3, 5, 6, 7, 8],...
  Score: 0% (Kein Code generiert) | Latenz: 39.7s | 0.0 tok/s | ≈0% Thinking | CPU: 52% | RAM: 11.0 GB | GPU: 67% | VRAM: 14.8 GB

  [3/5] Problem: I have a pandas dataframe that looks like the following: ID  ...

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  [RETRY] API-Fehler (Versuch 1/3): Fallback ebenfalls fehlgeschlagen

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  [RETRY] API-Fehler (Versuch 2/3): Fallback ebenfalls fehlgeschlagen

[WARN] Streaming fehlgeschlagen (No response within 67.5s (attempt 3)), Fallback ohne Streaming...

[ERROR] API-Fehler (Fallback, TimeoutError): timed out
  Score: 0% (Timeout/API-Fehler (120.0s)) | Latenz: 120.0s | 0.0 tok/s | ≈0% Thinking | CPU: 57% | RAM: 11.3 GB | GPU: 93% | VRAM: 14.9 GB

  [4/5] Problem: I have a list of numpy vectors of the format:     [array([[-0...
  Score: 0% (Kein Code generiert) | Latenz: 20.3s | 0.0 tok/s | ≈0% Thinking | CPU: 49% | RAM: 11.9 GB | GPU: 58% | VRAM: 14.9 GB

  [5/5] Problem:  I have a silly question.  I have done Cross-validation in sc...
  Score: 0% (Kein Code generiert) | Latenz: 20.3s | 0.0 tok/s | ≈0% Thinking | CPU: 49% | RAM: 11.9 GB | GPU: 60% | VRAM: 14.9 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_132234_DS1000_Qwen3.6 27B.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_132234_Qwen3.6 27B.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (947s)

  >>> Custom: CoderEval / Qwen3.6 27B
==========================================================
  LM Studio Benchmark-Tool v10
  DS1000 + CoderEval
  Subsampling: 5 Aufgaben pro Benchmark
============================================================
  Python: 3.14.6 (C:\Users\pskra\AppData\Local\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen3.6 27B
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen3.6 27B
  Aufgaben:  5
============================================================

  [1/5] Round a floating-point number....
  Score: 0% (Kein Code generiert) | Latenz: 8.6s | 0.0 tok/s | ≈0% Thinking | CPU: 52% | RAM: 11.8 GB | GPU: 61% | VRAM: 14.9 GB

  [2/5] Check whether the obj class has the fill and compute methods....
  Score: 0% (Kein Code generiert) | Latenz: 8.9s | 0.0 tok/s | ≈0% Thinking | CPU: 44% | RAM: 11.8 GB | GPU: 62% | VRAM: 14.9 GB

  [3/5] Return every response with the length of max_results     Args:     res...
  Score: 0% (Kein Code generiert) | Latenz: 9.8s | 0.0 tok/s | ≈0% Thinking | CPU: 46% | RAM: 11.9 GB | GPU: 62% | VRAM: 14.9 GB

  [4/5] Convert a string to a regex pattern object      Args:             patt...
  Score: 0% (Kein Code generiert) | Latenz: 10.8s | 0.0 tok/s | ≈0% Thinking | CPU: 50% | RAM: 11.9 GB | GPU: 61% | VRAM: 14.9 GB

  [5/5] Check whether the obj class has the run method....
  Score: 0% (Kein Code generiert) | Latenz: 10.4s | 0.0 tok/s | ≈0% Thinking | CPU: 45% | RAM: 11.8 GB | GPU: 62% | VRAM: 14.9 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_132333_CoderEval_Qwen3.6 27B.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_132333_Qwen3.6 27B.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (59s)

  >>> EvalPlus: HumanEval+ / Qwen3.6 27B
  [codegen] humaneval [0,5] ...
in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3.6-27b\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 0.800
humaneval+ (base + extra tests)
pass@1: 0.800

  [OK] HumanEval+ done (26s)

  >>> EvalPlus: MBPP+ / Qwen3.6 27B
  [codegen] mbpp [0,5] ...
7 as it is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen3.6-27b\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 0.857
mbpp+ (base + extra tests)
pass@1: 0.714

  [OK] MBPP+ done (28s)

  >>> LM-Eval: ARC-Challenge / Qwen3.6 27B
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-27b', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (82s)

  >>> LM-Eval: HellaSwag / Qwen3.6 27B
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-27b', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |    0|±  |     0|


   [OK] HellaSwag done (79s)

  >>> LM-Eval: TruthfulQA / Qwen3.6 27B
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-27b', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   |Value|   |Stderr|
|--------------|------:|------|-----:|-----------|---|----:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  |    0|±  |     0|
|              |       |none  |     0|bleu_diff  |↑  |    0|±  |     0|
|              |       |none  |     0|bleu_max   |↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rouge1_max |↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rouge2_max |↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_acc |↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_diff|↑  |    0|±  |     0|
|              |       |none  |     0|rougeL_max |↑  |    0|±  |     0|


  [OK] TruthfulQA done (114s)

 >>> MMLU-Pro (modifiziert): Qwen3.6 27B
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_biology: 0.0% (86s)
    [OK] mmlu_pro_business: 0.0% (88s)
    [OK] mmlu_pro_health: 0.0% (100s)
    [OK] mmlu_pro_chemistry: 100.0% (236s)
    [OK] mmlu_pro_history: 0.0% (113s)
  [OK] MMLU-Pro (mod.) done (622s) – Subsets: 5/5, avg: 20.0%

  >>> LM-Eval: MathQA / Qwen3.6 27B
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen3.6-27b', 'num_concurrent': 1, 'max_tokens': 4096, 'temperature': 0.0, 'top_p': 1.0, 'until': []}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |    0|±  |     0|


  [OK] MathQA done (52s)

  >>> Agentic (tool-eval-bench): Qwen3.6 27B
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (517s)
  [OK] Bereits vollstaendig in: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen3.6-27b.csv

============================================================
  Modell 8/8: Qwen2.5 Coder 14B Instruct
============================================================
  [INFO] Anderes Modell geladen (Qwen3.6 27B) – entlade...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

  [INFO] Lade 'qwen2.5-coder-14b-instruct'...
  [OK] Geladen
  [INFO] Exakte Modell-ID: qwen2.5-coder-14b-instruct
  [INFO] Warte 10s auf API-Initialisierung...

  >>> Custom: DS1000 / Qwen2.5 Coder 14B Instruct
Max absolute difference among violations: 1.5281381
Max relative difference among violations: 0.4832397
 ACTUAL: array([[-3.872983,  3.872983],
       [-4.690416,  4.690416],
       [-3.      ,  3.      ],
       [-4.242641,  4.242641]])
 DESIRED: array([[-3.872983,  3.872983],
       [-3.162278,  3.162278],
       [-4.358899,  4.358899],
       [-3.741657,  3.741657]])
  Score: 0% (Harness-Fehler: failed:
Not equal to tolerance rtol=1e-07, atol=0

Mismatched elements: 6 / 8 (75%)
First 5 mismatches are at indices:
 [1, 0]: -4.690415759827464 (ACTUAL), -3.162277660168379 (DESIRED)
 [1, 1]: 4.6904157598193965 (ACTUAL), 3.162277660168379 (DESIRED)
 [2, 0]: -2.999999999999938 (ACTUAL), -4.358898943540673 (DESIRED)
 [2, 1]: 2.999999999999977 (ACTUAL), 4.358898943540673 (DESIRED)
 [3, 0]: -4.24264068711995 (ACTUAL), -3.7416573867739413 (DESIRED)
Max absolute difference among violations: 1.5281381
Max relative difference among violations: 0.4832397
 ACTUAL: array([[-3.872983,  3.872983],
       [-4.690416,  4.690416],
       [-3.      ,  3.      ],
       [-4.242641,  4.242641]])
 DESIRED: array([[-3.872983,  3.872983],
       [-3.162278,  3.162278],
       [-4.358899,  4.358899],
       [-3.741657,  3.741657]])) | Latenz: 36.7s | 2.8 tok/s | ≈0% Thinking | CPU: 48% | RAM: 13.6 GB | GPU: 92% | VRAM: 15.7 GB

  [5/5] Problem:  I am trying to run an Elastic Net regression but get the fol...
    [EVAL] Versuche DS1000-Harness ...
    [EVAL] DS1000-Harness: FEHLGESCHLAGEN -> failed: No module named 'statsmodels'
  Score: 0% (Harness-Fehler: failed: No module named 'statsmodels') | Latenz: 32.8s | 2.6 tok/s | ≈0% Thinking | CPU: 52% | RAM: 13.7 GB | GPU: 49% | VRAM: 15.7 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_135229_DS1000_qwen2.5-coder-14b-instruct.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_135229_qwen2.5-coder-14b-instruct.csv

[INFO] Benchmark abgeschlossen.

  [OK] DS1000 done (193s)

  >>> Custom: CoderEval / Qwen2.5 Coder 14B Instruct
ocal\Programs\Python\Python314\python.exe)


[OK] LM Studio API: http://127.0.0.1:1234/v1

============================================================
  Modell 1/1: Qwen2.5 Coder 14B Instruct
============================================================

  Lade codereval_selfcontained.jsonl (5 Aufgaben)

============================================================
  Benchmark: CoderEval
  Modell:    Qwen2.5 Coder 14B Instruct
  Aufgaben:  5
============================================================

  [1/5] Convert a script to one line command with the given seperator.        ...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 5.2s | 1.9 tok/s | ≈0% Thinking | CPU: 47% | RAM: 13.5 GB | GPU: 50% | VRAM: 15.7 GB

  [2/5] Return every response with the length of max_results     Args:     res...
    [EVAL] Direkte Tests: 2/2 bestanden
  Score: 100% (Tests: 2/2) | Latenz: 6.1s | 2.3 tok/s | ≈0% Thinking | CPU: 46% | RAM: 13.5 GB | GPU: 44% | VRAM: 15.7 GB

  [3/5] Round a floating-point number....
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 2.5s | 2.0 tok/s | ≈0% Thinking | CPU: 43% | RAM: 13.5 GB | GPU: 53% | VRAM: 15.7 GB

  [4/5] Creates a configuration with some simple parameters, the key parameter...
    [EVAL] Direkte Tests: 0/2 bestanden
  Score: 0% (Tests: 0/2) | Latenz: 12.2s | 2.7 tok/s | ≈0% Thinking | CPU: 48% | RAM: 13.5 GB | GPU: 44% | VRAM: 15.7 GB

  [5/5] Check if the type of the given filename is 'doxyfile'      Args:      ...
    [EVAL] Direkte Tests: 1/1 bestanden
  Score: 100% (Tests: 1/1) | Latenz: 4.4s | 1.1 tok/s | ≈0% Thinking | CPU: 46% | RAM: 13.5 GB | GPU: 50% | VRAM: 15.7 GB
[INFO] Task-Ergebnisse: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\tasks_20260630_135309_CoderEval_qwen2.5-coder-14b-instruct.csv
[INFO] Modell-Zusammenfassung: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\model_20260630_135309_qwen2.5-coder-14b-instruct.csv

[INFO] Benchmark abgeschlossen.

  [OK] CoderEval done (40s)

  >>> EvalPlus: HumanEval+ / Qwen2.5 Coder 14B Instruct
  [codegen] humaneval [0,5] ...
ing HumanEval/162 as it is not in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 164/164 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen2.5-coder-14b-instruct\humaneval\local-model_openai_temp_0.0.jsonl

  [evaluate] humaneval ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\916d9bfe7b490c2447245ec91595fa4f.pkl
Reading samples...
humaneval (base tests)
pass@1: 1.000
humaneval+ (base + extra tests)
pass@1: 1.000

  [OK] HumanEval+ done (26s)

  >>> EvalPlus: MBPP+ / Qwen2.5 Coder 14B Instruct
  [codegen] mbpp [0,5] ...
in (0, 5)
OpenAIChatDecoder •100% ------------------------------------- 378/378 • 0:00:00
C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\evalplus_qwen2.5-coder-14b-instruct\mbpp\local-model_openai_temp_0.0.jsonl

  [evaluate] mbpp ...
Load from ground-truth from C:\Users\pskra\AppData\Local\evalplus\evalplus\Cache\92743def42b30b354a30898e4fa33fb0.pkl
Reading samples...
mbpp (base tests)
pass@1: 1.000
mbpp+ (base + extra tests)
pass@1: 1.000

  [OK] MBPP+ done (28s)

  >>> LM-Eval: ARC-Challenge / Qwen2.5 Coder 14B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-coder-14b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|      Tasks       |Version|     Filter      |n-shot|  Metric   |   |Value|   |Stderr|
|------------------|------:|-----------------|-----:|-----------|---|----:|---|-----:|
|arc_challenge_chat|      1|remove_whitespace|     0|exact_match|↑  |    0|±  |     0|


  [OK] ARC-Challenge done (90s)

  >>> LM-Eval: HellaSwag / Qwen2.5 Coder 14B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-coder-14b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks    |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|-------------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|hellaswag_gen|      1|custom-extract|     0|exact_match|↑  |    1|±  |     0|


  [OK] HellaSwag done (71s)

  >>> LM-Eval: TruthfulQA / Qwen2.5 Coder 14B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-coder-14b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|    Tasks     |Version|Filter|n-shot|  Metric   |   | Value |   |Stderr|
|--------------|------:|------|-----:|-----------|---|------:|---|-----:|
|truthfulqa_gen|      3|none  |     0|bleu_acc   |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|bleu_diff  |↑  | 1.3177|±  |0.7934|
|              |       |none  |     0|bleu_max   |↑  |11.1551|±  |3.1730|
|              |       |none  |     0|rouge1_acc |↑  | 0.8000|±  |0.2000|
|              |       |none  |     0|rouge1_diff|↑  | 2.4457|±  |1.5666|
|              |       |none  |     0|rouge1_max |↑  |29.1159|±  |6.0063|
|              |       |none  |     0|rouge2_acc |↑  | 0.6000|±  |0.2449|
|              |       |none  |     0|rouge2_diff|↑  | 1.2316|±  |1.8984|
|              |       |none  |     0|rouge2_max |↑  |21.3975|±  |5.2015|
|              |       |none  |     0|rougeL_acc |↑  | 0.8000|±  |0.2000|
|              |       |none  |     0|rougeL_diff|↑  | 2.0277|±  |1.2221|
|              |       |none  |     0|rougeL_max |↑  |28.6980|±  |6.1770|


  [OK] TruthfulQA done (85s)

  >>> MMLU-Pro (modifiziert): Qwen2.5 Coder 14B Instruct
      Subsets: 5, pro Subset: 1, gesamt: 5
    [OK] mmlu_pro_economics: 100.0% (159s)
    [OK] mmlu_pro_math: 0.0% (188s)
    [OK] mmlu_pro_law: 0.0% (140s)
    [OK] mmlu_pro_biology: 0.0% (178s)
    [OK] mmlu_pro_other: 100.0% (112s)
  [OK] MMLU-Pro (mod.) done (777s) – Subsets: 5/5, avg: 40.0%

  >>> LM-Eval: MathQA / Qwen2.5 Coder 14B Instruct
local-chat-completions ({'base_url': 'http://127.0.0.1:1234/v1/chat/completions', 'model': 'qwen2.5-coder-14b-instruct', 'num_concurrent': 1, 'eos_string': '<|endoftext|>', 'max_tokens': 1024, 'temperature': 0.0, 'top_p': 1.0}), gen_kwargs: ({}), limit: 5.0, num_fewshot: None, batch_size: 1
|  Tasks   |Version|    Filter    |n-shot|  Metric   |   |Value|   |Stderr|
|----------|------:|--------------|-----:|-----------|---|----:|---|-----:|
|mathqa_gen|      1|custom-extract|     0|exact_match|↑  |  0.6|±  |0.2449|


[OK] MathQA done (44s)

  >>> Agentic (tool-eval-bench): Qwen2.5 Coder 14B Instruct
      Szenarien: 5/69 zufaellig ausgewaehlt
  [OK] Agentic done (1006s)
  [OK] Bereits vollstaendig in: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\modell_qwen2.5-coder-14b-instruct.csv

============================================================
  FERTIG
============================================================
  [custom] Qwen3.6 28B REAP I1 / DS1000
  [custom] Qwen3.6 28B REAP I1 / CoderEval
  [evalplus] Qwen3.6 28B REAP I1 / HumanEval+
  [evalplus] Qwen3.6 28B REAP I1 / MBPP+
  [lmeval] Qwen3.6 28B REAP I1 / ARC-Challenge
  [lmeval] Qwen3.6 28B REAP I1 / HellaSwag
  [lmeval] Qwen3.6 28B REAP I1 / TruthfulQA
  [lmeval] Qwen3.6 28B REAP I1 / MMLU-Pro
  [lmeval] Qwen3.6 28B REAP I1 / MathQA
  [agentic] Qwen3.6 28B REAP I1 / Agentic
  [custom] Qwen3 Coder REAP 25B A3B I1 / DS1000
  [custom] Qwen3 Coder REAP 25B A3B I1 / CoderEval
  [evalplus] Qwen3 Coder REAP 25B A3B I1 / HumanEval+
  [evalplus] Qwen3 Coder REAP 25B A3B I1 / MBPP+
  [lmeval] Qwen3 Coder REAP 25B A3B I1 / ARC-Challenge
  [lmeval] Qwen3 Coder REAP 25B A3B I1 / HellaSwag
  [lmeval] Qwen3 Coder REAP 25B A3B I1 / TruthfulQA
  [lmeval] Qwen3 Coder REAP 25B A3B I1 / MMLU-Pro
  [lmeval] Qwen3 Coder REAP 25B A3B I1 / MathQA
  [agentic] Qwen3 Coder REAP 25B A3B I1 / Agentic
  [custom] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / DS1000
  [custom] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / CoderEval
  [evalplus] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / HumanEval+
  [evalplus] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / MBPP+
  [lmeval] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / ARC-Challenge
  [lmeval] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / HellaSwag
  [lmeval] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / TruthfulQA
  [lmeval] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / MMLU-Pro
  [lmeval] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / MathQA
  [agentic] Qwen3 Coder REAP 25B A3B I1 (qwen3-coder-reap-25b-a3b-i1@q3_k_m) / Agentic
  [custom] Qwen2.5 14B Instruct 1M / DS1000
  [custom] Qwen2.5 14B Instruct 1M / CoderEval
  [evalplus] Qwen2.5 14B Instruct 1M / HumanEval+
  [evalplus] Qwen2.5 14B Instruct 1M / MBPP+
  [lmeval] Qwen2.5 14B Instruct 1M / ARC-Challenge
  [lmeval] Qwen2.5 14B Instruct 1M / HellaSwag
  [lmeval] Qwen2.5 14B Instruct 1M / TruthfulQA
  [lmeval] Qwen2.5 14B Instruct 1M / MMLU-Pro
  [lmeval] Qwen2.5 14B Instruct 1M / MathQA
  [agentic] Qwen2.5 14B Instruct 1M / Agentic
  [custom] Qwen3 30B A3B Python Coder / DS1000
  [custom] Qwen3 30B A3B Python Coder / CoderEval
  [evalplus] Qwen3 30B A3B Python Coder / HumanEval+
  [evalplus] Qwen3 30B A3B Python Coder / MBPP+
  [lmeval] Qwen3 30B A3B Python Coder / ARC-Challenge
  [lmeval] Qwen3 30B A3B Python Coder / HellaSwag
  [lmeval] Qwen3 30B A3B Python Coder / TruthfulQA
  [lmeval] Qwen3 30B A3B Python Coder / MMLU-Pro
  [lmeval] Qwen3 30B A3B Python Coder / MathQA
  [agentic] Qwen3 30B A3B Python Coder / Agentic
  [custom] AceMath 7B Instruct / DS1000
  [custom] AceMath 7B Instruct / CoderEval
  [evalplus] AceMath 7B Instruct / HumanEval+
  [evalplus] AceMath 7B Instruct / MBPP+
  [lmeval] AceMath 7B Instruct / ARC-Challenge
  [lmeval] AceMath 7B Instruct / HellaSwag
  [lmeval] AceMath 7B Instruct / TruthfulQA
  [lmeval] AceMath 7B Instruct / MMLU-Pro
  [lmeval] AceMath 7B Instruct / MathQA
  [agentic] AceMath 7B Instruct / Agentic
  [custom] Qwen3.6 27B / DS1000
  [custom] Qwen3.6 27B / CoderEval
  [evalplus] Qwen3.6 27B / HumanEval+
  [evalplus] Qwen3.6 27B / MBPP+
  [lmeval] Qwen3.6 27B / ARC-Challenge
  [lmeval] Qwen3.6 27B / HellaSwag
  [lmeval] Qwen3.6 27B / TruthfulQA
  [lmeval] Qwen3.6 27B / MMLU-Pro
  [lmeval] Qwen3.6 27B / MathQA
  [agentic] Qwen3.6 27B / Agentic
  [custom] Qwen2.5 Coder 14B Instruct / DS1000
  [custom] Qwen2.5 Coder 14B Instruct / CoderEval
  [evalplus] Qwen2.5 Coder 14B Instruct / HumanEval+
  [evalplus] Qwen2.5 Coder 14B Instruct / MBPP+
  [lmeval] Qwen2.5 Coder 14B Instruct / ARC-Challenge
  [lmeval] Qwen2.5 Coder 14B Instruct / HellaSwag
  [lmeval] Qwen2.5 Coder 14B Instruct / TruthfulQA
  [lmeval] Qwen2.5 Coder 14B Instruct / MMLU-Pro
  [lmeval] Qwen2.5 Coder 14B Instruct / MathQA
  [agentic] Qwen2.5 Coder 14B Instruct / Agentic

  [INFO] Raeume auf – entlade Modell(e)...
  [INFO] Entlade alle Modelle...
  [OK] Entlade-Kommando gesendet
  [OK] Alter Modell vollstaendig entladen

[INFO] Aktuelle Uebersicht: C:\Users\pskra\Python-Projekte\Benchmarks\ergebnisse\konsolidiert_aktuell.csv

      
  