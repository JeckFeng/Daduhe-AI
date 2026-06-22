"""链路追踪: X-Trace-Id 注入与透传"""
import uuid
from typing import Optional

from fastapi import Request


def get_or_generate_trace_id(request: Request, prefix: str = "daduhe") -> str:
    """从请求Header提取trace_id，不存在则生成"""
    trace_id = request.headers.get("X-Trace-Id")
    if not trace_id:
        trace_id = f"{prefix}-{uuid.uuid4()}"
    return trace_id


def generate_trace_id(prefix: str = "daduhe") -> str:
    return f"{prefix}-{uuid.uuid4()}"
