# Backend-Kompatibilitaet und SampleSize-1-Verifikation

Stand: 2026-09-25
Geltungsbereich: LM Studio 0.4.25.0, llama.cpp 0.4.1-dev Build 11081,
RTX 5060 Ti 16 GB, Windows 11.

Diese Verifikation trennt drei Aussagen:

1. Ist der Lebenszyklus technisch funktionsfaehig?
2. Sind Request, Template-/Reasoning-Verarbeitung und Streaming zwischen den
   Backends kompatibel?
3. Sind die beobachteten Benchmark-Scores eine belastbare Qualitaetsaussage?

## 1. Identischer Qwen-A/B-Lauf

Modellidentitaet und Datei waren auf beiden Backends identisch:

    Registry: lmstudio-community/qwen/qwen3.5-9b@q6_k
    GGUF:    D:\LLM-Modelle\models\lmstudio-community\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q6_K.gguf

Der Lauf wurde sequenziell ausgefuehrt; immer nur ein Backend war auf der GPU
aktiv. Beide Seiten erhielten denselben OpenAI-kompatiblen Request:

| Parameter               | Wert                                                                         |
| ----------------------- | ---------------------------------------------------------------------------- |
| Systemprompt            | You are a deterministic compatibility probe. Reply only to the user request. |
| Userprompt              | Respond with exactly one line containing COMPAT_OK.                          |
| Temperatur / Top-p      | 0.6 / 0.95      |
| Seed                    | 42              |
| Max tokens              | 1024            |
| Kontext / Parallelitaet | 32768 / 1       |
| Structured Output       | aus             |


| Backend   | Modus             | Ergebnis        | First event | Chunks | Zeit   |
| --------- | ----------------- | --------------- | ----------: | -----: | -----: |
| LM Studio | non-stream        | COMPAT_OK, stop |    -        |    -   | 4.80 s |
| LM Studio | OpenAI-SSE stream | COMPAT_OK, stop |  0.089 s    |   241  | 4.72 s |
| llama.cpp | non-stream        | COMPAT_OK, stop |    -        |    -   | 4.82 s |
| llama.cpp | OpenAI-SSE stream | COMPAT_OK, stop |  0.073 s    |   260  | 4.82 s |

Damit ist die fachlich relevante Finalantwort kompatibel. Reasoning-Text,
Reasoning-Laenge (LM Studio 876, llama.cpp 920 Zeichen) und Chunk-Anzahl sind
backendabhaengige Transport-/Parserdetails und keine Byte-Gleichheitskriterien.

Ein diagnostischer Vorlauf mit `max_tokens=256` lief bei llama.cpp in das
Reasoning-Limit: finish_reason=length und kein finaler Content.
Mit `max_tokens=1024` war die Antwort auf beiden Seiten vollstaendig.
Das ist eine Runtime-/Budgetregel fuer Thinking-Modelle und muss bei
Benchmarkprofilen explizit beruecksichtigt werden.

Der erste direkte llama.cpp-Start zeigte ausserdem einen echten Prozessgrenzenfehler:
Der Provider setzte `LLAMA_API_KEY` nur in seiner eigenen Umgebung, waehrend der
gestartete Prozess den Key nicht sah. Der Provider uebergibt die Umgebung jetzt
explizit an Popen; danach war der Endpoint authentifiziert und der Log enthielt
keine Meldung mehr, dass kein API-Key gesetzt sei.


## 2. GLM Structured Output unter LM Studio

Getestet wurde:

    Datei: D:\LLM-Modelle\models\unsloth\GLM-4.7-Flash-GGUF\GLM-4.7-Flash-Q3_K_S.gguf
    Identifier: glm47-live
    Kontext / Parallelitaet: 32768 / 1

Der Request verwendete `response_format.type=json_schema` mit dem Schema
classification, confidence und reason. Ergebnis:

    HTTP 200
    JSON parsebar: ja
    Schemafelder vollstaendig: ja
    classification: positive
    confidence: 1

Es trat kein Lazy-Grammar-Konflikt und kein Grammar-/HTTP-400-Fehler auf.
Die LM-Studio-Dokumentation beschreibt diesen Vertrag ueber
response_format und json_schema: [LM Studio Structured Output]
(https://lmstudio.ai/docs/developer/openai-compat/structured-output).
Die lokale GLM-Dokumentation bleibt zusaetzlich fuer das Reasoning-Parsing
verbindlich.

Die Schlussfolgerung ist eng begrenzt: GLM-4.7 Q3_K_S kann in dieser lokalen
LM-Studio-Konfiguration JSON-Schema-Ausgaben erzeugen.
**Das ersetzt weder einen Multi-Task-Qualitaetstest noch einen llama.cpp-Structured-Output-Test**.


## 3. GLM-Streamingvergleich

### OpenAI-kompatibler Stream

Gleicher System-/Userprompt, Sampling und Seed:

| Backend   | non-stream | stream  | First event | Chunks | Ergebnis            |
| --------- | ---------: | ------: | ----------: | -----: | ------------------- |
| LM Studio |   0.995 s  | 0.862 s |   0.043 s   |   30   | GLM_STREAM_OK, stop |
| llama.cpp |   1.031 s  | 0.627 s |   0.124 s   |   22   | GLM_STREAM_OK, stop |

Reasoning und finaler Content kamen in beiden Modi an. Chunkzahlen und
Reasoning-Laengen sind nicht identisch, der aggregierte finale Content und der
Abschlussstatus dagegen schon.
llama.cpp meldete beim Laden weiterhin die bekannte `special_eot_id`-/
`special_eom_id`-Warnung; sie verhinderte den Stream nicht.

### LM Studio nativer REST-Stream

Zusaetzlich wurde POST /api/v1/chat mit `stream=true` getestet.
Der Stream begann mit `chat.start` und endete mit `chat.end`.
Dazwischen wurden `prompt_processing.*`, `reasoning.start`, `mehrere reasoning.delta`,
`reasoning.end`, `message.start`, mehrere `message.delta` und `message.end`
beobachtet; es gab kein error-Ereignis und die aggregierte Nachricht war
`GLM_STREAM_OK`.

Das entspricht dem dokumentierten **LM-Studio**-SSE-Lifecycle:
[LM Studio Streaming Events](https://lmstudio.ai/docs/developer/rest/streaming-events)
und [LM Studio Chat REST API](https://lmstudio.ai/docs/developer/rest/chat).

Der **llama.cpp**-Vergleich verwendet dagegen den OpenAI-kompatiblen
POST /v1/chat/completions-Stream, bei dem `stream=true` SSE-Deltas liefert:
[llama.cpp API – Chat Completions und Structured Output](https://llama.app/docs/api#chat-completions).
Die beiden Streamvertraege sind semantisch vergleichbar,
aber **nicht ereignisnamenskompatibel.**


## 4. Fachliche Bewertung der SampleSize-1-Scores

Der Variant-B-Vertrag war seed=42, sample_size=1, je eine Aufgabe aus
DS1000, HumanEval+, ARC-Challenge und Agentic:

| Modell / Setup | DS1000 | HumanEval+ | ARC-Challenge | Agentic | Summe |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5 Q6_K / LM Studio | 0 | 1 | 1 | 1 | 3/4 |
| Gemma 4 12B Q6_K / externes MTP / llama.cpp | 0 | 1 | 0 | 1 | 2/4 |
| Muse Glimmer 30B IQ1_S / externer DFlash-Drafter / llama.cpp | 0 | 0 | 0 | 0 | 0/4 |

Diese Werte sind keine Qualitaetsrangliste. Bei n=1 bedeutet ein Treffer nur,
dass genau diese eine Aufgabe unter genau diesem Sampling-/Runtimezustand
bestanden wurde; ein Fehlschlag bedeutet nicht, dass die Modellfamilie die
Kategorie generell nicht beherrscht.

Besonders wichtig ist die Fehlerklassifikation der DS1000-Zeilen:

- Gemma: Harness error: failed: name b is not defined.
- Muse: No code generated.
- Qwen: No code generated bei leerer Antwort.

Diese drei DS1000-Nullen sind damit mindestens teilweise Pipeline-/Extraktions-
oder Harness-Signale und keine belastbaren Modellqualitaetsmessungen. Die
HumanEval-/ARC-/Agentic-Einzelwerte sind technische Indikatoren fuer den
jeweiligen Pfad, aber mit einem einzelnen Sample statistisch nicht stabil.

Fachliche Entscheidung: Der SampleSize-1-Lauf ist als Lifecycle-, Request-,
Template-, Structured-Output- und Streaming-Gate bestanden, nicht als
Qualitaetsbaseline. Vor dem pausierten SampleSize-5-Lauf muessen mindestens
die DS1000-Ausgabefehler getrennt behoben oder als Harnessfehler aus der
Qualitaetswertung ausgeschlossen werden. Erst danach ist eine Bewertung der
Modelle ueber mehrere Aufgaben und Kategorien zulaessig.

### DS1000-Follow-up: Qwen3.5 auf LM Studio und llama.cpp

Nach der Prompt-/Diagnoseaenderung wurde derselbe DS1000-Sample-1-Fall erneut
mit Seed 42 auf beiden Backends ausgefuehrt. Das Thinking-Modellprofil erhielt
`max_tokens=8192`; die effektive Coding-Einstellung meldete `thinking=False`.

| Backend | Ergebnis | Ausgabe / Harness | Laufzeit |
| --- | --- | --- | ---: |
| LM Studio | 0/1 | Stream lieferte keinen finalen Content; auch der Non-Streaming-Retry blieb reasoning-only und war abgeschnitten | 163.1 s |
| llama.cpp | 0/1 | Finaler Code kam an, scheiterte aber am Harness: erzeugte Matrixform `(5, 5)`, erwartet `(3, 5)` | 1.21 s |

Der llama.cpp-Lauf verwendete dieselbe lokale Qwen3.5-Q6_K-GGUF, Kontext 32768,
Parallelitaet 1 und dieselbe Benchmark-Aufgabe. Das LM-Studio-Ergebnis ist damit
nicht backenduebergreifend reproduziert: llama.cpp lieferte Code statt einer
reinen Reasoning-Ausgabe. Das grenzt den Fehler auf den LMS-/Provider-/Template-
Pfad ein, beweist aber noch nicht, dass genau das GUI-Feld die Ursache ist;
die Backends wenden optionale Reasoning-Parameter und gespeicherte Modell-
Defaults unterschiedlich an.

Die lokale LM-Studio-JSON-Config fuer dieses Qwen-Modell enthaelt einen
`systemPrompt` sowie Sampling- und Load-Felder, aber weder `reasoning_effort`,
`preserve-thinking` noch `reasoning-budget-message`. Die Benchmark baut ihre
Nachricht selbst und setzt bei diesem Coding-Aufruf
`chat_template_kwargs.enable_thinking=false`; ein freier Systemprompt ist
deshalb kein Ersatz fuer den Template-Schalter. Qwens Modellkarte beschreibt
`chat_template_kwargs: {"enable_thinking": false}` als den expliziten
Template-Moduswechsel:
[Qwen3.5-9B Modellkarte](https://huggingface.co/Qwen/Qwen3.5-9B).

Das GUI-Feld **Reasoning Budget Message** ist davon zu unterscheiden. Der
gleichnamige llama.cpp-Parameter injiziert eine Zeichenfolge in den laufenden
Thinking-Block, wenn dessen Tokenbudget erschoepft ist; er interpretiert den
Text nicht als JSON-Requestoptionen. Falls das LMS-Feld denselben Backend-
Parameter abbildet, ist `{"preserve-thinking": true, "reasoning_effort": "medium"}`
daher keine gueltige Art, diese Optionen zu konfigurieren, sondern allenfalls
ein literal injizierter Text. Fuer eine kontrollierte Wiederholung sollte das
Feld leer sein; Reasoning-Modus und -Aufwand muessen als separate API-/Template-
Optionen gesetzt werden. Siehe [llama.cpp Server-Optionen](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Codekorrektur: Ein Stream, der bereits das angeforderte Ausgabe-Limit erreicht
hat oder als abgeschnitten markiert ist und trotzdem keinen finalen Content
liefert, wird nicht nochmals mit demselben Prompt und Limit non-streaming
generiert. So wird der in diesem Lauf beobachtete doppelte 8192-Token-Aufwand
vermieden; ein leerer Reasoning-only-Output bleibt diagnostisch als solcher
erhalten. Ein Retry bleibt nur fuer einen vorzeitig beendeten, nicht
abgeschnittenen Stream vorgesehen, bei dem ein Transport-/Parserverlust noch
plausibel ist. Der falsche 5x5-Matrixoutput unter llama.cpp bleibt ein echter
Sample-Fehlschlag und kein DS1000-Extraktions- oder Harnessfehler.

## Reproduzierbare Laufartefakte

Die Rohdaten liegen im lokalen, ignorierten Verzeichnis ergebnisse:

- backend-ab-qwen-lmstudio-1024-20260925.json
- backend-ab-qwen-llama-deepseek-1024-20260925.json
- glm-lmstudio-structured-output-20260925.json
- glm-stream-lmstudio-openai-20260925.json
- glm-stream-lmstudio-native-20260925.json
- glm-stream-llama-20260925.json
- modell_20260925_100126_qwen_qwen3.5-9b@q6_k.csv
- modell_20260925_093152_unsloth_gemma-4-12b-it@q6_k.csv
- modell_20260925_094728_kookiesxy_muse-glimmer-30b-ternary-quants@iq1_s.csv
