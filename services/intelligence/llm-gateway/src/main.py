"""llm-gateway: LLM 调用工厂 — 统一 LLM 入口 + PG 缓存。

提供三个端点：
- POST /api/v1/completion        — 缓存包裹的非流式 LLM Completion
- POST /api/v1/completion/stream — 流式 SSE LLM Completion（缓存命中时单 token 返回）
- GET  /health /ready /metrics   — 健康检查与指标（由 daduhe_common 提供）

缓存键 = MD5(system + user + model + host)，切换后端（vLLM vs DeepSeek）
时自动 bust 缓存。

LLM 后端路由：
    vllm-local    → 本地 vLLM (AsyncOpenAI, base_url=vllm_url)
    deepseek-chat → DeepSeek API (AsyncOpenAI, base_url=deepseek_api_url)
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

# ── 表 DDL ────────────────────────────────────────────────────────

_CREATE_SCHEMA: str = "CREATE SCHEMA IF NOT EXISTS llm_gateway"
_CREATE_TABLE: str = """
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
    """创建 PG schema 和缓存表（幂等）。

    失败时不阻塞服务启动，仅记 WARN 日志（缓存降级为禁用）。
    """
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
    """应用生命周期：启动时初始化 PG 缓存表。"""
    _init_db()
    yield


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(title="llm-gateway", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware, service=SERVICE)

_pg_ok = lambda: "ok"  # noqa: E731
app.include_router(create_health_router(SERVICE, {"postgres": _pg_ok}))


# ── 请求/响应模型 ──────────────────────────────────────────────────


class Message(BaseModel):
    """OpenAI 兼容消息格式。"""
    role: str       # "system" / "user" / "assistant"
    content: str    # 消息文本


class CompletionRequest(BaseModel):
    """LLM Completion 请求体。"""
    model: str = "vllm-local"
    messages: list[Message]
    temperature: float = 0.1
    max_tokens: int = 2000
    caller: str = ""          # 调用方标识（用于日志/监控）
    priority: str = Field(default="batch", pattern=r"^(realtime|batch)$")
    """请求优先级：realtime（30s 超时）/ batch（120s 超时）。"""


class Usage(BaseModel):
    """Token 用量统计。"""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class CompletionData(BaseModel):
    """Completion 响应数据载荷。"""
    id: str
    content: str
    model: str
    usage: Usage
    latency_ms: float = 0


class CompletionResponse(BaseModel):
    """Completion 响应体（最外层封装）。"""
    code: int = 0
    data: CompletionData


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/completion — 非流式 LLM Completion
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/completion")
async def completion(request: Request):
    """缓存包裹的非流式 LLM Completion。

    流程：
        1. 解析 system/user prompt
        2. 计算缓存键（包含 host，区分不同后端）
        3. 缓存命中 → 直接返回
        4. 缓存未命中 → 调用 LLM → 写入缓存 → 返回
    """
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

    # 提取 system/user prompt 用于缓存键计算
    system_prompt = ""
    user_prompt = ""
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        elif m["role"] == "user":
            user_prompt = m["content"]

    # 缓存键 = MD5(system + user + model + host)
    # host 不同（vllm vs deepseek）会 bust 缓存
    cache_key = _cache.cache_key(
        req.model,
        system_prompt,
        user_prompt,
        host=_llm.get_host(req.model),
    )

    # ── 缓存命中 ──
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

    # ── 缓存未命中 → 调用 LLM ──
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

    # ── 写入缓存（失败不影响响应） ──
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


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/completion/stream — 流式 SSE Completion
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/completion/stream")
async def completion_stream(request: Request):
    """流式 LLM Completion（SSE，text/event-stream）。

    SSE 事件类型：
        - data: {"token": "<delta>"}   — 内容增量
        - data: {"done": True, ...}    — 完成信号 + usage + latency
        - event: error / data: {"error": "..."}  — 错误

    缓存命中时将完整内容作为单个 token 返回。
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

    # 提取 system/user 用于缓存键
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
        """SSE 事件生成器：缓存命中 → 单 token / 未命中 → 逐 token 流。"""
        # ── 缓存命中：将缓存内容作为单 token yield ──
        cached = _cache.get(cache_key)
        if cached is not None:
            info(SERVICE, "stream cache hit", trace_id, model=req.model)
            yield f"data: {json.dumps({'token': cached['content']})}\n\n"
            yield f"data: {json.dumps({'done': True, 'usage': {'prompt_tokens': cached.get('prompt_tokens', 0), 'completion_tokens': cached.get('completion_tokens', 0)}, 'latency_ms': cached.get('latency_ms', 0)})}\n\n"
            return

        # ── 缓存未命中 → 流式调用 LLM ──
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
        # prompt_tokens 粗略估算 = 所有消息内容的总长度
        prompt_tokens = len("".join(m["content"] for m in messages))

        yield f"data: {json.dumps({'done': True, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': len(full_content)}, 'latency_ms': latency_ms})}\n\n"

        # ── 写入缓存（失败不影响流式响应） ──
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
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保 SSE 实时推送
        },
    )


# ═══════════════════════════════════════════════════════════════
# Prometheus / 启动入口
# ═══════════════════════════════════════════════════════════════


@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点（占位：尚未实现）。"""
    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
