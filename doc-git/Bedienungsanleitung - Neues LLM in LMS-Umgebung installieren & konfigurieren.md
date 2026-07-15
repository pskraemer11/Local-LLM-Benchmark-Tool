## Bedienungsanleitung: Neues Modell installieren & konfigurieren

### Phase A – LM Studio macht automatisch

| Schritt                                                 | Was passiert                                                  | Wo                                                                                  |
|---------------------------------------------------------|---------------------------------------------------------------|-------------------------------------------------------------------------------------|
| ① GGUF importieren / `lms get`                          | Datei landet in `~/.lmstudio/models/{publisher}/{name}/`      |
| ② Erstes Laden des Modells                              | LMS erzeugt JSON-Config                                       | `~/.lmstudio/.internal/user-concrete-model-default-config/{publisher}/{dir}/*.json` |
| ③ Falls `hub/models/{pub}/{model}/model.yaml` existiert | Deren `config.operation.fields` fließen in JSON ein           | 
| ④ Falls `hub/models/{pub}/{model}/*.jinja` existiert    | Dessen Chat-Template überschreibt eingebettetes GGUF-Template | 

### Phase B – Manuelle Prüfung & unsere Pipeline

```bash
# 1. Prüfen: Ist das Modell in der Registry?
grep -l "model-name" doc-git/model_registry.yaml
```

**Fall 1: Modell ist bereits in der Registry**
→ `sync_model_configs.ps1 -FullSync` oder manuell:
```
python assemble_blueprint.py classify   # Klassifikation aktualisieren
python assemble_blueprint.py assemble   # Prompt in JSON schreiben
python assemble_blueprint.py validate   # Syntax-Check
```

**Fall 2: Neues Modell – Eintrag in Registry anlegen**

Am einfachsten: `sync_model_configs.ps1 -AutoAdd` erkennt das Modell via `lms ls` und trägt es automatisch ein. Manuell:

`doc-git/model_registry.yaml` – Eintrag einfügen (alphabetische Position):
```yaml
Mein-Neues-Modell-8B:
  publisher: "herausgeber"
  hf_url: "https://huggingface.co/herausgeber/Mein-Neues-Modell-8B"
  quants: [Q4_K_M, Q6_K]
  arch: "Llama Dense"
  k_cache: "q8_0"
  v_cache: "iq4_nl"
  offload: 1
  num_parallel: 1
  # notes, reasoning, capabilities, blueprint, truncation, context_length
  # werden von classify + registry_tool.py automatisch gesetzt
```

Dann:
```
python registry_tool.py sync           # Vollwartung: add + configs + sync-ctx + fill-ctx + fmt
python assemble_blueprint.py classify   # → reasoning, blueprint, truncation, capabilities gesetzt
python assemble_blueprint.py assemble   # → Prompt geschrieben
```

**Alle Infos, die classify + registry_tool.py automatisch ermitteln:**

| Feld           | Quelle                                                   | Beispiel                               |
|----------------|----------------------------------------------------------|----------------------------------------|
| `reasoning`    | Model-Name (Keywords: r1, thinking, qwq, reasoning, cot) | `Ministral-...-Reasoning` → `thinking` |
| `capabilities` | Model-Name (vl/vision/ocr, coder/code)                   | `qwen2.5-coder-14b` → `[coding, text]` |
| `blueprint`    | Aus reasoning + capabilities                             | `thinking` → `reasoning_assistant`     |
| `truncation`   | contextLength aus JSON-Config                            | `16384` (≥8192) → `medium`             |
| `offload`      | Default 1 (voller GPU-Offload) bei `add` / `fill-ctx`    | `1`                                    |
| `num_parallel` | 4 bei MoE-Architektur, sonst 1                           | `4` (MoE) / `1` (Dense)               |
| `context_length` | Aus JSON-Config via `sync-ctx`, Default 16384 via `fill-ctx` | `16384`                             |

### Phase C – Nur bei Spezialfällen

**Wann brauche ich ein Jinja-Template-Override?**

Nur wenn das Modell spezielle Chat-Template-Tokens hat, die nicht im GGUF eingebettet sind. Bisher einziger Fall: **Gemma-4** mit `<|think|>`-Token.

```bash
# Jinja-Override anlegen (falls nötig)
mkdir -p ~/.lmstudio/hub/models/{publisher}/{model-name}/
# Datei: {model-name}-template_minijinja.jinja
```

**Wann brauche ich eine model.yaml?**

| Use Case                                                | Beispiel aus Codebase                                                         | 
|---------------------------------------------------------|-------------------------------------------------------------------------------|
| `customFields` (UI-Dropdown, z.B. Reasoning-Effort)     | `openai/gpt-oss-20b/model.yaml` → `reasoningEffort`                           |
| `config.operation.fields` (Default-Temperatur, Parsing) | `essentialai/rnj-1/model.yaml` → `reasoning.parsing` mit `THOUGHT:/RESPONSE:` |
| `base` keys (mehrere Quants → ein Base-Model)           | `mistralai/codestral-22b-v0.1/model.yaml` → lmstudio-community-GGUF           |

⚠️ **Achtung (aus der Chronik, Zeile 2159):** `model.yaml` erzeugt eine **virtuelle Modell-Instanz** in LMS. Wenn dieselbe GGUF bereits als physische Instanz geladen ist → **HTTP-500-Konflikt** (zwei Instanzen auf selber Datei). Lösung: `model.yaml` nur für Modelle ohne physische GGUF, oder alternative Base-Keys nutzen.

### Phase D – Nach GGUF-Neuinstallation (gelöscht + neu geladen)

```
1. GGUF löschen           # Config bleibt erhalten
2. GGUF neu importieren    # Alte Config wird wiedererkannt
3. python registry_tool.py sync           # Configs + Registry abgleichen
4. python assemble_blueprint.py classify  # Klassifikation aktualisieren
5. python assemble_blueprint.py assemble  # Prompt neu schreiben
```
→ Fertig. Die alte `model.yaml` (falls vorhanden) wird beim `lms clone`/`lms get` aktualisiert, nicht beim manuellen Import.

### Kurz-Referenz (Cheat Sheet)

```bash
# Vollwartung (Registry + Configs)
python registry_tool.py sync

# Regisrty vs LMS vs Configs vergleichen
python registry_tool.py compare

# Standard-Fall (Modell bekannt)
python assemble_blueprint.py classify && assemble && validate

# Neues Modell – automatisch via sync_model_configs.ps1
.\sync_model_configs.ps1 -AutoAdd
# oder manuell:
# → registry.yaml editieren (publisher, arch, k/v_cache, offload, num_parallel eintragen)
python registry_tool.py sync
python assemble_blueprint.py classify  # füllt reasoning, capabilities, blueprint, truncation
python assemble_blueprint.py assemble

# Komplett-Sync inkl. Prompt-Assembly
.\sync_model_configs.ps1 -FullSync

# Nur Preview (ohne zu schreiben)
python assemble_blueprint.py preview

# Validierung nach Änderungen
python assemble_blueprint.py validate
```

