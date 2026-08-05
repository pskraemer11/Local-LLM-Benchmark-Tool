#!/usr/bin/env python3
"""
LM-Eval Proxy – forwards OpenAI Chat Completions requests directly to
an OpenAI-compatible endpoint (e.g. LM Studio /v1/chat/completions).

Usage:
  python tools/lmeval_proxy.py                       # port 1235, upstream 127.0.0.1:1234
  python tools/lmeval_proxy.py --port 1236 --upstream localhost:4321

The proxy implements:
  GET  /v1/models             → pass-through
  POST /v1/chat/completions   → pass-through (no translation)

Then point lm_eval's base_url to http://localhost:1235/v1.
"""

import json
import os
import sys
import time
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse

# ── Defaults ──
DEFAULT_PORT = 1235
DEFAULT_UPSTREAM = os.environ.get("LLM_API_BASE", "http://127.0.0.1:1234").replace("/v1", "")

# ── Helpers ──

def _upstream_url(upstream: str, path: str) -> str:
    u = upstream.rstrip("/")
    p = path.lstrip("/")
    return f"{u}/{p}"


# Longer timeout for API calls (MATH-500 needs up to 120s per request)
API_TIMEOUT = 900

def _proxy_upstream(upstream: str, path: str, headers: dict, body: bytes = None) -> tuple[int, dict, bytes]:
    """Forward a request to the upstream server and return (status, response_headers, body)."""
    url = _upstream_url(upstream, path)
    method = "POST" if body else "GET"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=API_TIMEOUT) as resp:
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


# ── HTTP Handler ──

class ProxyHandler(BaseHTTPRequestHandler):
    upstream = DEFAULT_UPSTREAM

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[lmeval_proxy] {args[0]} {args[1]} {args[2]}\n")

    def _get_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length)
        return b""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/v1/models":
            status, resp_headers, body = _proxy_upstream(self.upstream, "/v1/models", dict(self.headers))
            self._send_response(status, resp_headers, body)
        elif path == "/health":
            self._send_json(200, {"status": "ok", "upstream": self.upstream})
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._get_body()

        if path == "/v1/chat/completions":
            self._handle_chat_completion(body)
        else:
            # Pass through to upstream
            status, resp_headers, resp_body = _proxy_upstream(self.upstream, path, dict(self.headers), body)
            self._send_response(status, resp_headers, resp_body)

    def _handle_chat_completion(self, raw_body: bytes) -> None:
        """Forward /v1/chat/completions directly to upstream (no translation)."""
        try:
            openai_body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return

        is_stream = openai_body.get("stream", False)

        if is_stream:
            self._handle_streaming(openai_body)
        else:
            self._handle_non_streaming(openai_body)

    def _handle_non_streaming(self, openai_body: dict) -> None:
        """Forward request and return response directly."""
        request_data = json.dumps(openai_body).encode("utf-8")
        status, resp_headers, resp_body = _proxy_upstream(
            self.upstream, "/v1/chat/completions", {"Content-Type": "application/json"},
            request_data
        )
        self._send_response(status, resp_headers, resp_body)

    def _handle_streaming(self, openai_body: dict) -> None:
        """Forward streaming request and pass through SSE events."""
        request_data = json.dumps(openai_body).encode("utf-8")
        req = Request(
            _upstream_url(self.upstream, "/v1/chat/completions"),
            data=request_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            with urlopen(req, timeout=API_TIMEOUT) as upstream_resp:
                buffer = b""
                while True:
                    chunk = upstream_resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    # Split on double newlines (SSE delimiter)
                    while b"\n\n" in buffer:
                        line, buffer = buffer.split(b"\n\n", 1)
                        self.wfile.write(line + b"\n\n")
                        self.wfile.flush()
                # Flush remaining buffer
                if buffer:
                    self.wfile.write(buffer)
                    self.wfile.flush()
        except Exception:
            error_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:20]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": openai_body.get("model", "local-model"),
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
            }
            self.wfile.write(f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
        finally:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_response(status, {"Content-Type": "application/json"}, body)

    def _send_response(self, status: int, headers: dict, body: bytes) -> None:
        self.send_response(status)
        content_type = headers.get("Content-Type", "application/json")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LM-Eval Proxy – forwards OpenAI Chat Completions to upstream")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Proxy port (default: {DEFAULT_PORT})")
    parser.add_argument("--upstream", type=str, default=DEFAULT_UPSTREAM,
                        help=f"Upstream server URL (default: {DEFAULT_UPSTREAM})")
    parser.add_argument("--bind", type=str, default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    args = parser.parse_args()

    ProxyHandler.upstream = args.upstream
    # ThreadingHTTPServer (Fix 05.08.): HTTPServer verarbeitet nur EINEN
    # Request gleichzeitig -> lm_eval num_concurrent>1 wurde serialisiert,
    # dadurch lief trotz np=4 nur 1 Slot (Server-Log-Beweis 05.08.: alle
    # Requests auf Slot 3). Threading-Server erlaubt paralleles Durchreichen.
    server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
    print(f"[lmeval_proxy] Listening on {args.bind}:{args.port}")
    print(f"[lmeval_proxy] Upstream: {args.upstream}")
    print(f"[lmeval_proxy] Set base_url=http://{args.bind}:{args.port}/v1 in lm_eval config")
    print("[lmeval_proxy] Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[lmeval_proxy] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
