"""统一JSON结构化日志"""
import json
import sys
import time
import uuid
from datetime import datetime, timezone


def log(level: str, service: str, message: str, trace_id: str = "", **detail):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": service,
        "trace_id": trace_id,
        "message": message,
    }
    if detail:
        entry["detail"] = detail
    print(json.dumps(entry, ensure_ascii=False), file=sys.stderr, flush=True)


def info(service: str, message: str, trace_id: str = "", **detail):
    log("INFO", service, message, trace_id, **detail)


def warn(service: str, message: str, trace_id: str = "", **detail):
    log("WARN", service, message, trace_id, **detail)


def error(service: str, message: str, trace_id: str = "", **detail):
    log("ERROR", service, message, trace_id, **detail)
