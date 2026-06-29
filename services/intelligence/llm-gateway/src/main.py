"""llm-gateway: LLM 调用工厂 — 统一 LLM 入口 + PG 缓存。

POST /api/v1/completion — cache-wrapped LLM completion.
Cache key = compute_args_hash(system, user, model, host) so switching
backends (vllm vs deepseek) automatically busts the cache.
"""

from contextlib import asynccontextmanager
import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from daduhe_common import (
    TraceMiddleware,
    info,
    warn,
    error as log_error,
    get_or_generate_trace_id,
    create_health_router,
)

from src.settings import Settings
from src.client import LLMClient
from src.cache import LLMCache

SERVICE = "llm-gateway"

_settings = Settings()
_llm = LLMClient(_settings)
_cache = LLMCache(_settings)

# ── Table DDL ────────────────────────────────────────────────────

_CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS llm_gateway"
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS llm_gateway.llm_cache (
    cache_key   TEXT PRIMARY KEY,
    model       TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    user_prompt TEXT NOT NULL DEFAULT '',
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _init_db() -> None:
    """Create PG schema and cache table if they don't exist."""
    try:
        conn = psycopg2.connect(
            host=_settings.pg_host,
            port=_settings.pg_port,
            user=_settings.pg_user,
            password=_settings.pg_password,
            dbname=_settings.pg_database,
        )
        cur = conn.cursor()
        cur.execute(_CREATE_SCHEMA)
        cur.execute(_CREATE_TABLE)
        conn.commit()
        cur.close()
        conn.close()
        info(SERVICE, "pg schema initialized")
    except Exception as exc:
        warn(SERVICE, "pg init failed (cache disabled)", error=str(exc))


# ── Lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(title="llm-gateway", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware, service=SERVICE)

_pg_ok = lambda: "ok"  # noqa: E731
app.include_router(create_health_router(SERVICE, {"postgres": _pg_ok}))


# ── Models ───────────────────────────────────────────────────────


class Message(BaseModel):
    role: str
    content: str


class CompletionRequest(BaseModel):
    model: str = "vllm-local"
    messages: list[Message]
    temperature: float = 0.1
    max_tokens: int = 2000
    caller: str = ""
    priority: str = Field(default="batch", pattern=r"^(realtime|batch)$")


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class CompletionData(BaseModel):
    id: str
    content: str
    model: str
    usage: Usage
    latency_ms: float = 0


class CompletionResponse(BaseModel):
    code: int = 0
    data: CompletionData


# ── POST /api/v1/completion ─────────────────────────────────────


@app.post("/api/v1/completion")
async def completion(request: Request):
    trace_id = get_or_generate_trace_id(request, SERVICE)
    body = await request.json()

    try:
        req = CompletionRequest(**body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"code": 1002, "message": str(exc), "trace_id": trace_id},
        )

    messages = [m.model_dump() for m in req.messages]

    # Extract system/user prompts for cache key (LightRAG-style identity)
    system_prompt = ""
    user_prompt = ""
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        elif m["role"] == "user":
            user_prompt = m["content"]

    cache_key = _cache.cache_key(
        req.model,
        system_prompt,
        user_prompt,
        host=_llm.get_host(req.model),
    )

    # ── Cache hit ──
    cached = _cache.get(cache_key)
    if cached is not None:
        info(
            SERVICE,
            "cache hit",
            trace_id,
            model=req.model,
            caller=req.caller,
        )
        return CompletionResponse(
            code=0,
            data=CompletionData(
                id=f"llm-resp-{trace_id[:8]}",
                content=cached["content"],
                model=req.model,
                usage=Usage(
                    prompt_tokens=cached.get("prompt_tokens", 0),
                    completion_tokens=cached.get("completion_tokens", 0),
                ),
                latency_ms=cached.get("latency_ms", 0),
            ),
        ).model_dump()

    # ── Cache miss → call LLM ──
    info(
        SERVICE,
        "cache miss, calling LLM",
        trace_id,
        model=req.model,
        caller=req.caller,
    )

    try:
        result = await _llm.completion(
            model=req.model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            priority=req.priority,
        )
    except Exception as exc:
        log_error(SERVICE, "llm call failed", trace_id, error=str(exc))
        return JSONResponse(
            status_code=502,
            content={"code": 4001, "message": str(exc), "trace_id": trace_id},
        )

    # ── Cache result ──
    try:
        _cache.set(cache_key, req.model, system_prompt, user_prompt, result)
    except Exception as exc:
        warn(SERVICE, "cache set failed", trace_id, error=str(exc))

    return CompletionResponse(
        code=0,
        data=CompletionData(
            id=f"llm-resp-{trace_id[:8]}",
            content=result["content"],
            model=req.model,
            usage=Usage(
                prompt_tokens=result["prompt_tokens"],
                completion_tokens=result["completion_tokens"],
            ),
            latency_ms=result["latency_ms"],
        ),
    ).model_dump()


# ── POST /api/v1/completion/stream ────────────────────────────────


@app.post("/api/v1/completion/stream")
async def completion_stream(request: Request):
    """Streaming LLM completion — returns SSE (text/event-stream).

    Event types:
      - ``token`` — a content delta
      - ``done``  — completion signal with usage + latency
      - ``error`` — error message
    """
    import json
    import time as time_mod

    trace_id = get_or_generate_trace_id(request, SERVICE)
    body = await request.json()

    try:
        req = CompletionRequest(**body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"code": 1002, "message": str(exc), "trace_id": trace_id},
        )

    messages = [m.model_dump() for m in req.messages]

    # Extract system/user for cache key
    system_prompt = ""
    user_prompt = ""
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        elif m["role"] == "user":
            user_prompt = m["content"]

    cache_key = _cache.cache_key(
        req.model,
        system_prompt,
        user_prompt,
        host=_llm.get_host(req.model),
    )

    async def _event_stream():
        # ── Cache hit: yield cached content as single token ──
        cached = _cache.get(cache_key)
        if cached is not None:
            info(SERVICE, "stream cache hit", trace_id, model=req.model)
            yield f"data: {json.dumps({'token': cached['content']})}\n\n"
            yield f"data: {json.dumps({'done': True, 'usage': {'prompt_tokens': cached.get('prompt_tokens', 0), 'completion_tokens': cached.get('completion_tokens', 0)}, 'latency_ms': cached.get('latency_ms', 0)})}\n\n"
            return

        # ── Cache miss → stream from LLM ──
        info(SERVICE, "stream cache miss", trace_id, model=req.model)
        t0 = time_mod.perf_counter()
        full_content: list[str] = []

        try:
            async for token in _llm.completion_stream(
                model=req.model,
                messages=messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                priority=req.priority,
            ):
                full_content.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            log_error(SERVICE, "stream failed", trace_id, error=str(exc))
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            return

        latency_ms = round((time_mod.perf_counter() - t0) * 1000)
        content = "".join(full_content)
        prompt_tokens = len("".join(m["content"] for m in messages))  # rough estimate

        yield f"data: {json.dumps({'done': True, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': len(full_content)}, 'latency_ms': latency_ms})}\n\n"

        # ── Cache the result ──
        try:
            _cache.set(
                cache_key,
                req.model,
                system_prompt,
                user_prompt,
                {
                    "content": content,
                    "model": req.model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": len(full_content),
                    "latency_ms": latency_ms,
                },
            )
        except Exception as exc:
            warn(SERVICE, "stream cache set failed", trace_id, error=str(exc))

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/metrics")
async def metrics():
    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
