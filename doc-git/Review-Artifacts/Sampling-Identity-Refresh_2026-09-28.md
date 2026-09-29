# Sampling-Identität: gezielter Refresh am 28.09.2026

Die Basis ist der aktuelle Stand nach dem vom Benutzer parallel abgeschlossenen `sync --import-lms-settings --refresh-sampling`. Frühere Registry-Daten wurden nicht zurückgespielt.

- Baseline SHA256: `02072357fc8682a137c0a616fb46b76f7568e4103e0d7e891d0ac9332970fec4`.
- Backup: `model_registry_before_R09_20260928_134721.yaml` unter `backups/` (maschinenlokal, gitignoriert).
- Einträge insgesamt: 71; numerische Profile auditiert: 41.
- Gezielt ausgewählt: 36; erneut confirmed: 17; offen/unresolved/conflict/not_found: 19.
- Registry SHA256 nach Anwendung: `659670592c105617f8a6a2fca127454474d7119ab26fe81c8825b07c1158f140`.

Auswahl: Nur bereits numerisch belegte Profile mit einer Quelle außerhalb des nachgewiesenen Artefakt-/Quantisierungsbezugs, ohne exakten Modellabschnitt in einem Publisher-Dokument oder ohne eindeutigen IdentityLink wurden erneut recherchiert. Es gab keinen Refresh aller Registry-Einträge. Ausschließlich Sampling-Blöcke ausgewählter Einträge wurden verändert; LMS-JSONs und übrige Modellfelder blieben unverändert.

Eine `base_model:quantized:`-Beziehung oder `base_model_relation: quantized` erlaubt die identische Base-Modellquelle. Finetune-, Adapter-, Merge- oder bloße Base-Abstammung erlaubt keine Übernahme. Unbewiesene Suchtreffer und allgemeine Publisher-/Backend-Seiten bestätigen keine Werte. Wenn kein belastbares Profil bleibt, enthält der neue Block keine numerischen Empfehlungen und markiert die offene Recherche ausdrücklich.

## Ausgewählte Profile

### `ggml-org/gpt-oss-20b@mxfp4`

Grund: Repository huihui-ai/Huihui-gpt-oss-20b-mxfp4-abliterated-v2 liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: `ggml-org/gpt-oss-20b-MXFP4-GGUF`

Metadatenbeziehung:

- [ggml-org/gpt-oss-20b-MXFP4-GGUF](https://huggingface.co/api/models/ggml-org/gpt-oss-20b-MXFP4-GGUF?full=false): metadata unavailable; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 0.7, "top_k": 20, "top_p": 0.8}, "coding": {"temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"temperature": 0.7, "top_k": 20, "top_p": 0.8}}
```

Alte Quellen:

- [https://huggingface.co/huihui-ai/Huihui-gpt-oss-20b-mxfp4-abliterated-v2/raw/main/README.md](https://huggingface.co/huihui-ai/Huihui-gpt-oss-20b-mxfp4-abliterated-v2/raw/main/README.md): outside proven chain.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `unsloth/ernie-4.5-21b-a3b-pt@iq4_nl`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Quelle https://github.com/PaddlePaddle/ERNIE belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"temperature": 0.8, "top_p": 0.95}, "coding": {"temperature": 0.8, "top_p": 0.95}, "knowledge": {"temperature": 0.8, "top_p": 0.95}, "math": {"temperature": 0.8, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/PaddlePaddle/ERNIE](https://github.com/PaddlePaddle/ERNIE): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `unsloth/qwen3-30b-a3b-instruct-2507@q3_k_s`

Grund: Quelle https://github.com/QwenLM/Qwen-Agent belegt keinen Sampling-Abschnitt für die exakte Modellvariante. Quelle https://github.com/QwenLM/Qwen3 belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF`

Metadatenbeziehung:

- [unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF](https://huggingface.co/api/models/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- [Qwen/Qwen3-30B-A3B-Instruct-2507](https://huggingface.co/api/models/Qwen/Qwen3-30B-A3B-Instruct-2507?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"top_p": 0.8}, "coding": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/QwenLM/Qwen-Agent](https://github.com/QwenLM/Qwen-Agent): no exact model sampling scope.
- [https://github.com/QwenLM/Qwen3](https://github.com/QwenLM/Qwen3): no exact model sampling scope.
- [https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/raw/main/README.md](https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/raw/main/README.md): artifact.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "coding": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://github.com/QwenLM/Qwen3](https://github.com/QwenLM/Qwen3)
- [https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/raw/main/README.md](https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/raw/main/README.md)

### `mradermacher/qwen3.6-28b-reap-i1@iq3_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `mradermacher/Qwen3.6-28B-REAP-i1-GGUF`

Metadatenbeziehung:

- [mradermacher/Qwen3.6-28B-REAP-i1-GGUF](https://huggingface.co/api/models/mradermacher/Qwen3.6-28B-REAP-i1-GGUF?full=false): identity verified; quantisierte Bases: `0xSero/Qwen3.6-28B`
- [0xSero/Qwen3.6-28B](https://huggingface.co/api/models/0xSero/Qwen3.6-28B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/mradermacher/Qwen3.6-28B-REAP-i1-GGUF/raw/main/README.md](https://huggingface.co/mradermacher/Qwen3.6-28B-REAP-i1-GGUF/raw/main/README.md)

### `mradermacher/qwen3.6-28b-reap-i1@q3_k_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `mradermacher/Qwen3.6-28B-REAP-i1-GGUF`

Metadatenbeziehung:

- [mradermacher/Qwen3.6-28B-REAP-i1-GGUF](https://huggingface.co/api/models/mradermacher/Qwen3.6-28B-REAP-i1-GGUF?full=false): identity verified; quantisierte Bases: `0xSero/Qwen3.6-28B`
- [0xSero/Qwen3.6-28B](https://huggingface.co/api/models/0xSero/Qwen3.6-28B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/mradermacher/Qwen3.6-28B-REAP-i1-GGUF/raw/main/README.md](https://huggingface.co/mradermacher/Qwen3.6-28B-REAP-i1-GGUF/raw/main/README.md)

### `noctrex/ernie-4.5-21b-a3b-pt_moe@mxfp4`

Grund: Quelle https://github.com/PaddlePaddle/ERNIE belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `noctrex/ERNIE-4.5-21B-A3B-PT-MXFP4_MOE-GGUF`

Metadatenbeziehung:

- [noctrex/ERNIE-4.5-21B-A3B-PT-MXFP4_MOE-GGUF](https://huggingface.co/api/models/noctrex/ERNIE-4.5-21B-A3B-PT-MXFP4_MOE-GGUF?full=false): identity verified; quantisierte Bases: `baidu/ERNIE-4.5-21B-A3B-PT`
- [baidu/ERNIE-4.5-21B-A3B-PT](https://huggingface.co/api/models/baidu/ERNIE-4.5-21B-A3B-PT?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 0.8, "top_p": 0.95}, "coding": {"temperature": 0.8, "top_p": 0.95}, "knowledge": {"temperature": 0.8, "top_p": 0.95}, "math": {"temperature": 0.8, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/PaddlePaddle/ERNIE](https://github.com/PaddlePaddle/ERNIE): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/noctrex/ERNIE-4.5-21B-A3B-PT-MXFP4_MOE-GGUF/raw/main/README.md](https://huggingface.co/noctrex/ERNIE-4.5-21B-A3B-PT-MXFP4_MOE-GGUF/raw/main/README.md)

### `mradermacher/qwen3-coder-reap-25b-a3b-i1@q3_k_m`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `mradermacher/Qwen3-Coder-REAP-25B-A3B-i1-GGUF`

Metadatenbeziehung:

- [mradermacher/Qwen3-Coder-REAP-25B-A3B-i1-GGUF](https://huggingface.co/api/models/mradermacher/Qwen3-Coder-REAP-25B-A3B-i1-GGUF?full=false): identity verified; quantisierte Bases: `cerebras/Qwen3-Coder-REAP-25B-A3B`
- [cerebras/Qwen3-Coder-REAP-25B-A3B](https://huggingface.co/api/models/cerebras/Qwen3-Coder-REAP-25B-A3B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/mradermacher/Qwen3-Coder-REAP-25B-A3B-i1-GGUF/raw/main/README.md](https://huggingface.co/mradermacher/Qwen3-Coder-REAP-25B-A3B-i1-GGUF/raw/main/README.md)

### `lmstudio-community/internlm2-math-plus-20b@q4_k_m`

Grund: Quelle https://github.com/InternLM/InternLM belegt keinen Sampling-Abschnitt für die exakte Modellvariante. Quelle https://github.com/InternLM/InternLM-XComposer belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `lmstudio-community/internlm2-math-plus-20b-GGUF`

Metadatenbeziehung:

- [lmstudio-community/internlm2-math-plus-20b-GGUF](https://huggingface.co/api/models/lmstudio-community/internlm2-math-plus-20b-GGUF?full=false): identity verified; quantisierte Bases: `internlm/internlm2-math-plus-20b`
- [internlm/internlm2-math-plus-20b](https://huggingface.co/api/models/internlm/internlm2-math-plus-20b?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "coding": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "knowledge": {"repetition_penalty": 3.0}, "math": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "thinking": {"enabled": true, "repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}}
```

Alte Quellen:

- [https://github.com/InternLM/InternLM](https://github.com/InternLM/InternLM): no exact model sampling scope.
- [https://github.com/InternLM/InternLM-XComposer](https://github.com/InternLM/InternLM-XComposer): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/lmstudio-community/internlm2-math-plus-20b-GGUF/raw/main/README.md](https://huggingface.co/lmstudio-community/internlm2-math-plus-20b-GGUF/raw/main/README.md)

### `intel/qwen3-30b-a3b-instruct-2507-q2ks-mixed-autoround@q2_k_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `Intel/Qwen3-30B-A3B-Instruct-2507-gguf-q2ks-mixed-AutoRound`

Metadatenbeziehung:

- [Intel/Qwen3-30B-A3B-Instruct-2507-gguf-q2ks-mixed-AutoRound](https://huggingface.co/api/models/Intel/Qwen3-30B-A3B-Instruct-2507-gguf-q2ks-mixed-AutoRound?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- [Qwen/Qwen3-30B-A3B-Instruct-2507](https://huggingface.co/api/models/Qwen/Qwen3-30B-A3B-Instruct-2507?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "coding": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://github.com/QwenLM/Qwen3](https://github.com/QwenLM/Qwen3)
- [https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507/raw/main/README.md](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507/raw/main/README.md)

### `essentialai/rnj-1@q8_0`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Repository essentialai/rnj-1 liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"temperature": 0.2, "top_p": 0.95}, "coding": {"temperature": 0.2, "top_p": 0.95}, "knowledge": {"temperature": 0.2, "top_p": 0.95}, "math": {"temperature": 0.2, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/essentialai/rnj-1/raw/main/README.md](https://huggingface.co/essentialai/rnj-1/raw/main/README.md): outside proven chain.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `qwen/qwen3-14b@q6_k`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Quelle https://github.com/QwenLM/Qwen3 belegt keinen Sampling-Abschnitt für die exakte Modellvariante. Repository qwen/qwen3-14b liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/QwenLM/Qwen3](https://github.com/QwenLM/Qwen3): no exact model sampling scope.
- [https://huggingface.co/qwen/qwen3-14b/raw/main/README.md](https://huggingface.co/qwen/qwen3-14b/raw/main/README.md): outside proven chain.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `unsloth/gemma-4-12b-it@q6_k`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Repository unsloth/gemma-4-12b-it liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/unsloth/gemma-4-12b-it/raw/main/README.md](https://huggingface.co/unsloth/gemma-4-12b-it/raw/main/README.md): outside proven chain.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `peculiar-ragdoll/tiel-coder-35b-a3b@iq3_xxs`

Grund: Repository LuffyTheFox/Tiel-Coder-35B-A3B-Genesis-Hermes-GGUF liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: `peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF`

Metadatenbeziehung:

- [peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF](https://huggingface.co/api/models/peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF?full=false): identity verified; quantisierte Bases: `ornith-ai/Ornith-1.5-35B-A3B`
- [ornith-ai/Ornith-1.5-35B-A3B](https://huggingface.co/api/models/ornith-ai/Ornith-1.5-35B-A3B?full=false): identity verified; quantisierte Bases: keine

Vorher: `conflict`

```json
{"coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/LuffyTheFox/Tiel-Coder-35B-A3B-Genesis-Hermes-GGUF/raw/main/README.md](https://huggingface.co/LuffyTheFox/Tiel-Coder-35B-A3B-Genesis-Hermes-GGUF/raw/main/README.md): outside proven chain.
- [https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B/raw/main/README.md](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B/raw/main/README.md): quantized chain.

Nachher: `conflict`

```json
{"coding": {"temperature": 0.6, "top_k": 20, "top_p": 0.95}, "knowledge": {"temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B/raw/main/README.md](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B/raw/main/README.md)
- [https://huggingface.co/peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF/raw/main/README.md](https://huggingface.co/peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF/raw/main/README.md)

### `internlm/internlm2_5-20b-chat@q4_k_m`

Grund: Quelle https://github.com/InternLM/InternLM belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `internlm/internlm2_5-20b-chat-gguf`

Metadatenbeziehung:

- [internlm/internlm2_5-20b-chat-gguf](https://huggingface.co/api/models/internlm/internlm2_5-20b-chat-gguf?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "coding": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "knowledge": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "math": {"repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}, "thinking": {"enabled": true, "repetition_penalty": 1.005, "temperature": 1.0, "top_k": 40, "top_p": 0.8}}
```

Alte Quellen:

- [https://github.com/InternLM/InternLM](https://github.com/InternLM/InternLM): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 0.8, "top_k": 50, "top_p": 0.8}, "coding": {"temperature": 0.8, "top_k": 50, "top_p": 0.8}, "knowledge": {"temperature": 0.8, "top_k": 50, "top_p": 0.8}, "math": {"temperature": 0.8, "top_k": 50, "top_p": 0.8}}
```

Neue Quellen:

- [https://huggingface.co/internlm/internlm2_5-20b-chat-gguf/raw/main/README.md](https://huggingface.co/internlm/internlm2_5-20b-chat-gguf/raw/main/README.md)

### `lmstudio-community/starcoder2-15b-instruct-v0.1@q6_k`

Grund: Quelle https://huggingface.co/papers/2402.19173 belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `lmstudio-community/starcoder2-15b-instruct-v0.1-GGUF`

Metadatenbeziehung:

- [lmstudio-community/starcoder2-15b-instruct-v0.1-GGUF](https://huggingface.co/api/models/lmstudio-community/starcoder2-15b-instruct-v0.1-GGUF?full=false): identity verified; quantisierte Bases: `bigcode/starcoder2-15b`
- [bigcode/starcoder2-15b](https://huggingface.co/api/models/bigcode/starcoder2-15b?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 0.2, "top_p": 0.95}, "coding": {"temperature": 0.2, "top_p": 0.95}, "knowledge": {"temperature": 0.2, "top_p": 0.95}, "math": {"temperature": 0.2, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/papers/2402.19173](https://huggingface.co/papers/2402.19173): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 0.2, "top_p": 0.95}, "coding": {"temperature": 0.2, "top_p": 0.95}, "knowledge": {"temperature": 0.2, "top_p": 0.95}, "math": {"temperature": 0.2, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/bigcode/starcoder2-15b/raw/main/README.md](https://huggingface.co/bigcode/starcoder2-15b/raw/main/README.md)

### `mradermacher/granite-4.2-30b-i1@iq3_m`

Grund: Quelle https://github.com/ibm-granite/granite-4.2-language-models belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `mradermacher/granite-4.2-30b-i1-GGUF`

Metadatenbeziehung:

- [mradermacher/granite-4.2-30b-i1-GGUF](https://huggingface.co/api/models/mradermacher/granite-4.2-30b-i1-GGUF?full=false): identity verified; quantisierte Bases: `ibm-granite/granite-4.2-30b`
- [ibm-granite/granite-4.2-30b](https://huggingface.co/api/models/ibm-granite/granite-4.2-30b?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_p": 0.95}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "temperature": 1.0, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/ibm-granite/granite-4.2-language-models](https://github.com/ibm-granite/granite-4.2-language-models): no exact model sampling scope.
- [https://huggingface.co/ibm-granite/granite-4.2-30b/raw/main/README.md](https://huggingface.co/ibm-granite/granite-4.2-30b/raw/main/README.md): quantized chain.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_p": 0.95}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "temperature": 1.0, "top_p": 0.95}}
```

Neue Quellen:

- [https://github.com/ibm-granite/granite-4.2-language-models](https://github.com/ibm-granite/granite-4.2-language-models)
- [https://www.ibm.com/granite/docs/models/granite4-2](https://www.ibm.com/granite/docs/models/granite4-2)

### `byteshape/qwen3.6-35b-a3b@iq3_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `byteshape/Qwen3.6-35B-A3B-GGUF`

Metadatenbeziehung:

- [byteshape/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/api/models/byteshape/Qwen3.6-35B-A3B-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.6-35B-A3B`
- [Qwen/Qwen3.6-35B-A3B](https://huggingface.co/api/models/Qwen/Qwen3.6-35B-A3B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "thinking": {"enabled": true, "min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/main/README.md)

### `byteshape/qwen3.8-27b@iq4_xs`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `byteshape/Qwen3.8-27B-GGUF`

Metadatenbeziehung:

- [byteshape/Qwen3.8-27B-GGUF](https://huggingface.co/api/models/byteshape/Qwen3.8-27B-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.8-27B`
- [Qwen/Qwen3.8-27B](https://huggingface.co/api/models/Qwen/Qwen3.8-27B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md)

### `jrell/qwen3.8-27b-i1-smaller@iq4_xs`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `jrell/Qwen3.8-27B-i1-IQ4_XS-GGUF-Smaller`

Metadatenbeziehung:

- [jrell/Qwen3.8-27B-i1-IQ4_XS-GGUF-Smaller](https://huggingface.co/api/models/jrell/Qwen3.8-27B-i1-IQ4_XS-GGUF-Smaller?full=false): identity verified; quantisierte Bases: `unsloth/Qwen3.8-27B-GGUF`
- [unsloth/Qwen3.8-27B-GGUF](https://huggingface.co/api/models/unsloth/Qwen3.8-27B-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.8-27B`
- [Qwen/Qwen3.8-27B](https://huggingface.co/api/models/Qwen/Qwen3.8-27B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md)
- [https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/raw/main/README.md](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/raw/main/README.md)

### `unsloth/qwen3.6-27b-mtp@iq3_xxs`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `unsloth/Qwen3.6-27B-MTP-GGUF`

Metadatenbeziehung:

- [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/api/models/unsloth/Qwen3.6-27B-MTP-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.6-27B`
- [Qwen/Qwen3.6-27B](https://huggingface.co/api/models/Qwen/Qwen3.6-27B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "coding": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}}
```

Neue Quellen:

- [https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF/raw/main/README.md](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF/raw/main/README.md)

### `tooltd/qwen3.6-27b-mini-xs-mtp-16gb-vram@iq4_xs`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `bytkim/qwen3.6-27b-mtp-pi-tune@q3_k_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `bytkim/Qwen3.6-27B-MTP-pi-tune-GGUF`

Metadatenbeziehung:

- [bytkim/Qwen3.6-27B-MTP-pi-tune-GGUF](https://huggingface.co/api/models/bytkim/Qwen3.6-27B-MTP-pi-tune-GGUF?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "presence_penalty": 1.5, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "coding": {"min_p": 0.0, "presence_penalty": 1.5, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "presence_penalty": 1.5, "temperature": 0.7, "top_k": 20, "top_p": 0.8}}
```

Neue Quellen:

- [https://huggingface.co/bytkim/Qwen3.6-27B-MTP-pi-tune-GGUF/raw/main/README.md](https://huggingface.co/bytkim/Qwen3.6-27B-MTP-pi-tune-GGUF/raw/main/README.md)

### `byteshape/qwen3-coder-30b-a3b-instruct@iq3_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `byteshape/Qwen3-Coder-30B-A3B-Instruct-GGUF`

Metadatenbeziehung:

- [byteshape/Qwen3-Coder-30B-A3B-Instruct-GGUF](https://huggingface.co/api/models/byteshape/Qwen3-Coder-30B-A3B-Instruct-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- [Qwen/Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/api/models/Qwen/Qwen3-Coder-30B-A3B-Instruct?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"repetition_penalty": 1.05, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "coding": {"repetition_penalty": 1.05, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"repetition_penalty": 1.05, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"repetition_penalty": 1.05, "temperature": 0.7, "top_k": 20, "top_p": 0.8}}
```

Neue Quellen:

- [https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct/raw/main/README.md](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct/raw/main/README.md)

### `byteshape/qwen3.5-9b@q5_k_s`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `byteshape/Qwen3.5-9B-GGUF`

Metadatenbeziehung:

- [byteshape/Qwen3.5-9B-GGUF](https://huggingface.co/api/models/byteshape/Qwen3.5-9B-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.5-9B`
- [Qwen/Qwen3.5-9B](https://huggingface.co/api/models/Qwen/Qwen3.5-9B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `conflict`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/byteshape/Qwen3.5-9B-GGUF/raw/main/README.md](https://huggingface.co/byteshape/Qwen3.5-9B-GGUF/raw/main/README.md)

### `mradermacher/gemma-4-31b-i1@iq3_xs`

Grund: Repository coder3101/gemma-4-31B-it-heretic liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: `mradermacher/gemma-4-31B-i1-GGUF`

Metadatenbeziehung:

- [mradermacher/gemma-4-31B-i1-GGUF](https://huggingface.co/api/models/mradermacher/gemma-4-31B-i1-GGUF?full=false): identity verified; quantisierte Bases: `google/gemma-4-31B`
- [google/gemma-4-31B](https://huggingface.co/api/models/google/gemma-4-31B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/coder3101/gemma-4-31B-it-heretic/raw/main/README.md](https://huggingface.co/coder3101/gemma-4-31B-it-heretic/raw/main/README.md): outside proven chain.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/google/gemma-4-31B/raw/main/README.md](https://huggingface.co/google/gemma-4-31B/raw/main/README.md)

### `freedomaisvr/gemma-4-12b-it-qat@nvfp4`

Grund: Repository SC117/gemma-4-12B-it-heretic-QAT-GGUF liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: `FreedomAISVR/Gemma-4-12B-it-QAT-NVFP4-GGUF`

Metadatenbeziehung:

- [FreedomAISVR/Gemma-4-12B-it-QAT-NVFP4-GGUF](https://huggingface.co/api/models/FreedomAISVR/Gemma-4-12B-it-QAT-NVFP4-GGUF?full=false): identity verified; quantisierte Bases: `google/gemma-4-12B-it-qat-q4_0-unquantized`
- [google/gemma-4-12B-it-qat-q4_0-unquantized](https://huggingface.co/api/models/google/gemma-4-12B-it-qat-q4_0-unquantized?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"temperature": 0.6, "top_k": 64, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"temperature": 0.6, "top_k": 64, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/SC117/gemma-4-12B-it-heretic-QAT-GGUF/raw/main/README.md](https://huggingface.co/SC117/gemma-4-12B-it-heretic-QAT-GGUF/raw/main/README.md): outside proven chain.
- [https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-unquantized/raw/main/README.md](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-unquantized/raw/main/README.md): quantized chain.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-unquantized/raw/main/README.md](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-unquantized/raw/main/README.md)

### `ibm-granite/granite-4.2-8b@q6_k`

Grund: Quelle https://github.com/ibm-granite/granite-4.2-language-models belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `ibm-granite/granite-4.2-8b-GGUF`

Metadatenbeziehung:

- [ibm-granite/granite-4.2-8b-GGUF](https://huggingface.co/api/models/ibm-granite/granite-4.2-8b-GGUF?full=false): identity verified; quantisierte Bases: `ibm-granite/granite-4.2-8b`
- [ibm-granite/granite-4.2-8b](https://huggingface.co/api/models/ibm-granite/granite-4.2-8b?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_p": 0.95}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "temperature": 1.0, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/ibm-granite/granite-4.2-language-models](https://github.com/ibm-granite/granite-4.2-language-models): no exact model sampling scope.
- [https://huggingface.co/ibm-granite/granite-4.2-8b/raw/main/README.md](https://huggingface.co/ibm-granite/granite-4.2-8b/raw/main/README.md): quantized chain.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_p": 0.95}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "temperature": 1.0, "top_p": 0.95}}
```

Neue Quellen:

- [https://github.com/ibm-granite/granite-4.2-language-models](https://github.com/ibm-granite/granite-4.2-language-models)
- [https://huggingface.co/ibm-granite/granite-4.2-8b/raw/main/README.md](https://huggingface.co/ibm-granite/granite-4.2-8b/raw/main/README.md)

### `llmsforall/millie-35b-a3b-11gb@?`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Quelle https://github.com/llmsforall/llama.cpp belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 1.0, "top_k": 64, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"min_p": 0.0, "temperature": 1.0, "top_k": 64, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/llmsforall/llama.cpp](https://github.com/llmsforall/llama.cpp): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `mrfuzzihead/qwen3.8-35b-a3b-distill-apex@?`

Grund: Kein eindeutiger vollständiger IdentityLink zum lokalen Hauptartefakt. Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: keine eindeutige Bindung

Metadatenbeziehung:

- Kein lokales Artefakt als sicherer Startpunkt; keine Alias-/Publisher-Heuristik eingesetzt.

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- Keine belegte Modellquelle erreichbar beziehungsweise keine eindeutige lokale Bindung.

### `unsloth/qwen3.6-35b-a3b-mtp@iq2_m`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`

Metadatenbeziehung:

- [unsloth/Qwen3.6-35B-A3B-MTP-GGUF](https://huggingface.co/api/models/unsloth/Qwen3.6-35B-A3B-MTP-GGUF?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.6-35B-A3B`
- [Qwen/Qwen3.6-35B-A3B](https://huggingface.co/api/models/Qwen/Qwen3.6-35B-A3B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `conflict`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/raw/main/README.md](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/raw/main/README.md)

### `roleplaiapp/deepseek-r1-distill-qwen-32b@q2_k`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `roleplaiapp/DeepSeek-R1-Distill-Qwen-32B-Q2_K-GGUF`

Metadatenbeziehung:

- [roleplaiapp/DeepSeek-R1-Distill-Qwen-32B-Q2_K-GGUF](https://huggingface.co/api/models/roleplaiapp/DeepSeek-R1-Distill-Qwen-32B-Q2_K-GGUF?full=false): identity verified; quantisierte Bases: `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B`
- [deepseek-ai/DeepSeek-R1-Distill-Qwen-32B](https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/roleplaiapp/DeepSeek-R1-Distill-Qwen-32B-Q2_K-GGUF/raw/main/README.md](https://huggingface.co/roleplaiapp/DeepSeek-R1-Distill-Qwen-32B-Q2_K-GGUF/raw/main/README.md)

### `intel/qwen3.8-27b-q2ks-autoround@q2_k_s`

Grund: Quelle https://github.com/intel/auto-round belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `Intel/Qwen3.8-27B-q2ks-AutoRound`

Metadatenbeziehung:

- [Intel/Qwen3.8-27B-q2ks-AutoRound](https://huggingface.co/api/models/Intel/Qwen3.8-27B-q2ks-AutoRound?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.8-27B`
- [Qwen/Qwen3.8-27B](https://huggingface.co/api/models/Qwen/Qwen3.8-27B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"temperature": 0.6, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"temperature": 0.6, "top_p": 0.95}, "thinking": {"enabled": true, "min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/intel/auto-round](https://github.com/intel/auto-round): no exact model sampling scope.
- [https://huggingface.co/Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B): quantized chain.

Nachher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_p": 0.95}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"temperature": 1.0, "top_p": 0.95}, "thinking": {"enabled": true, "min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md)

### `gguf-org/muse-glimmer-30b@nvfp4`

Grund: Quelle https://github.com/z-lab/dflash belegt keinen Sampling-Abschnitt für die exakte Modellvariante. Repository 0bserverx/Muse-Glimmer-30B-Heretic-Uncensored-GGUF liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung. Repository Blackfrost-AI/Muse-Glimmer-30B-Abliterated-BF16 liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: `gguf-org/muse-glimmer-30b-gguf`

Metadatenbeziehung:

- [gguf-org/muse-glimmer-30b-gguf](https://huggingface.co/api/models/gguf-org/muse-glimmer-30b-gguf?full=false): identity verified; quantisierte Bases: `meta-models/Muse-Glimmer-30B`
- [meta-models/Muse-Glimmer-30B](https://huggingface.co/api/models/meta-models/Muse-Glimmer-30B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "coding": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "knowledge": {"temperature": 1.0, "top_k": 64, "top_p": 0.95}, "math": {"temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/z-lab/dflash](https://github.com/z-lab/dflash): no exact model sampling scope.
- [https://huggingface.co/0bserverx/Muse-Glimmer-30B-Heretic-Uncensored-GGUF/raw/main/README.md](https://huggingface.co/0bserverx/Muse-Glimmer-30B-Heretic-Uncensored-GGUF/raw/main/README.md): outside proven chain.
- [https://huggingface.co/Blackfrost-AI/Muse-Glimmer-30B-Abliterated-BF16/raw/main/README.md](https://huggingface.co/Blackfrost-AI/Muse-Glimmer-30B-Abliterated-BF16/raw/main/README.md): outside proven chain.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/gguf-org/muse-glimmer-30b-gguf/raw/main/README.md](https://huggingface.co/gguf-org/muse-glimmer-30b-gguf/raw/main/README.md)

### `prism-ml/ternary-bonsai-27b@q2_g64`

Grund: Repository Qwen/Qwen3.8-27B liegt außerhalb der belegten Artefakt-/Quantisierungsbeziehung.

Artefakt-Repositories: `prism-ml/Ternary-Bonsai-27B-gguf`

Metadatenbeziehung:

- [prism-ml/Ternary-Bonsai-27B-gguf](https://huggingface.co/api/models/prism-ml/Ternary-Bonsai-27B-gguf?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.6-27B`
- [Qwen/Qwen3.6-27B](https://huggingface.co/api/models/Qwen/Qwen3.6-27B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://huggingface.co/Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B): quantized chain.
- [https://huggingface.co/Qwen/Qwen3.6-27B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.6-27B/raw/main/README.md): quantized chain.
- [https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md): outside proven chain.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 0.7, "top_k": 20, "top_p": 0.95}, "coding": {"temperature": 0.7, "top_k": 20, "top_p": 0.95}, "knowledge": {"temperature": 0.7, "top_k": 20, "top_p": 0.95}, "math": {"temperature": 0.7, "top_k": 20, "top_p": 0.95}}
```

Neue Quellen:

- [https://huggingface.co/prism-ml/Ternary-Bonsai-27B-gguf/raw/main/README.md](https://huggingface.co/prism-ml/Ternary-Bonsai-27B-gguf/raw/main/README.md)

### `mradermacher/r3-qwen3-14b-lora-4k-i1@q6_k`

Grund: Quelle https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `mradermacher/R3-Qwen3-14B-LoRA-4k-i1-GGUF`

Metadatenbeziehung:

- [mradermacher/R3-Qwen3-14B-LoRA-4k-i1-GGUF](https://huggingface.co/api/models/mradermacher/R3-Qwen3-14B-LoRA-4k-i1-GGUF?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "thinking": {"enabled": true, "min_p": 0.0, "temperature": 0.6, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html): no exact model sampling scope.

Nachher: `unresolved`

```json
{}
```

Neue Quellen:

- [https://huggingface.co/mradermacher/R3-Qwen3-14B-LoRA-4k-i1-GGUF/raw/main/README.md](https://huggingface.co/mradermacher/R3-Qwen3-14B-LoRA-4k-i1-GGUF/raw/main/README.md)

### `vinpix/ternary-bonsai-27b-stock-mtp@q2_k`

Grund: Quelle https://github.com/PrismML-Eng/Bonsai-demo belegt keinen Sampling-Abschnitt für die exakte Modellvariante.

Artefakt-Repositories: `vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF`

Metadatenbeziehung:

- [vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF](https://huggingface.co/api/models/vinpix/Ternary-Bonsai-27B-Stock-MTP-GGUF?full=false): identity verified; quantisierte Bases: `prism-ml/Ternary-Bonsai-27B-gguf`
- [prism-ml/Ternary-Bonsai-27B-gguf](https://huggingface.co/api/models/prism-ml/Ternary-Bonsai-27B-gguf?full=false): identity verified; quantisierte Bases: `Qwen/Qwen3.6-27B`
- [Qwen/Qwen3.6-27B](https://huggingface.co/api/models/Qwen/Qwen3.6-27B?full=false): identity verified; quantisierte Bases: keine

Vorher: `confirmed`

```json
{"agentic": {"min_p": 0.05, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.05, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "knowledge": {"min_p": 0.05, "temperature": 1.0, "top_k": 20, "top_p": 0.95}, "math": {"min_p": 0.05, "temperature": 1.0, "top_k": 20, "top_p": 0.95}}
```

Alte Quellen:

- [https://github.com/PrismML-Eng/Bonsai-demo](https://github.com/PrismML-Eng/Bonsai-demo): no exact model sampling scope.

Nachher: `confirmed`

```json
{"agentic": {"temperature": 1.0, "top_k": 20, "top_p": 0.95}, "coding": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "knowledge": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}, "math": {"min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "temperature": 0.7, "top_k": 20, "top_p": 0.8}}
```

Neue Quellen:

- [https://huggingface.co/Qwen/Qwen3.6-27B/raw/main/README.md](https://huggingface.co/Qwen/Qwen3.6-27B/raw/main/README.md)

## Nicht ausgewählte numerische Profile

Die folgende Quellenzuordnung bestand die Identitätsprüfung. Die Auswahlprüfung ist kein vollständiger numerischer Neuvergleich dieser unveränderten Profile.

- `mradermacher/gemma-4-19b-a4b-it-reap-i1@q4_k_m`: https://huggingface.co/0xSero/Gemma-4-19B (quantized chain)
- `unsloth/qwen3-coder-30b-a3b-instruct@q3_k_s`: https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/raw/main/README.md (artifact)
- `mradermacher/darwin-28b-coder-i1@q3_k_s`: https://huggingface.co/FINAL-Bench/Darwin-28B-Coder/raw/main/README.md (quantized chain)
- `empero-ai/qwen3.8-9b-distill@q8_0`: https://huggingface.co/empero-ai/qwen3.8-9b-distill/raw/main/README.md (quantized chain)
- `mudler/gemma-4-26b-a4b-it-apex@mini`: https://huggingface.co/google/gemma-4-26B-A4B-it (quantized chain)

## Verifikation und Grenzen

- Native Windows-PowerShell, vorhandenes Python 3.12.10; prozesslokales `LLM_PROVIDER=lmstudio` für Tests.
- 35 fokussierte Tests bestanden: `python -m pytest tests/test_sampling_identity.py tests/test_sampling_research.py -q`.
- Ruff für `src/sampling_research.py` und `src/registry_tool.py` bestanden; fokussiertes mypy für `src/sampling_research.py` bestanden.
- Vollständige Modellidentität, Artefakt-Repositories, öffentliche HF-Metadaten und Modellabschnitte in offiziellen Quellen wurden geprüft. Kein GPU-Benchmark wurde dafür ausgeführt.
- Nicht ausgewählte Registry-Felder und Einträge wurden nach dem erneuten Lesen semantisch gegen die gesicherte Baseline verglichen.
- Nicht erreichbare oder nicht ausreichend belegte Empfehlungen bleiben ausdrücklich offen. Unresolved entfernt frühere unbewiesene Zahlen; Kategorie-Defaults sind anschließend die explizite Laufzeit-Fallback-Policy.

## Abschließende Nachprüfung

Der integrierte Re-Review verschärfte zusätzlich die Zuordnung verschachtelter
Modellabschnitte: Ein exakter Parent-Abschnitt autorisiert keinen fremden
Sibling-/Finetune-Unterabschnitt. Modellnamen mit Punkt/Unterstrich werden dabei
symmetrisch normalisiert. Die 17 erneut bestätigten Profile wurden anschließend
aus ihren Quellen geprüft; kein Sampling-Block musste nochmals verändert werden.
HF-Cache-Repository-Referenzen stammen ebenfalls direkt aus der Artefakt-Evidenz
des `IdentityLink`, statt aus einer angenommenen physischen Parent-Verzeichnisform.
Fremde Artefakt-Publisher/Quants werden vor der Webrecherche abgewiesen.

Die finale Sampling-Suite besitzt 41 bestandene Tests. Der danach ausgeführte
technische Header-Sync änderte vier Nicht-Sampling-Felder in drei Registry-Einträgen;
die finale Registry-SHA256 lautet
`5a6aa5d4dd1d90b271ab55829e2576891ff2ec076b0572bed3f46e701e50c378`.
Details und offene lokale Bindungen stehen im
[Fix-/Re-Review-Bericht](Code-Review_registry_Fixes_2026-09-28.md).
