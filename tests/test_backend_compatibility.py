from __future__ import annotations

import json

from tools.backend_compatibility import (
    RequestSpec,
    build_payload,
    normalize_base_url,
    parse_sse_lines,
)


def test_normalize_base_url_adds_v1_once() -> None:
    assert normalize_base_url("http://127.0.0.1:1234") == "http://127.0.0.1:1234/v1"
    assert normalize_base_url("http://127.0.0.1:1234/v1/") == "http://127.0.0.1:1234/v1"


def test_build_payload_is_shared_and_json_mode_is_explicit() -> None:
    spec = RequestSpec("p", max_tokens=17, temperature=0.7, top_p=1.0, seed=9, response_format="json")
    payload = build_payload("model", spec, stream=True)
    assert payload["stream"] is True
    assert payload["max_tokens"] == 17
    assert payload["response_format"] == {"type": "json_object"}


def test_parse_sse_lines_preserves_reasoning_and_content() -> None:
    lines = [
        f"data: {json.dumps({'choices': [{'delta': {'reasoning_content': 'think '}}]})}\n".encode(),
        f"data: {json.dumps({'choices': [{'delta': {'content': 'answer'}}]})}\n".encode(),
        f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}\n".encode(),
        b"data: [DONE]\n",
    ]
    content, reasoning, finish, chunks = parse_sse_lines(lines)
    assert content == "answer"
    assert reasoning == "think "
    assert finish == "stop"
    assert chunks == 3


def test_parse_sse_lines_ignores_comments_and_malformed_data() -> None:
    content, reasoning, finish, chunks = parse_sse_lines(
        [b": keep-alive\n", b"data: not-json\n", b"data: [DONE]\n"]
    )
    assert (content, reasoning, finish, chunks) == ("", "", None, 0)
