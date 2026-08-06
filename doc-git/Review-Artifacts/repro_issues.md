# Repro-Issues: model_registry.yaml vs. LM Studio Hub

Erzeugt automatisch: 2026-08-06 20:57:59

Source of Truth fuer Modell-Fakten sind die GGUF-Dateien (unveraenderlich).
Die `model_registry.yaml` ist editierbar (python-Programme/manuell) und wird
hier gegen die Hub-`model.yaml` (`metadataOverrides`) geprueft, die von LM
Studio mitgeliefert und nirgendwo im Prozess angefasst wird.

## Validate-Zusammenfassung

- **Gesamtprobleme (validate):** 0
- `template_missing_file`: 0
- `template_missing_config`: 0
- `missing_reasoning`: 0
- `missing_capabilities`: 0
- `missing_blueprint`: 0
- `registry_no_config`: 0
- `reasoning_arch_mismatch`: 0
- `config_context_drift`: 0
- `config_np_ukv_drift`: 0
- `config_context_too_small`: 0

## Hub-Abweichungen (Registry vs. model.yaml)

1 Registry-Einträge weichen vom Hub ab:

- **qwen/qwen3.5-9b** (qwen3.5-9b):
    - reasoning: Registry='instruct' vs Hub=True

## Hub-Hinweise (kein model.yaml im lokalen Hub)

57 Einträge haben keine lokale Hub-model.yaml (kein Abgleich moeglich, manuelle GGUF-Pruefung noetig):

- **mistralai/codestral-22b-v0.1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/phi-4**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/deepseek-coder-33b-instruct**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/devstral-small-2-24b-instruct-2512**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/ernie-4.5-21b-a3b-pt@iq4_nl**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **tiiuae/falcon3-10b-instruct**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **mradermacher/gemma-4-26b-a4b-it-i1@iq4_xs**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **unsloth/gemma-4-26b-a4b-it@iq3_s**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **ibm-granite/granite-4.0-h-tiny**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **ibm-granite/granite-4.1-30b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/januscoder-14b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **jetbrains/mellum2-12b-a2.5b-instruct**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **lmstudio-community/ministral-3-14b-instruct-2512**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/kimi-linear-reap-35b-a3b-instruct.i1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/nemotron-cascade-14b-thinking**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **nerdsking/nerdsking-python-coder-7b-i**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/qwen3-30b-a3b-instruct-2507**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/qwen3-coder-30b-a3b-instruct**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/qwen3-coder-reap-25b-a3b-i1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/qwen3-coder-reap-25b-a3b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/north-mini-code-1.0**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **qwen/qwen2.5-coder-14b-instruct@q5_0**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **qwen/qwen2.5-coder-14b-instruct@q5_k_m**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **qwen/qwen2.5-coder-14b-instruct@q6_k**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **Qwen/Qwen3.5-9B-GGUF@q6_k**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **unsloth/qwen3.6-27b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/qwen3.6-27b-mtp**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/qwen3.6-27b-i1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/qwen3.6-28b-reap-i1@iq3_s**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **mradermacher/qwen3.6-28b-reap-i1@q3_k_s**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **bartowski/mistralai_magistral-small-2509**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **lmstudio-community/deepseek-r1-distill-qwen-14b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **gabriellarson/mamba-codestral-7b-v0.1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **tiiuae/falcon3-mamba-7b-instruct**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **internlm/internlm2_5-20b-chat**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **lmstudio-community/deepseek-coder-v2-lite-instruct**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **lmstudio-community/internlm2-math-plus-20b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **google/gemma-4-12b-it-qat**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **quietimpostor/nemotron-3-nano-reap-21b-a3b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **intel/qwen3-30b-a3b-thinking-2507-q2ks-mixed-autoround**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **intel/qwen3-coder-30b-a3b-instruct-q2ks-mixed-autoround**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **intel/mirothinker-v1.5-30b-q2ks-mixed-autoround**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
- **jetbrains/mellum2-12b-a2.5b-thinking_moe**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **noctrex/lfm2-24b-a2b_moe**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/glm-4.7-flash**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/glm-4.7-flash-reap-23b-a3b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **noctrex/ernie-4.5-21b-a3b-pt_moe**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/gemma-4-19b-a4b-it-reap-i1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **ibm-granite/granite-4.1-8b**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **mradermacher/gemma-4-26b-a4b-it-i1**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **bartowski/google_gemma-4-26b-a4b-it**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/gemma-4-26b-a4b-it**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/ernie-4.5-21b-a3b-pt**: kein Hub-modell.yaml gefunden (Registry hat GGUF-Größe)
- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: Quant-Variante ohne eigene model.yaml (Basis-Modell im Hub trägt die Architektur-Infos)
