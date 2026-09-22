# Z.AI/GLM-Modelle

Diese Datei bündelt die projektbezogenen Hinweise zu den lokal getesteten
GLM-Modellen. Die technische Beschreibung für Structured Output und die
historischen API-Beobachtungen steht in
`GLM 4.5 - 4.7_Structured Output_en.md`.

## Quellen

- [GLM-4.7 Einstellungen](https://z.ai/blog/glm-4.7)
- [GLM-4.6V](https://z.ai/blog/glm-4.6v)
- [Z.AI Thinking Mode](https://docs.z.ai/guides/capabilities/thinking-mode)
- [Z.AI Deep Thinking](https://docs.z.ai/guides/capabilities/thinking)
- [Z.AI Structured Output](https://docs.z.ai/guides/capabilities/struct-output)
- [Unsloth: GLM-4.6 lokal ausführen](https://unsloth.ai/docs/models/tutorials/glm-4.6-how-to-run-locally)
- [Unsloth: GLM-4.7 Flash](https://unsloth.ai/docs/models/tutorials/glm-4.7-flash)

Die folgenden Links bleiben als weiterführende Hintergrundquellen erhalten:

- <https://arxiv.org/html/2602.15763v2> (GLM-5, nicht lokal verwendet)
- <https://arxiv.org/pdf/2602.15763v2> (GLM-5, nicht lokal verwendet)
- <https://gist.github.com/apnea/e9dd7a650bdc3300375fffc54592f48d>
- <https://discord.com/channels/1391832426048651334/1448472481513082961/threads/1503851170584858624>
- <https://discord.com/channels/1391832426048651334/1448472481513082961/threads/1452900621085708412>

## Projektstatus am 22.09.2026

Die direkte llama.cpp-Migration verwendet die CUDA-Installation
`C:\Program Files\llama.cpp\llama-server.exe`. Die llama-GUI und der
WindowsApps-Wrapper `llama.exe` sind davon getrennt und bilden nicht den
Benchmark-Backendpfad. Der Provider übergibt eine konkret aufgelöste GGUF-
Datei an den Server; die Anzeige eines Modells in der GUI ist keine
Zulässigkeitsprüfung für Benchmarks.

Die beiden folgenden Modellfamilien werden getrennt behandelt:

| Familie                              | GGUF-Architektur | Benchmark-Regel                                                                                       |
| ------------------------------------ | ---------------- | ----------------------------------------------------------------------------------------------------- |
| GLM-4.7 Flash und GLM-4.7 Flash REAP | `deepseek2`      | `glm_reasoning_coding`, nicht gestreamte Vergleichstests, explizite Behandlung von `reasoning-format` |
| GLM-4.6V                             | `glm4`           | eigener Text-/Vision-Pfad; keine automatische Übernahme der GLM-4.7-Ausnahmen                         |

Für die drei GLM-4.7-Registry-Einträge ist derzeit
`reasoning_format: deepseek` hinterlegt. Dadurch wird das Denken in
`message.reasoning_content` abgelegt und der finale Inhalt bleibt im normalen
Content-Kanal. `auto`, `none`, `deepseek` und `deepseek-legacy` bleiben
diagnostische Varianten. Sie dürfen nicht ohne Ergebnisvergleich vertauscht
werden.

## config.ini, Preset und Registry

llama.cpp unterscheidet globale Defaults von einem modellbezogenen Preset.
Unter Windows liegt die automatische Benutzerkonfiguration bei:

```text
%APPDATA%\llama.cpp\config.ini
C:\Users\<user>\AppData\Roaming\llama.cpp\config.ini
```

Diese `config.ini` ist für hardwareweite Defaults geeignet, beispielsweise
eine konservative Kontextbasis oder allgemeine Serveroptionen. Das
projektbezogene Router-Preset liegt dagegen explizit unter:

```text
C:\Users\<user>\.config\llama.cpp\preset.ini
```

Es wird über `--models-preset` oder `LLAMA_ARG_MODELS_PRESET` aktiviert. Die
Priorität lautet:

```text
eingebaute Defaults
  -> config.ini
  -> LLAMA_ARG_* Umgebungsvariablen
  -> Preset [*]
  -> Preset [Modell]
  -> explizite CLI-Argumente
  -> API-Request-Parameter
```

Bei einem normalen Einzelaufruf ohne Router entfallen die Preset-Ebenen. Ein
benannter Preset-Abschnitt überschreibt `[*]`; explizite äußere CLI-Argumente
haben die höchste Priorität. Sampling, Structured Output, Seed, Stop-Bedingung
und `reasoning-format` bleiben Modell-/Benchmark-Policy bzw. Request-Ebene
und gehören nicht in einen allgemeinen Hardware-Default.

Die Registry `doc-git\model_registry.yaml` bleibt die Single Source of Truth
für Modellidentität, GGUF-Zuordnung, Kontext/KV-Policy, Templates,
Reasoning-Verhalten und Sampling-Evidenz. Das llama.cpp-Preset ist ein daraus
abgeleitetes Laufzeitartefakt. Es wird erzeugt oder aktualisiert mit:

```powershell
py -3.12 .\src\registry_tool.py export-llama-preset "C:\Users\<user>\.config\llama.cpp\preset.ini" --merge-existing
```

Vorhandene benutzerdefinierte Abschnitte bleiben beim Mergen erhalten. Die
aus der Registry generierten Abschnitte sollten nicht als primärer Pflegeweg
manuell verändert werden. Beim derzeit installierten llama.cpp-Build wird
`mmap` zwar als CLI-Option akzeptiert, aber im Models-Preset abgewiesen; es
steht deshalb momentan nicht im generierten globalen Abschnitt.

## GLM-Sampling nach Benchmarkkategorie

Die [offiziellen GLM-4.7-Fußnoten](https://z.ai/blog/glm-4.7) unterscheiden
folgende Einstellungen:

| Kategorie                                  | Temperatur | Top-p           | Status im Projekt                                                          |
| ------------------------------------------ | ---------: | --------------: | -------------------------------------------------------------------------- |
| Wissen / Standardaufgaben                  | 1.0        | 0.95            | direkt dokumentierter Default                                              |
| Coding, Terminal Bench, SWE-bench Verified | 0.7        | 1.0             | direkt dokumentierte Coding-Einstellung                                    |
| Math                                       | 0.7        | 1.0             | aus Coding abgeleitet, nicht als eigene Z.AI-Math-Angabe behauptet         |
| Agentic / τ²-Bench                         | 0          | nicht angegeben | Temperatur direkt belegt; `top_p` wird nicht als Herstellerangabe erfunden |

`sampling_research.py` erkennt inzwischen konkrete Namen wie Terminal Bench,
SWE-bench und τ²-Bench, auch wenn die Herstellerseite nicht die internen
Projektkategorien verwendet. Unvollständige Profile bleiben erhalten. Eine
Math-Einstellung wird als `derived_from: coding` markiert, wenn nur die
Coding-Evidenz vorliegt. Bei konflikthaften REAP-Quellen wird dagegen keine
scheinbar sichere Einstellung automatisch übernommen.

Das Tokenbudget ist unabhängig von der Temperatur. Für den aktuellen
Reasoning-Blueprint sind 8192 Tokens als Benchmark-Responsebudget und 4096
Tokens als separates LM-Studio-Reasoningbudget vorgesehen. Die Werte sind
konfigurierbar und dürfen nicht pauschal auf 1024 Tokens reduziert werden.

## Structured Output und typische Warnungen

Für LM Studio bleibt `json_schema` der getestete OpenAI-kompatible
Structured-Output-Vertrag. Beim direkten llama.cpp-Pfad wird Structured Output
nicht global erzwungen. Ein explizites GLM-Profil kann
`response_format={"type":"json_object"}` verwenden; bei
`reasoning-format none` wird die JSON-Grammatik nicht gleichzeitig erzwungen,
weil die Gedanken sonst durch dieselbe Grammatik laufen können.

Die Warnungen

```text
special_eot_id is not in special_eog_ids
special_eom_id is not in special_eog_ids
```

stammen aus den Tokenizer-/End-of-Generation-Metadaten des GGUF. Sie sind
allein kein Request-Fehler. Relevant werden sie erst bei falschem Abbruch,
zu frühem Ende oder ausgeschöpftem Budget. Auch die Meldung zur aktivierten
Reasoning-Preservierung beschreibt zunächst nur Template-/Runtime-Verhalten;
für die Bewertung müssen finaler Content, Reasoning-Kanal, Stop-Grund und
Tokenverbrauch gemeinsam geprüft werden.
