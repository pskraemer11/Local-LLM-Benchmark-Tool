#!/usr/bin/env python3
"""
LM-Eval Proxy – translates OpenAI Chat Completions requests to LM Studio
Native API (/api/v1/chat) with reasoning='off' support.

Usage:
  python tools/lmeval_proxy.py                       # port 1235, upstream 127.0.0.1:1234
  python tools/lmeval_proxy.py --port 1236 --upstream localhost:4321

The proxy implements:
  GET  /v1/models             → pass-through to LM Studio
  POST /v1/chat/completions   → translate to native API with reasoning='off'

Then point lm_eval's base_url to http://localhost:1235/v1.
"""

import json
import os
import re
import sys
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from io import BytesIO

# ── Defaults ──
DEFAULT_PORT = 1235
DEFAULT_UPSTREAM = "http://127.0.0.1:1234"

# ── Helpers ──

def _upstream_url(upstream: str, path: str) -> str:
    u = upstream.rstrip("/")
    p = path.lstrip("/")
    return f"{u}/{p}"


def _proxy_upstream(upstream: str, path: str, headers: dict, body: bytes = None) -> tuple[int, dict, bytes]:
    """Forward a request to LM Studio and return (status, response_headers, body)."""
    url = _upstream_url(upstream, path)
    method = "POST" if body else "GET"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            resp_headers = dict(resp.headers)
            return resp.status, resp_headers, resp.read()
    except Exception as e:
        # Try to read error body
        try:
            if hasattr(e, "read"):
                err_body = e.read().decode("utf-8", errors="replace")[:500]
            else:
                err_body = str(e)
        except Exception:
            err_body = str(e)
        return 502, {"Content-Type": "text/plain"}, f"Proxy error: {err_body}".encode("utf-8")


# ── Response builders ──

def _build_openai_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:20]}"


def _build_openai_usage(prompt_tokens: int, completion_tokens: int, reasoning_tokens: int = 0) -> dict:
    d: dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if reasoning_tokens:
        d["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return d


def _extract_messages(openai_body: dict) -> tuple[str, str]:
    """Extract system_prompt and input from OpenAI messages array."""
    messages = openai_body.get("messages", [])
    system_parts = []
    input_parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            if content:
                input_parts.append(content)
        elif role == "assistant":
            # Some lm_eval tasks pass assistant messages too
            input_parts.append(f"Assistant: {content}" if content else "")
    system_prompt = "\n".join(system_parts) if system_parts else None
    user_input = "\n".join(input_parts) if input_parts else ""
    return system_prompt, user_input


def _translate_to_native(openai_body: dict, upstream: str) -> tuple[str, dict]:
    """Translate OpenAI Chat Completions body to native API body.
    
    Returns (native_url, native_body).
    """
    system_prompt, user_input = _extract_messages(openai_body)
    # Native API: /api/v1/chat
    native_url = _upstream_url(upstream, "/api/v1/chat")

    native_body = {
        "model": openai_body.get("model", "local-model"),
        "input": user_input,
        "temperature": openai_body.get("temperature", 0.0),
        "top_p": openai_body.get("top_p", 1.0),
        "max_output_tokens": openai_body.get("max_tokens", 512),
        "reasoning": "off",  # ← THE KEY FIX
    }

    # Optional: top_k
    top_k = openai_body.get("top_k")
    if top_k is not None and top_k > 0:
        native_body["top_k"] = top_k

    # Optional: min_p
    min_p = openai_body.get("min_p")
    if min_p is not None:
        native_body["min_p"] = min_p

    # System prompt (if present)
    if system_prompt:
        native_body["system_prompt"] = system_prompt

    # Stop tokens
    stop = openai_body.get("stop")
    if stop:
        if isinstance(stop, str):
            native_body["stop"] = [stop]
        elif isinstance(stop, list):
            native_body["stop"] = stop

    # Streaming support
    if openai_body.get("stream"):
        native_body["stream"] = True

    # Clean None values
    native_body = {k: v for k, v in native_body.items() if v is not None}
    return native_url, native_body


def _translate_native_response(native_data: dict, model_id: str, elapsed: float) -> dict:
    """Translate native API response to OpenAI Chat Completions format."""
    content = ""
    reasoning_content = ""
    output = native_data.get("output", [])
    for item in output:
        if item.get("type") == "message":
            text = item.get("content", "")
            # Check if content has reason/think tags
            stripped, thinks = _strip_think_tags(text)
            content += stripped
        elif item.get("type") == "reasoning":
            reasoning_content += item.get("content", "")

    stats = native_data.get("stats", {})
    prompt_tokens = stats.get("input_tokens", 0)
    completion_tokens = stats.get("total_output_tokens", 0)
    reasoning_tokens = stats.get("reasoning_output_tokens", 0) or len(reasoning_content.split())

    openai_response = {
        "id": _build_openai_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": _build_openai_usage(prompt_tokens, completion_tokens, reasoning_tokens),
        "system_fingerprint": model_id,
    }

    # Include reasoning content in separate field if present
    if reasoning_content:
        openai_response["choices"][0]["message"]["reasoning_content"] = reasoning_content

    return openai_response


def _strip_think_tags(text: str) -> tuple[str, int]:
    """Remove <think>...</think> tags and count their tokens."""
    think_count = 0
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    think_matches = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
    for m in think_matches:
        think_count += len(m.split())
    return stripped.strip(), think_count


# ── SSE helpers for streaming ──

def _translate_native_sse_to_openai(native_sse_line: str, model_id: str) -> str:
    """Translate a single native API SSE line to OpenAI format."""
    if not native_sse_line.startswith("data: "):
        return native_sse_line

    data_str = native_sse_line[6:].strip()
    if data_str == "[DONE]":
        return "data: [DONE]\n\n"

    try:
        native_chunk = json.loads(data_str)
    except json.JSONDecodeError:
        return native_sse_line

    item_type = native_chunk.get("type", "")
    if item_type != "message":
        return ""

    content = native_chunk.get("content", "")
    openai_chunk = {
        "id": _build_openai_id(),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": None,
            }
        ],
    }
    return f"data: {json.dumps(openai_chunk, ensure_ascii=False)}\n\n"


# ── HTTP Handler ──

class ProxyHandler(BaseHTTPRequestHandler):
    upstream = DEFAULT_UPSTREAM

    def log_message(self, format, *args):
        sys.stderr.write(f"[lmeval_proxy] {args[0]} {args[1]} {args[2]}\n")

    def _get_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length)
        return b""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/v1/models":
            status, resp_headers, body = _proxy_upstream(self.upstream, "/v1/models", dict(self.headers))
            self._send_response(status, resp_headers, body)
        elif path == "/health":
            self._send_json(200, {"status": "ok", "upstream": self.upstream})
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._get_body()

        if path == "/v1/chat/completions":
            self._handle_chat_completion(body)
        else:
            # Pass through to upstream
            status, resp_headers, resp_body = _proxy_upstream(self.upstream, path, dict(self.headers), body)
            self._send_response(status, resp_headers, resp_body)

    def _handle_chat_completion(self, raw_body: bytes):
        """Translate OpenAI /v1/chat/completions → native /api/v1/chat with reasoning='off'."""
        try:
            openai_body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return

        is_stream = openai_body.get("stream", False)
        model_id = openai_body.get("model", "local-model")

        # Build native API request
        native_url, native_body = _translate_to_native(openai_body, self.upstream)

        if is_stream:
            self._handle_streaming(native_url, native_body, model_id)
        else:
            self._handle_non_streaming(native_url, native_body, model_id)

    def _handle_non_streaming(self, native_url: str, native_body: dict, model_id: str):
        """Call native API and return translated response."""
        t0 = time.time()
        status, resp_headers, resp_body = _proxy_upstream(
            self.upstream, "/api/v1/chat", {"Content-Type": "application/json"},
            json.dumps(native_body).encode("utf-8")
        )
        elapsed = time.time() - t0

        if status != 200:
            self._send_json(502, {
                "error": f"Native API returned {status}",
                "detail": resp_body.decode("utf-8", errors="replace")[:500],
            })
            return

        try:
            native_data = json.loads(resp_body)
        except json.JSONDecodeError as e:
            self._send_json(502, {"error": f"Native API response parse error: {e}"})
            return

        openai_response = _translate_native_response(native_data, model_id, elapsed)
        self._send_json(200, openai_response)

    def _handle_streaming(self, native_url: str, native_body: dict, model_id: str):
        """Call native API with stream=True and translate SSE on the fly."""
        # Remove stream from body (native API SSE format differs from OpenAI)
        native_body.pop("stream", None)
        request_data = json.dumps(native_body).encode("utf-8")

        req = Request(native_url, data=request_data,
                      headers={"Content-Type": "application/json"},
                      method="POST")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            with urlopen(req, timeout=120) as native_resp:
                buffer = b""
                while True:
                    chunk = native_resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    # Split on double newlines (SSE delimiter)
                    while b"\n\n" in buffer:
                        line, buffer = buffer.split(b"\n\n", 1)
                        line_str = line.decode("utf-8", errors="replace")
                        translated = _translate_native_sse_to_openai(line_str, model_id)
                        if translated:
                            self.wfile.write(translated.encode("utf-8"))
                        self.wfile.flush()
                # Flush remaining buffer
                if buffer:
                    line_str = buffer.decode("utf-8", errors="replace")
                    translated = _translate_native_sse_to_openai(line_str, model_id)
                    if translated:
                        self.wfile.write(translated.encode("utf-8"))
                    self.wfile.flush()
        except Exception as e:
            error_chunk = {
                "id": _build_openai_id(),
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
            }
            self.wfile.write(f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
        finally:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_response(status, {"Content-Type": "application/json"}, body)

    def _send_response(self, status: int, headers: dict, body: bytes):
        self.send_response(status)
        content_type = headers.get("Content-Type", "application/json")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LM-Eval Proxy – translate OpenAI → Native API with reasoning='off'")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Proxy port (default: {DEFAULT_PORT})")
    parser.add_argument("--upstream", type=str, default=DEFAULT_UPSTREAM,
                        help=f"LM Studio server URL (default: {DEFAULT_UPSTREAM})")
    parser.add_argument("--bind", type=str, default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    args = parser.parse_args()

    ProxyHandler.upstream = args.upstream
    server = HTTPServer((args.bind, args.port), ProxyHandler)
    print(f"[lmeval_proxy] Listening on {args.bind}:{args.port}")
    print(f"[lmeval_proxy] Upstream LM Studio: {args.upstream}")
    print(f"[lmeval_proxy] Set base_url=http://{args.bind}:{args.port}/v1 in lm_eval config")
    print(f"[lmeval_proxy] Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[lmeval_proxy] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
