"""统一错误码体系"""


class ErrorCode:
    OK = 0
    MISSING_FIELD = 1001
    INVALID_VALUE = 1002
    NOT_FOUND = 3001
    UPSTREAM_UNAVAILABLE = 4001
    UPSTREAM_TIMEOUT = 4002
    GRAPH_EXTRACTION_FAILED = 5003
    SEARCH_FAILED = 5004
    LLM_CALL_FAILED = 5005
    INTERNAL_ERROR = 9001


MESSAGES = {
    0: "ok",
    1001: "missing required field: {field}",
    1002: "invalid value for {field}: {value}",
    3001: "{resource} not found: {id}",
    4001: "upstream service unavailable: {service}",
    4002: "upstream timeout: {service}",
    5003: "graph extraction failed: {reason}",
    5004: "search failed: {reason}",
    5005: "LLM call failed: {reason}",
    9001: "internal error: {detail}",
}


def error_response(code: int, trace_id: str = "", **kwargs) -> dict:
    message = MESSAGES.get(code, "unknown error").format(**kwargs)
    resp = {"code": code, "message": message}
    if trace_id:
        resp["trace_id"] = trace_id
    return resp
