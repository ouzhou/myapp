from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = b"x-request-id"
_MAX_REQUEST_ID_LEN = 128


def _incoming_request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key != _REQUEST_ID_HEADER:
            continue
        raw = value.decode("latin-1").strip()
        if raw and "\r" not in raw and "\n" not in raw:
            return raw[:_MAX_REQUEST_ID_LEN]
        break
    return str(uuid4())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        header_value = request_id.encode("latin-1")

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, header_value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_id)
