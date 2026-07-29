# Qwen3.6 / REAP: Native-API-Fix (Stop-Tokens + Reasoning)

## Problem
Qwen3.6 27B und Qwen3.6 28B REAP liefen in v13 schlechter als vorher.

## Root Cause
Alle Qwen3.6-Modelle haben in `benchmark_config.py` den Override `enable_thinking: False`. Seit v13 führt das zur Route über **`_generate_answer_native()`** (LM Studio Native API `/api/v1/chat`) statt der OpenAI-kompatiblen API (`/v1/chat/completions`). Die Native API hatte drei Defizite:

### 1. Keine Stop-Tokens ❌
`_generate_answer_native()` akzeptierte/sendete keinen `stop`-Parameter. Qwen-Modelle benötigen `<|im_end|>` als Stop-Token, sonst generieren sie weit über die Code-Grenzen hinaus → verschwendetes Token-Budget, niedrige Scores.

**Fix (24.07.2026):**
- `_generate_answer_native()` um `stop: Optional[list[str]]` erweitert
- Body baut `stop`-Feld wenn `stop` gesetzt
- Fallback: Falls Native API `stop` nicht unterstützt → Retry ohne `stop`

### 2. `reasoning: "off"` nur für Thinking-Modelle ❌
`reasoning: "off"` wurde nur gesetzt wenn `_model_supports_reasoning()` → True (d.h. `reasoning: thinking` im Registry). REAP-Modelle haben `reasoning: instruct` → kein `reasoning: "off"` → Thinking blieb eingeschaltet → Token-Budget aufgebraucht.

**Fix:** `reasoning: "off"` wird jetzt **immer** gesetzt, da die Native-API-Route nur eingeschlagen wird wenn `enable_thinking=False` ist. Der bestehende Fallback (Retry ohne reasoning) fängt Modelle ab, die den Parameter nicht unterstützen.

### 3. Kein Fallback für Stop-Token-Fehler ❌
Die Native-API-Retry-Logik behandelte nur `reasoning`-Fehler, nicht `stop`-Fehler.

**Fix:** Neue Hilfsfunktion `_retry_native()` extrahiert. Retry-Kette: stop → reasoning.

## Geänderte Datei
`custom_benchmark.py`:
- `_retry_native()` – neue Hilfsfunktion (Z. 760)
- `_generate_answer_native()` – `stop`-Parameter + `reasoning: "off"` immer (Z. 789)
- `generate_answer()` – `stop=stop` an Native API übergeben (Z. 720)

Siehe auch: `GPT-OSS-20b_Harmony-Template-Injection.md` (top_k=0 Fix) – ähnliche API-Problematik.
