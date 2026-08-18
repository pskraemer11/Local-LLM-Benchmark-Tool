# Unsloth GGUF Workflow: gguf_dump.py, Jinja-Templates, llama.cpp-Tools

> Status: 2026-08-13 (C3, Planung.md)
> Ziel: Stand der drei Werkzeug-Themen für die lokale GGUF-Verwaltung dokumentieren.
> Quellen: llama.cpp GitHub/DeepWiki, Unsloth-Docs, lokale venv-Installation.

---

## 1. gguf_dump.py — Stand

**Verfügbar:** im venv `C:\Users\pskra\Python-Projekte\.venv` (Paket `gguf` **0.19.0**).
Scripts-Ordner: `C:\Users\pskra\Python-Projekte\.venv\Lib\site-packages\gguf\scripts\`:
`gguf_dump.py`, `gguf_convert_endian.py`, `gguf_editor_gui.py`, `gguf_hash.py`,
`gguf_new_metadata.py`, `gguf_set_metadata.py`.

**Hinweis:** Die System-Python (`C:\Users\pskra\AppData\Local\Programs\Python\Python312`)
hat `gguf` **nicht** installiert — nur das venv des übergeordneten Projekts. `registry_tool.py`
nutzt `from gguf import GGUFReader` (im venv-Pfad) für `_read_gguf_arch`.

**Aufruf (Metadaten):**
```powershell
& "C:\Users\pskra\Python-Projekte\.venv\Scripts\python.exe" `
  -m gguf.scripts.gguf_dump --no-tensors "<pfad>\modell.gguf"
```

**JSON (maschinenlesbar, inkl. Chat-Template):**
```powershell
& "...\python.exe" -m gguf.scripts.gguf_dump --no-tensors --json "<pfad>\modell.gguf" `
  | ConvertFrom-Json
```

**Chat-Template gezielt extrahieren (llama.cpp-Diskussion #19469):**
```bash
gguf_dump.py --no-tensors --json <MODEL.gguf> \
  | jq -r '.metadata["tokenizer.chat_template"].value'
```

**Weitere Optionen:** `--markdown` (menschenlesbare Tabellen inkl. Tensor-Gruppen),
`--data-offset`, `--data-alignment`. **GUI:** `gguf_editor_gui.py` (Qt) — GGUF-Metadaten
ansehen/bearbeiten/ergänzen, auch für lokale Dateien.

**Lokaler Bezug:** `registry_tool.py` liest GGUF-Header bereits selbst
(`_read_gguf_arch`: block_count, embedding_length, is_reasoning, context_length,
expert_count). `gguf_dump.py` ist die schnelle externe Voll-Inspktion (alle Keys,
Tokenizer, Template) — nützlich z.B. zum Vergleich GGUF-Template vs. Hub-Template.

---

## 2. Jinja-Templates

### Unsloth `chat_templates.py`
- Standardisierte Templates für Llama 3.1/3.2, Gemma 2/3/4, Mistral, Qwen 3, Phi-4
  (Dict `CHAT_TEMPLATES`; `get_chat_template()` setzt sie in den Tokenizer).
- **EOS-Synchronisation:** Template-EOS muss zu den physischen Spezialtokens des
  Vocab passen (`<|im_end|>` → eos_token + Token ggf. neu hinzugefügt).
- **`save_to_gguf`:** Beim GGUF-Export wird das Jinja-Template über
  `OLLAMA_TEMPLATES`/`MODEL_TO_OLLAMA_TEMPLATE_MAPPER` auf eine Ollama-Template-
  Zeichenkette gemappt und als `tokenizer.chat_template` in die GGUF-Metadaten
  geschrieben. `fix_sentencepiece_gguf` stellt sicher, dass custom Tokens auch
  physisch in `tokenizer.model` landen.

### llama.cpp
- **minja** = eigene C++-Jinja2-Engine; liest `tokenizer.chat_template` aus der GGUF.
- **Auto-Erkennung** bekannter Formate (`LLM_CHAT_TEMPLATE_*`, z.B. ChatML, Llama-3,
  Mistral-v3, Phi-3/4, Granite-4.1, DeepSeek-3) über Marker.
- **Autoparser/PEG:** generiert aus dem Template einen PEG-Parser, um Modell-Output
  (Content, Reasoning, Tool-Calls) zurück in strukturierte Messages zu parsen;
  GBNF-Grammatiken erzwingen gültiges JSON bei Tool-Calls.
- **`--jinja` in `llama-server`/`llama-cli`:** nutzt das eingebettete Template.
  **Bekannter Nebeneffekt (Unsloth-Hinweis):** bei unterstützten Tools hängt
  llama-server zusätzlich *"Respond in JSON format, either with tool_call ..."* an —
  kann bei Fine-Tunes stören; `--no-jinja` deaktiviert aber auch `tools`.
- **`--chat-template-file <file>`:** Template-Override (nützlich wenn GGUF-Template
  veraltet/inkompatibel). Offizielle Templates: `scripts/get_chat_template.py`
  (von HuggingFace, Beispielaufrufe in `models/templates/README.md`).

### Bezug zur lokalen Doku/Registry
- Lokale Jinja-Overrides: `doc-git/Jinja-Chat-Templates/` (z.B. `gpt-oss-20b_harmony.jinja`,
  `gemma4_12b_template_minijinja.jinja`, `phi-4_template_unsloth.jinja`).
- `Gemma 4 - Consolidated Model Hints`: 4 parallele Generations-Quellen
  (GGUF vs. Hub vs. doc-git vs. JSON-Config) → mögliche Divergenz; Hub-Jinja ist
  für Gemma-4 autoritativ (`~/.lmstudio/hub/models/google/*.jinja`).
- Gemma-4-`chat_template_kwargs`-Trick wirkt NICHT (Thinking hard-verdrahtet im
  GGUF-Jinja), siehe `thinking-config_en.md`.

---

## 3. llama.cpp-Tools (Auswahl)

| Tool/Script | Zweck |
|---|---|
| `llama-server` | OpenAI-kompatible Server; `--jinja`, `--chat-template-file`, `--parallel N`, `--ctx-size`, `--flash-attn` |
| `llama-cli` | CLI-Inferenz (Chat/Completion, `--jinja`, `--single-turn`) |
| `llama-gguf-hash` | GGUF-Hashes (identische Dateien erkennen) |
| `llama-gguf` / `llama-gguf-split` | GGUF-Info/Quants splitten |
| `llama-quantize` | Quantisierung |
| `test-chat-template` | JSON-Input durch `.jinja` rendern → inspizieren (Template-Validierung) |
| `test-jinja` | minja-Engine gegen Standard-Jinja2 testen |
| `gguf-py/scripts/*` | `gguf_dump.py`, `gguf_editor_gui.py`, `gguf_set_metadata.py`, `gguf_new_metadata.py`, `gguf_hash.py`, `gguf_convert_endian.py` |
| `scripts/get_chat_template.py` | Offizielles Chat-Template von HF holen (für `--chat-template-file`) |

**Function-Calling:** native Tool-Formate (Llama 3.1/3.3, Qwen 2.5/2.5-Coder,
Mistral-Nemo, DeepSeek-R1 …) oder generisches Format (Fallback) — `Chat format: Generic`
im Log; Template-Erkennung testbar mit `./build/bin/test-chat ../minja/build/tests/*.jinja`.

---

## Fazit für das Projekt

- **gguf_dump.py** (0.19.0) im venv einsatzbereit → Voll-Inspktion von GGUF-Metadaten
  und eingebetteten Chat-Templates ohne `registry_tool`-Umweg.
- **Jinja-Templates:** GGUF-`tokenizer.chat_template` ist die SSOT für llama.cpp;
  lokale Overrides in `doc-git/Jinja-Chat-Templates/` dokumentiert. Bei
  Template-Problemen: `test-chat-template` (llama.cpp) oder `gguf_dump --json` zur
  Extraktion nutzen.
- **llama.cpp-Tools:** für Ad-hoc-Inferenz/Verifikation eines einzelnen GGUF
  geeignet; für die Benchmark-Pipeline ist der Orchestrator heute provider-basiert
  (LM Studio, TabbyAPI, OpenAI-compatible / Unsloth, oder der runner-own
  `unsloth_server`-Prozess).
