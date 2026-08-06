"""Wrapper for tool_eval_bench (Agentic pipeline).

LM Studio rejects requests that combine ``response_format`` (structured
output / json_schema) with ``tools`` in the same payload:

    Cannot combine structured output constraints with lazy grammar

tool_eval_bench's orchestrator already avoids this on the FIRST tool turn,
but re-applies ``response_format`` on later turns while ``tools`` are still
present -> HTTP 400 -> degraded Agentic scores (observed 2026-08-03 with
deepseek-coder-33b-instruct@Q3_K_S).

This wrapper patches the adapter so the combination never reaches the
server, then auto-detects the known Channel-Error and marks it for the
launcher via a [CHANNEL-ERROR] line (analogous to custom_benchmark.py).
"""

from __future__ import annotations

import sys
from typing import Any

from tool_eval_bench.adapters import openai_compat

_ORIGINAL_CHAT_COMPLETION = openai_compat.OpenAICompatibleAdapter.chat_completion


async def _patched_chat_completion(self: Any, **kwargs: Any) -> Any:
    tools = kwargs.get("tools")
    response_format = kwargs.get("response_format")
    if response_format and tools:
        print(
            "[CHANNEL-ERROR] response_format + tools kombiniert – "
            "structured output verworfen (llama.cpp lazy-grammar-Konflikt)",
            file=sys.stderr,
        )
        kwargs["response_format"] = None
    return await _ORIGINAL_CHAT_COMPLETION(self, **kwargs)


openai_compat.OpenAICompatibleAdapter.chat_completion = _patched_chat_completion

from tool_eval_bench.cli.bench import main

if __name__ == "__main__":
    main()