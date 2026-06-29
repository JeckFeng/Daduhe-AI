"""daduhe-common — 三个 intelligence 服务的共享基础设施。

Prefer importing from this top-level package rather than from submodules directly:
    from daduhe_common import info, error, ErrorCode, error_response
"""

from daduhe_common.middleware import TraceMiddleware as TraceMiddleware
from daduhe_common.logging import info as info, warn as warn, error as error
from daduhe_common.tracing import (
    get_or_generate_trace_id as get_or_generate_trace_id,
    generate_trace_id as generate_trace_id,
)
from daduhe_common.health import create_health_router as create_health_router
from daduhe_common.error_codes import ErrorCode as ErrorCode, error_response as error_response
