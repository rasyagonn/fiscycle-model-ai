"""Bearer service authentication, loopback development, bounded body, request IDs."""
import contextvars
import hmac
import json
import os
import uuid
from starlette.responses import JSONResponse

tenant_context = contextvars.ContextVar("fiscycle_tenant", default="local_demo")


class ServiceBoundary:
    def __init__(self, app):
        self.app = app
        self.tokens = json.loads(os.getenv("FISCYCLE_GATEWAY_TOKENS", "{}"))
        if not isinstance(self.tokens,dict): raise ValueError("Invalid gateway token mapping")
        token = os.getenv("FISCYCLE_AI_SERVICE_TOKEN")
        if token: self.tokens[token] = "service_backend"
        if any(not isinstance(k,str) or not k or not isinstance(v,str) or not v for k,v in self.tokens.items()):
            raise ValueError("Invalid service credential mapping")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http": return await self.app(scope, receive, send)
        from app.core.config import MAX_BODY_BYTES
        rid = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"").decode("latin1").removeprefix("Bearer ")
        # Private Docker Spaces may consume Authorization at the HF proxy.
        if b'x-fiscycle-service-token' in headers:
            supplied=headers[b'x-fiscycle-service-token'].decode('latin1')
        public = scope["path"] in {"/health", "/docs", "/openapi.json", "/redoc", "/"}
        tenant = "local_demo"
        async def respond(code, message):
            return await JSONResponse({"detail":message,"request_id":rid}, status_code=code,
                                      headers={"X-Request-ID":rid})(scope, receive, send)
        if self.tokens and not public and scope['method'] != 'OPTIONS':
            tenant = next((v for k,v in self.tokens.items() if hmac.compare_digest(k.encode(),supplied.encode())), None)
            if tenant is None: return await respond(401,"Bearer service token diperlukan")
        elif not self.tokens:
            host = (scope.get("client") or ("",0))[0]
            if host not in {"127.0.0.1", "::1", "testclient", "localhost"}:
                return await respond(403,"Mode tanpa token hanya menerima loopback")
        chunks = []
        if scope['method'] in {'POST','PUT','PATCH'}:
            length = headers.get(b'content-length')
            if length is not None:
                try:
                    if int(length) < 0: raise ValueError()
                    if int(length) > MAX_BODY_BYTES: return await respond(413,"Request melebihi batas ukuran")
                except ValueError: return await respond(400,"Content-Length tidak valid")
            count = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect': return
                count += len(message.get('body',b''))
                if count > MAX_BODY_BYTES: return await respond(413,"Request melebihi batas ukuran")
                chunks.append(message.get('body',b''))
                if not message.get('more_body'): break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered and chunks:
                delivered = True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        async def traced_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers',[]).append((b'x-request-id',rid.encode()))
            await send(message)
        context = tenant_context.set(tenant)
        try: await self.app(scope,bounded_receive,traced_send)
        finally: tenant_context.reset(context)
