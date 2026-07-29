# Gemma-4 Modellvarianten – vollständiger Bericht, Stand 13.07.2026

## 1. Beteiligte Varianten (9 Einträge in Registry)

| Variante                    | Publisher    | Quant(s)     | Arch          | Besonderheit                               |
|-----------------------------|--------------|--------------|---------------|--------------------------------------------|
| `gemma-4-12b`               | google       | Q8_0         | Gemma-4 (12B) | **Aus LMS verschwunden** (Chronik Z. 1892) |
| `gemma-4-12b-qat`           | google       | Q4_0         | Gemma-4 (12B) | QAT-Version                                |
| `gemma-4-19b-a4b-it-REAP`   | mradermacher | Q4_K_S       | Gemma-4 (19B) | 18 Experts, REAP-komprimiert               |
| `gemma-4-26b-a4b-it`        | unsloth      | IQ3_S        | Gemma-4 (26B) | Ursache HTTP-500-Konflikt                  |
| `gemma-4-26b-a4b-it-quat`   | mradermacher | Q4_0         | Gemma-4 (26B) | QAT-gewichtet                              |
| `gemma-4-26B-A4B-it-UD`     | unsloth      | IQ3_XXS+     | Gemma-4 (26B) | UD-Version                                 |
| `gemma-4-31B.i1`            | mradermacher |      –       | Gemma-4 (31B) | i1-Quant                                   |
| `gemma-4-e4b`               | google       |      –       | Gemma-4       | Embedding-Modell?                          |
| `google_gemma-4-26B-A4B-it` | bartowski    |Q3_K_S,IQ4_XS+| Gemma-4 (26B) | lm_eval=0%-Problem (kein HF-Eintrag)       |

---

## 2. Template-Chronologie (Zeitstrahl)

```
02.07.  12B MiniJinja-Template erstellt (gemma4_12b_template_minijinja.jinja)
04.07.  Alle 3 Gemma-Templates in doc-git/ abgelegt
        Template-Fix: <|turn|>system → <|turn>system (7 Tag-Korrekturen)
04.07.  thinking parametrisierbar: --thinking CLI-Flag, enable_thinking via extra_body
05.07.  model.yaml unter hub/models/google/gemma-4-26b-a4b-it/ erstellt
        → HTTP 500: doppelte Instanz derselben GGUF
05.07.  <|think|> aus System-Prompt entfernt (JSON-Config-Fix)
        enableThinking: false gesetzt
05.07.  model.yaml gelöscht (HTTP-500-Fix)
08.07.  Gemma-Templates per Google-Docs aktualisiert:
        - 26B: always-on <|think|> (supress ghost thought channels)
        - 19B/12B: empty thinking block
09.07.  Jinja-Template-Check: doc-git vs Config-eingebettet
        - 19B/26B: identisch ✅
        - 12B: Config hatte einfachere Version ohne enable_thinking/tools → aktualisiert
        Backup: template-config-backups_20260709/
11.07.  Gemma-Jinja ignoriert enable_thinking=False → System-Prompt-Override:
        "Do NOT use thinking or reasoning. Answer directly without <|channel>thought tags."
13.07.  Unser Blueprint-System: gemma_assistant/gemma_reasoning Blueprints
```

---

## 3. Template-Divergenz (KRITISCH)

**Drei Generationen von Jinja-Templates existieren parallel und sind NICHT deckungsgleich:**

### Generation 1: GGUF-eingebettet (Original)
- **Wo:** Im GGUF-File (tokenizer_config.json)
- **Variante:** IQ4_XS-Config hat 270-zeiliges Makro-Template mit Multimodal+Tools
- **LMS-Nutzung:** LMS fällt auf dieses Template zurück, wenn kein Hub-Jinja-Override und kein promptTemplate in der JSON-Config existiert

### Generation 2: Hub-Jinja-Override (`~/.lmstudio/hub/models/google/*.jinja`)
- **Wo:** 3 Dateien (12B in Unterordner, 19B+26B als flache Dateien)
- **26B hub:** `<|think|>` **gated** by `enable_thinking` (korrekt ✅)
- **26B hub:** KEIN `<|channel>thought` im Generation-Prompt (korrekt ✅)
- **LMS-Nutzung:** Überschreibt GGUF-eigenes Template WENN die Datei existiert

### Generation 3: doc-git-Kopien (`doc-git/Jinja-Chat-Templates/*.jinja`)
- **12B doc-git:** Hat `<|channel>thought` im Generation-Prompt (⚠️ veraltet)
- **19B doc-git:** `<|channel>thought` vorhanden (⚠️ veraltet, hub hat es nicht)
- **26B doc-git:** `<|think|>` **unconditional** (kein `if enable_thinking`), `<|channel>thought` vorhanden (⚠️ veraltet)

### Generation 4: `promptTemplate` in JSON-Configs (eingebettete Kopie)
- **Wo:** Im `operation.fields[]` der per-model JSON-Configs
- **Was:** LMS hat bei Config-Erstellung eine Kopie des damals aktiven Templates eingebettet
- **LMS-Nutzung:** UNKLAR – die Chronik (Z. 3808-3844) belegt, dass WIR diese Felder aktiv synchronisiert haben (Backup vom 09.07.)
- **IQ4_XS.json** → enthält das 270-Zeilen-Makro-Original aus dem GGUF
- **Q3_K_S.json** → enthält die doc-git-26b-Version (unconditional `<|think|>`)

---

## 4. Drei aktive Fehlerquellen

### ❌ Fehler 1: doc-git-Kopien ≠ Hub-Overrides

| Feature              | doc-git 26B                  | hub 26B                               | Auswirkung                                                    |
|----------------------|------------------------------|---------------------------------------|---------------------------------------------------------------|
| `<|think|>`          | **Unconditional** (immer an) | **Gated** (nur bei `enable_thinking`) | Bei Neuanlage einer Config aus doc-git → Thinking immer aktiv |
| `<|channel>thought>` | Vorhanden                    | **Fehlt**                             | doc-git unterdrückt Thought-Kanal bei non-thinking; hub nicht |

**Fix:** doc-git-Kopien mit hub-Versionen überschreiben.

### ❌ Fehler 2: Eingebettetes `promptTemplate` in Configs (Generation 4)

Jede JSON-Config hat ein eingebettetes Jinja-Template. Dessen Herkunft variiert:
- Configs, die VOR dem Hub-Override erstellt wurden → GGUF-Original (IQ4_XS: 270 Zeilen Makro)
- Configs, die NACH dem Hub-Override erstellt wurden → doc-git-Version (Q3_K_S: 91 Zeilen indented)
- Configs, die per Backup+Restore am 09.07. synchronisiert wurden → doc-git-Version

**LMS-Priorität (Vermutung nach Chronik-Analyse):**

```
JSON-Config.promptTemplate → Hub-Jinja-Override → GGUF-eingebettetes Template
```

Wenn LMS das `promptTemplate`-Feld respektiert (was die Chronik nahelegt, da wir es aktiv synchronisiert haben), dann 
**überschreibt das eingebettete Template aus der IQ4_XS-Config (270 Zeilen Makro) das Hub-Override (90 Zeilen) und das GGUF-Original**. 
Das bedeutet: Die IQ4_XS-Quant-Läufe nutzen ein komplett anderes Template als die Q3_K_S-Läufe.

### ❌ Fehler 3: 12B-Template-Situation

- `hub/models/google/gemma-4-12b/gemma4_12b_template_minijinja.jinja` (2.685 B, 79 Zeilen, KEIN `<|channel>thought`)
- `doc-git/Jinja-Chat-Templates/gemma4_12b_template_minijinja.jinja` (2.791 B, 83 Zeilen, MIT `<|channel>thought`)
- Kein separates `hub/models/google/gemma4-12b-template_minijinja.jinja` (die flache Datei existiert nicht)

Die hub-Version hat das `enable_thinking`-Gating und kein Thought-Channel. Die doc-git-Version hat beides. 
Divergenz seit dem 08.07.-Update (als die hub-Templates per Google-Docs aktualisiert wurden, die doc-git-Kopien aber nicht).

---

## 5. Empfohlene Aktionen

1. **doc-git-Kopien mit hub-Versionen ersetzen** – sind die autoritative Quelle
2. **`promptTemplate` in allen JSON-Configs entfernen** – damit LMS zwingend das Hub-Override nutzt. 
        Alternativ: alle embedded Templates auf den aktuellen hub-Stand aktualisieren
3. **`gemma-4-12b` aus Registry entfernen** (Modell existiert nicht mehr in LMS)
4. **12B flache Jinja-Datei** `hub/models/google/gemma4-12b-template_minijinja.jinja` erstellen (analog zu 19B/26B)