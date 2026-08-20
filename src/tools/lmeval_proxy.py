#!/usr/bin/env python3
"""
LM-Eval Proxy - forwards OpenAI Chat Completions requests directly to
an OpenAI-compatible endpoint (e.g. LM Studio /v1/chat/completions).

Usage:
  python tools/lmeval_proxy.py                       # port 1235, upstream 127.0.0.1:1234
  python tools/lmeval_proxy.py --port 1236 --upstream localhost:4321

The proxy implements:
  GET  /v1/models             → pass-through
  POST /v1/chat/completions   → pass-through (no translation)

Then point lm_eval's base_url to http://localhost:1235/v1.
"""

import ipaddress
import json
import os
import socket
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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
CLIENT_IDLE_TIMEOUT = 60
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_SSE_EVENT_BYTES = 1024 * 1024
MAX_CONCURRENT_REQUESTS = 16
ALLOWED_GET_PATHS = frozenset({"/v1/models", "/health"})
ALLOWED_POST_PATHS = frozenset({"/v1/chat/completions"})


def _is_loopback_bind(bind: str) -> bool:
    if bind.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(bind).is_loopback
    except ValueError:
        return False


def _bounded_read(response: object, limit: int) -> bytes:
    headers = getattr(response, "headers", {})
    content_length = headers.get("Content-Length") if headers else None
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise ValueError("upstream response exceeds configured limit")
        except ValueError as exc:
            if str(exc) == "upstream response exceeds configured limit":
                raise
            raise ValueError("invalid upstream Content-Length") from exc
    body = response.read(limit + 1)  # type: ignore[attr-defined]
    if len(body) > limit:
        raise ValueError("upstream response exceeds configured limit")
    return body

def _proxy_upstream(upstream: str, path: str, headers: dict, body: bytes | None = None) -> tuple[int, dict, bytes]:
    """Forward a request to the upstream server and return (status, response_headers, body)."""
    url = _upstream_url(upstream, path)
    method = "POST" if body is not None else "GET"
    request_headers = {"Accept": headers.get("Accept", "application/json")}
    if body is not None:
        request_headers["Content-Type"] = headers.get("Content-Type", "application/json")
    if "Authorization" in headers:
        request_headers["Authorization"] = headers["Authorization"]
    req = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=API_TIMEOUT) as resp:
            resp_headers = dict(resp.headers)
            return resp.status, resp_headers, _bounded_read(resp, MAX_RESPONSE_BYTES)
    except Exception as e:
        # Try to read error body
        try:
            if hasattr(e, "read"):
                err_body = e.read().decode("utf-8", errors="replace")[:500]
            else:
                err_body = str(e)
        except Exception:
            err_body = str(e)
        return 502, {"Content-Type": "text/plain"}, f"Proxy error: {err_body}".encode()


# ── HTTP Server / Handler ──

class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threading server with explicit admission control and daemon cleanup."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = MAX_CONCURRENT_REQUESTS

    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(server_address, handler_class)
        self._admission = BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not self._admission.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._admission.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._admission.release()

class ProxyHandler(BaseHTTPRequestHandler):
    upstream = DEFAULT_UPSTREAM
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(CLIENT_IDLE_TIMEOUT)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[lmeval_proxy] {args[0]} {args[1]} {args[2]}\n")

    def _get_body(self) -> bytes | None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._send_json(411, {"error": "Content-Length is required"})
            return None
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return None
        if length < 0 or length > MAX_REQUEST_BODY_BYTES:
            self._send_json(413, {"error": "request body exceeds configured limit"})
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._send_json(400, {"error": "incomplete request body"})
            return None
        return body

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if path not in ALLOWED_GET_PATHS:
            self._send_json(404, {"error": "route not allowed"})
            return
        status, resp_headers, body = _proxy_upstream(self.upstream, path, dict(self.headers))
        self._send_response(status, resp_headers, body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path not in ALLOWED_POST_PATHS:
            self._send_json(404, {"error": "route not allowed"})
            return
        body = self._get_body()
        if body is not None:
            self._handle_chat_completion(body)

    def do_OPTIONS(self) -> None:
        self._send_json(405, {"error": "method not allowed"})

    def _handle_chat_completion(self, raw_body: bytes) -> None:
        """Forward /v1/chat/completions directly to upstream (no translation)."""
        try:
            openai_body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return
        if not isinstance(openai_body, dict):
            self._send_json(400, {"error": "JSON body must be an object"})
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
        self.send_header("Connection", "close")
        self.end_headers()

        total_forwarded = 0
        try:
            with urlopen(req, timeout=API_TIMEOUT) as upstream_resp:
                buffer = b""
                while True:
                    chunk = upstream_resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > MAX_SSE_EVENT_BYTES:
                        raise ValueError("SSE event exceeds configured limit")
                    # Split on double newlines (SSE delimiter)
                    while b"\n\n" in buffer:
                        line, buffer = buffer.split(b"\n\n", 1)
                        total_forwarded += len(line) + 2
                        if total_forwarded > MAX_RESPONSE_BYTES:
                            raise ValueError("stream response exceeds configured limit")
                        self.wfile.write(line + b"\n\n")
                        self.wfile.flush()
                # Flush remaining buffer
                if buffer:
                    if len(buffer) > MAX_SSE_EVENT_BYTES:
                        raise ValueError("SSE event exceeds configured limit")
                    total_forwarded += len(buffer)
                    if total_forwarded > MAX_RESPONSE_BYTES:
                        raise ValueError("stream response exceeds configured limit")
                    self.wfile.write(buffer)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        except Exception:
            error_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:20]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": openai_body.get("model", "local-model"),
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
            }
            try:
                self.wfile.write(f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except OSError:
                return
        finally:
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except OSError:
                pass

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_response(status, {"Content-Type": "application/json"}, body)

    def _send_response(self, status: int, headers: dict, body: bytes) -> None:
        if len(body) > MAX_RESPONSE_BYTES:
            status = 502
            body = b'{"error":"response exceeds configured limit"}'
        self.send_response(status)
        content_type = headers.get("Content-Type", "application/json")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except OSError:
            pass


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Bounded loopback LM-Eval proxy")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Proxy port (default: {DEFAULT_PORT})")
    parser.add_argument("--upstream", type=str, default=DEFAULT_UPSTREAM,
                        help=f"Upstream server URL (default: {DEFAULT_UPSTREAM})")
    parser.add_argument("--bind", type=str, default="127.0.0.1", help="Loopback bind address")
    args = parser.parse_args()
    if not _is_loopback_bind(args.bind):
        parser.error("--bind must be a loopback address; use an authenticated gateway for remote access")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    ProxyHandler.upstream = args.upstream
    server = BoundedThreadingHTTPServer((args.bind, args.port), ProxyHandler)
    print(f"[lmeval_proxy] Listening on {args.bind}:{args.port}")
    print(f"[lmeval_proxy] Set base_url=http://{args.bind}:{args.port}/v1 in lm_eval config")
    print("[lmeval_proxy] Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[lmeval_proxy] Shutting down...")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
