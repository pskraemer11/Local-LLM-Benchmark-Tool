# Granite-Modelle – Konsolidierter Analysebericht, Stand 13.07.2026

**Auftrag/Prompt:
Wiederhole diese Recherche (vorher zu Gemma-4) zu Systemprompts, Chat-Templates, Config- und yaml-Dateien anhand des Chatverlauf aus 
"C:\Users\pskra\Python-Projekte\Benchmarks\Doku-intern\Konsolidierte_Compaction-Chronik_20260615-20260713.md" für die Granite-Modelle.  
Gleiche die Daten aus den drei ~\.lmstudio Ordnern für .\models, .\hub und .internal\user-concrete-model-default-config sowie 
die Dateien im doc-git Ordner ab mit den Einträgen in model_registry.yaml.

Analysiere die Zusammenhänge, und erstelle einen konsolidierten zusammenfassenden Bericht.  
Nehme auch hier die Modelkarten von HuggingFace zur Unterstützung bei Klärung offener Punkte dazu.

## 1. Übersicht Registry-Einträge (7 Einträge)

| Registry-Name               | Publisher                 | Arch        | Template                            | Blueprint      |Capabilities(Ist)|Capabilities (HF-Soll)|
|-----------------------------|---------------------------|-------------|-------------------------------------|----------------|-----------------|----------------------|
| `granite-4.0-h-tiny`        | ibm-granite               | Granite-4.0 | `granite-4.0-h-tiny_template.jinja` | `default_chat` | text            | **coding** fehlt     |
| `granite-4.0-h-tiny-UD`     | unsloth                   | Granite-4.0 | `granite-4.0-h-tiny_template.jinja` | `default_chat` | text            | **coding** fehlt     |
| `granite-4.1-8b`            |ibm-granite,lms-co.,unsloth| Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text            | **coding** fehlt     |
| `granite-4.1-8b-UD`         | unsloth                   | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text            | **coding** fehlt     |
| `granite-4.1-30b`           | ibm-granite, mradermacher | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text            | **coding** fehlt     |
| `granite-4.1-30b-i1`        | ibm-granite, mradermacher | Granite-4.1 | `granite-4.1-30b_template.jinja`    | `default_chat` | text            | **coding** fehlt     |

---

## 2. Abgleich mit HuggingFace Model Cards

### Granite-4.1-30b / Granite-4.1-8b
- **Laut HF**: Decoder-only dense Transformer, GQA/RoPE/SwiGLU. 30B (64 Layer) / 8B (40 Layer). 131K Context. 
- **Tool Calling, Coding, Instruction Following, RAG, FIM, JSON Output, multilingual (12 Sprachen)**. 
- **Chat-Template**: `<\|start_of_role\|>` / `<\|end_of_role\|>` / `<\|end_of_text\|>`.
- **In Registry**: `arch: Granite-4.1` ✅; `capabilities: [text]` ⚠️ **coding fehlt**; `blueprint: default_chat` ⚠️ sollte eher coding_agent oder ein granite-spezifischer Blueprint sein.

### Granite-4.0-h-tiny
- Laut HF: **MoE** Hybrid **Mamba-2**/Transformer (9:1). **64 total experts, 6 active, 1 shared**. 7B total / 1B active. 128K Context. NoPE. 
- **Tool Calling, Coding, Instruction Following, RAG, FIM, JSON, multilingual**. Chat-Template identisch.
- **In Registry**: `arch: Granite-4.0` ✅; `experts: 24` ❌ **sollte 64 sein**; `capabilities: [text]` ⚠️ **coding fehlt**; `notes:` sagt "24 Experts" ❌


---

## 3. System-Prompt-Qualität (3 Bugs gefunden)

### Bug A: Falscher Modellname in JSON-Configs
Mehrere Configs haben den **falschen Modellnamen** im System-Prompt – ein Matching-Problem im Assemble-Script (Publisher-Overwrite / normalize_match):

| Config-Datei unter                                    | System-Prompt sagt (falsch)                                          | Sollte sein                              |
|-------------------------------------------------------|----------------------------------------------------------------------|------------------------------------------|
| `ibm-granite/...granite-4.0-h-tiny-Q8_0.gguf.json`    | `You are **granite-4.0-h-tiny-UD** ... by **unsloth**`               | `granite-4.0-h-tiny` by `ibm-granite`    |
| `ibm-granite/...granite-4.1-30b-Q3_K_S.gguf.json`     | `You are **granite-4.1-30b-i1** ... by **ibm-granite/mradermacher**` | `granite-4.1-30b` by `ibm-granite`       |
| `ibm-granite/...granite-4.1-8b-Q8_0.gguf.json`        | `You are **granite-4.1-8b-UD** ... by **unsloth**`                   | `granite-4.1-8b` by `ibm-granite`        |
| `lmstudio-community/...granite-4.1-8b-Q8_0.gguf.json` | `You are **granite-4.1-8b-UD** ... by **unsloth**`                   | `granite-4.1-8b` by `lmstudio-community` |

**Ursache**: Der `normalize_model_name()`-Match ist zu weit – "granite-4.0-h-tiny" matched auch "granite-4.0-h-tiny-UD", und der erste Treffer gewinnt.

### Bug B: `granite-20b-code-instruct` ohne `arch`
System-Prompt: *"a **Unknown** model"* ⚠️. `arch`-Feld fehlt im Registry-Eintrag.

### Bug C: Kein System-Prompt in `lmstudio-community/granite-4.1-8b-Q6_K.gguf.json`
Diese Config hat ein leeres `operation.fields`-Array – gar kein System-Prompt geschrieben.

---

## 4. Chat-Template-Situation

### Jinja-Templates in `doc-git/Jinja-Chat-Templates/`:
- `granite-4.1-30b_template.jinja` (71 Zeilen) ✅ – korrekt
- `granite-4.0-h-tiny_template.jinja` (72 Zeilen) ✅ – korrekt (minimaler Unterschied: Kommentar + andere Bedingung in Zeile 45)

### promptTemplate in JSON-Configs:
| Publisher    | Config                   | promptTemplate                         | Status                  |
|--------------|--------------------------|----------------------------------------|-------------------------|
| ibm-granite  | 4.0-h-tiny Q8_0          | ✅ eingebettet (3037 chars, korrekt)   | **Noch nicht entfernt** |
| ibm-granite  | 4.1-30b Q3_K_S           | ✅ eingebettet (2925 chars, korrekt)   | **Noch nicht entfernt** |
| ibm-granite  | 4.1-8b Q8_0              | ✅ eingebettet (2925 chars, korrekt)   | **Noch nicht entfernt** |
| mradermacher | 4.1-30b-i1 Q3_K_S        | ✅ eingebettet (2925 chars, korrekt)   | **Noch nicht entfernt** |
| bartowski    | 20b-code-instruct Q5_K_S | ❌ keins                               |       ✅               |
| unsloth      | 4.0-h-tiny-UD Q8_K_XL    | ❌ keins                               |       ✅               |
| unsloth      | 4.1-8b(-UD) Q8/Q6        | ❌ keins                               |       ✅               |
| lmstudio-community | 4.1-8b Q6/Q8       | ❌ keins                               |       ✅               |

### Hub-Jinja-Overrides (`hub/models/`):
**Keine einzige Granite-Jinja-Datei** in `hub/models/` gefunden. Anders als bei Gemma-4 existieren keine Hub-Overrides. LMS fällt bei fehlendem `promptTemplate` direkt auf das GGUF-eingebettete Template zurück.

---

## 5. Blueprint-Angemessenheit

Alle Granite-4.x-Modelle nutzen `default_chat` (3 Textbausteine: safety + output_style). Die HF-Karten belegen jedoch **deutlich mehr Fähigkeiten**:
- Tool Calling (Function Calling)
- Coding (Code-Generierung, -Completion, -Debugging)
- RAG / lange Kontexte (128K-131K)
- Instruction Following
- Multilingual (12 Sprachen)
- JSON Output / Structured Output

Der `default_chat`-Blueprint bildet diese Spezialfähigkeiten nicht ab. **Empfehlung**: Dedizierten `granite_chat`-Blueprint erstellen (analog zu `gemma_assistant`) mit:
- `coding` in capabilities (alle Granite-Modelle)
- Einem `granite_capabilities`-Modul (Function Calling, Coding, RAG, long context, multilingual)

---

## 6. Weitere Auffälligkeiten

### Kontextlänge
- `granite-4.0-h-tiny Q8_0`: **1.048.576** (1M!) in JSON-Config → weit über HF-Spec (128K). Vermutlich LMS-Default, nie gesetzt.
- `granite-4.1-30b Q3_K_S`: Nicht in den gelisteten Config-Feldern – kein contextLength gesetzt?
- HF gibt 128K (4.0) bzw. 131K (4.1) an.

### `granite-20b-code-instruct` ist deprecated
Laut HF: "⚠️ **DEPRECATED** – not recommended for new projects." Sollte in Registry mit einem Hinweis versehen oder entfernt werden.

---

## 7. Empfohlene Aktionen

| # | Aktion | Priority |
|---|---|---|
| 1 | `arch: Granite-20b-Code` zu `granite-20b-code-instruct` in Registry hinzufügen                                | 🔴 High   |
| 2 | `coding` zu `capabilities` aller Granite-4.x-Modelle hinzufügen (über `classify_capabilities()` oder manuell) | 🔴 High   |
| 3 | Bugfix: `normalize_model_name()`-Match so korrigieren, dass "granite-4.0-h-tiny" nicht                        | 🔴 High   |
            "granite-4.0-h-tiny-UD" matcht (exakter Match oder Suffix-Abgleich)                                     |           |
| 4 | `experts: 64` für `granite-4.0-h-tiny` korrigieren (HF: 64 total / 6 active)                                  | 🟡 Medium |
| 5 | `promptTemplate` aus den 4 verbliebenen ibm-granite/mradermacher Configs entfernen                            | 🟡 Medium |
            (oder durch Hub-Override ersetzen)
| 6 | Dedizierten `granite_chat`-Blueprint + `granite_capabilities`-Modul erstellen                                 | 🟡 Medium |
| 7 | `granite-20b-code-instruct` mit `deprecated: true` markieren                                                  | 🟢 Low    |
| 8 | Kontextlängen in Configs auf HF-Werte setzen (128K / 131K)                                                    | 🟢 Low    |
| 9 | `lmstudio-community/granite-4.1-8b-Q6_K.gguf.json` ohne System-Prompt neu assemblen                           | 🟢 Low    |

Soll ich die Aktionen ausführen?