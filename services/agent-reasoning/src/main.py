"""agent-reasoning: Agent推理层 — 智能问答、LLM调用工厂、检索模式选择"""
import os
import sys

sys.path.insert(0, "/app")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging import info, error as log_error
from common.tracing import get_or_generate_trace_id
from common.health import create_health_router
from common.error_codes import ErrorCode, error_response

SERVICE = "agent-reasoning"

app = FastAPI(title="agent-reasoning", version="0.1.0")

app.include_router(create_health_router(SERVICE, {}))


# ============================================================
# POST /api/v1/chat — 智能问答（核心入口）
# ============================================================

@app.post("/api/v1/chat")
async def chat(request: Request):
    trace_id = get_or_generate_trace_id(request, "agent-reasoning")
    body = await request.json()

    query = body.get("query", "")
    conversation_id = body.get("conversation_id", "")
    retrieval_mode = body.get("retrieval_mode", "auto")
    stream = body.get("stream", False)

    info(
        SERVICE,
        "chat request",
        trace_id,
        query=query,
        retrieval_mode=retrieval_mode,
    )

    # TODO:
    # 1. 意图识别
    # 2. 根据retrieval_mode调用search-engine检索
    # 3. 可选: 调用graph-engine获取图谱上下文
    # 4. 组装prompt，调用LLM生成答案
    # 5. 组装溯源引用citations

    return JSONResponse(
        content={
            "code": 0,
            "data": {
                "answer": "[TODO] LLM回答内容",
                "citations": [],
                "retrieval_mode_used": retrieval_mode,
                "conversation_id": conversation_id or f"conv-{trace_id[:8]}",
                "trace_id": trace_id,
            },
        }
    )


# ============================================================
# POST /api/v1/llm/completion — LLM调用工厂（内部共享服务）
# ============================================================

@app.post("/api/v1/llm/completion")
async def llm_completion(request: Request):
    trace_id = get_or_generate_trace_id(request, "agent-reasoning")
    body = await request.json()

    model = body.get("model", "deepseek-chat")
    messages = body.get("messages", [])
    temperature = body.get("temperature", 0.1)
    max_tokens = body.get("max_tokens", 2000)
    caller = body.get("caller", "unknown")
    priority = body.get("priority", "batch")

    info(
        SERVICE,
        "llm completion",
        trace_id,
        model=model,
        caller=caller,
        priority=priority,
    )

    # TODO:
    # 1. 根据model选择后端: deepseek-chat → DeepSeek API / vllm-local → 本地vLLM
    # 2. 根据priority选择: realtime → 低延迟 / batch → 高吞吐
    # 3. 统一调用OpenAI兼容API
    # 4. 记录token用量，用于成本统计

    return JSONResponse(
        content={
            "code": 0,
            "data": {
                "id": f"llm-resp-{trace_id[:8]}",
                "content": "[TODO] LLM响应",
                "model": model,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "latency_ms": 0,
            },
        }
    )


@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
