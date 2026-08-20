"""Regression tests for the bounded local LM-Eval proxy."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, "src/tools")

import lmeval_proxy as proxy


class _UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"data": [{"id": "smoke-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = json.dumps({
            "id": "chatcmpl-test",
            "choices": [{"message": {"content": "proxy-ok"}}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _serve(server: HTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_proxy_accepts_only_loopback_binds() -> None:
    assert proxy._is_loopback_bind("127.0.0.1") is True
    assert proxy._is_loopback_bind("::1") is True
    assert proxy._is_loopback_bind("0.0.0.0") is False  # noqa: S104 - intentional negative test
    assert proxy._is_loopback_bind("192.168.1.20") is False


def test_proxy_forwards_allowed_routes_and_rejects_arbitrary_post() -> None:
    upstream = HTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    proxy_server = proxy.BoundedThreadingHTTPServer(("127.0.0.1", 0), proxy.ProxyHandler)
    proxy.ProxyHandler.upstream = f"http://127.0.0.1:{upstream.server_port}"
    upstream_thread = _serve(upstream)
    proxy_thread = _serve(proxy_server)
    try:
        models = json.loads(urlopen(f"http://127.0.0.1:{proxy_server.server_port}/v1/models").read())
        assert models["data"][0]["id"] == "smoke-model"

        request = Request(
            f"http://127.0.0.1:{proxy_server.server_port}/v1/chat/completions",
            data=json.dumps({"model": "smoke-model", "messages": []}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = json.loads(urlopen(request).read())
        assert response["choices"][0]["message"]["content"] == "proxy-ok"

        forbidden = Request(
            f"http://127.0.0.1:{proxy_server.server_port}/v1/admin",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(forbidden)
        assert exc_info.value.code == 404
    finally:
        proxy_server.shutdown()
        proxy_server.server_close()
        upstream.shutdown()
        upstream.server_close()
        proxy_thread.join(timeout=2)
        upstream_thread.join(timeout=2)


def test_proxy_rejects_oversized_request_body(monkeypatch: pytest.MonkeyPatch) -> None:
    upstream = HTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    proxy_server = proxy.BoundedThreadingHTTPServer(("127.0.0.1", 0), proxy.ProxyHandler)
    proxy.ProxyHandler.upstream = f"http://127.0.0.1:{upstream.server_port}"
    monkeypatch.setattr(proxy, "MAX_REQUEST_BODY_BYTES", 4)
    upstream_thread = _serve(upstream)
    proxy_thread = _serve(proxy_server)
    try:
        request = Request(
            f"http://127.0.0.1:{proxy_server.server_port}/v1/chat/completions",
            data=b"12345",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(request)
        assert exc_info.value.code == 413
    finally:
        proxy_server.shutdown()
        proxy_server.server_close()
        upstream.shutdown()
        upstream.server_close()
        proxy_thread.join(timeout=2)
        upstream_thread.join(timeout=2)
