"""FastAPI middleware: X-Trace-Id 自动注入与透传"""
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class TraceMiddleware(BaseHTTPMiddleware):
    """自动处理 X-Trace-Id 的注入与透传。

    注册后每个 endpoint 通过 request.state.trace_id 直接获取 trace_id，
    无需手动调用 get_or_generate_trace_id。
    """

    def __init__(self, app, service: str = "daduhe"):
        super().__init__(app)
        self.service = service

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id")
        if not trace_id:
            trace_id = f"{self.service}-{uuid.uuid4()}"

        request.state.trace_id = trace_id

        response: Response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
