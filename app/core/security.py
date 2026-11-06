"""Trusted gateway boundary. Tokens are provisioned server-side, never supplied as tenant IDs."""
import contextvars
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

from starlette.responses import JSONResponse

tenant_context = contextvars.ContextVar("fiscycle_tenant", default="local_demo")
logger = logging.getLogger("fiscycle.requests")


class GatewayBoundary:
    def __init__(self, app):
        self.app = app
        self.tokens = json.loads(os.getenv("FISCYCLE_GATEWAY_TOKENS", "{}"))
        if not isinstance(self.tokens, dict) or any(not k or not isinstance(v, str) or not v for k, v in self.tokens.items()):
            raise ValueError("Gateway tokens must map secret tokens to tenant names")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from app.core.config import MAX_BODY_BYTES
        headers = dict(scope.get("headers", []))
        rid = uuid.uuid4().hex
        start = time.monotonic()
        tenant = "local_demo"
        supplied = headers.get(b"authorization", b"").decode("latin1").removeprefix("Bearer ")
        api = scope["path"] not in {"/", "/ecosystem", "/bsf-intelligence", "/manifest.webmanifest", "/sw.js", "/fiscycle-icon.svg"} and not scope["path"].startswith("/assets/")
        if self.tokens and api and scope["method"] != "OPTIONS":
            tenant = next((v for k, v in self.tokens.items() if hmac.compare_digest(k.encode(), supplied.encode())), None)
            if tenant is None:
                return await JSONResponse({"detail": "Token gateway diperlukan", "request_id": rid}, status_code=401)(scope, receive, send)
        elif not self.tokens:
            host = (scope.get("client") or ("", 0))[0]
            if host not in {"127.0.0.1", "::1", "testclient", "localhost"}:
                return await JSONResponse({"detail": "Mode lokal hanya menerima koneksi loopback"}, status_code=403)(scope, receive, send)
        # Request bodies are bounded even when Content-Length is absent or untrusted.
        chunks, count = [], 0
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                count += len(message.get("body", b""))
                if count > MAX_BODY_BYTES:
                    return await JSONResponse({"detail": "Ukuran request melebihi batas"}, status_code=413)(scope, receive, send)
                chunks.append(message.get("body", b""))
                if not message.get("more_body"):
                    break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered and chunks:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        async def traced_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
                logger.info("request=%s method=%s status=%s duration_ms=%.1f", rid, scope["method"], message["status"], (time.monotonic()-start)*1000)
            await send(message)
        context = tenant_context.set(tenant)
        try:
            await self.app(scope, bounded_receive, traced_send)
        finally:
            tenant_context.reset(context)
