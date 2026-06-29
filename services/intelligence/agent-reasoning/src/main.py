"""Agent 推理层主入口 — 智能问答、LLM 调用工厂、多源检索编排。

LangGraph StateGraph 编排 6 节点流水线：
supervisor → context_resolution → call_tools → fusion → generator → citation。

支持两种响应模式：
- 非流式（JSON）：POST /api/v1/chat with stream=False
- 流式（SSE）：POST /api/v1/chat with stream=True

同时暴露内部共享服务：
- POST /api/v1/llm/completion — LLM 调用工厂（graph-engine 等内部服务调用）
"""

import json
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from daduhe_common import (
    TraceMiddleware,
    info,
    warn,
    error as log_error,
    get_or_generate_trace_id,
    create_health_router,
)

from src.models import (
    ChatRequest,
    ChatResponse,
    ChatResponseData,
    LLMCompletionRequest,
    LLMCompletionResponse,
    LLMCompletionData,
    Usage,
)
from src.settings import Settings
from src.graph.builder import build_graph
from src.llm.client import LLMClient
from src.store.conversation import InMemoryConversationStore, ConversationMessage

SERVICE = "agent-reasoning"

# ── 启动初始化 ──
_sett = Settings()
_llm = LLMClient(_sett)
_store = InMemoryConversationStore()
_graph = build_graph(settings=_sett, llm=_llm, store=_store)

app = FastAPI(title="agent-reasoning", version="0.1.0")
app.add_middleware(TraceMiddleware, service=SERVICE)
app.include_router(create_health_router(SERVICE, {}))


# ══════════════════════════════════════════════════════════════
# POST /api/v1/chat — 智能问答（核心入口）
# ══════════════════════════════════════════════════════════════


@app.post("/api/v1/chat")
async def chat(request: Request):
    """智能问答核心接口。

    接收用户问题，根据 stream 参数选择非流式（JSON）或流式（SSE）响应模式。
    非流式：执行完整流水线后返回 JSON 响应。
    流式：通过 SSE 逐 token 推送答案。

    Args:
        request: FastAPI Request，JSON body 对应 ChatRequest

    Returns:
        JSONResponse（非流式）或 StreamingResponse（流式）
    """
    trace_id = get_or_generate_trace_id(request, "agent-reasoning")
    body = await request.json()

    try:
        req = ChatRequest(**body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"code": 1002, "message": str(exc), "trace_id": trace_id},
        )

    info(
        SERVICE,
        "chat request",
        trace_id,
        query=req.query[:200],
        retrieval_mode=req.retrieval_mode,
        stream=req.stream,
    )

    # 首次对话自动生成 conv_id，后续同一会话传入同一个 id 实现多轮对话
    conv_id = req.conversation_id or f"conv-{trace_id[:8]}"
    input_state = {
        "query": req.query,
        "conversation_id": conv_id,
        "trace_id": trace_id,
        "retrieval_mode": req.retrieval_mode,
    }

    if req.stream:
        return StreamingResponse(
            _stream_chat(req, input_state, conv_id, trace_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── 非流式路径 ──
    t0 = time.perf_counter()
    try:
        result = await _graph.ainvoke(input_state)
    except Exception as exc:
        log_error(SERVICE, "graph execution failed", trace_id, error=str(exc))
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"code": 9001, "message": str(exc), "trace_id": trace_id},
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    # ── 存储会话 ──
    try:
        await _store.append_messages(
            conv_id,
            [
                ConversationMessage(role="user", content=req.query),
                ConversationMessage(role="assistant", content=result.get("answer", "")),
            ],
        )
    except Exception as exc:
        warn(SERVICE, "failed to store conversation", trace_id, error=str(exc))

    info(SERVICE, "chat response", trace_id, elapsed_ms=elapsed_ms)

    return ChatResponse(
        code=0,
        data=ChatResponseData(
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
            retrieval_mode_used=req.retrieval_mode,
            conversation_id=conv_id,
            trace_id=trace_id,
        ),
    ).model_dump()


# ── SSE 流式辅助函数 ──


async def _stream_chat(
    req: ChatRequest,
    input_state: dict,
    conv_id: str,
    trace_id: str,
):
    """异步生成器，消费 graph.astream() 产出 SSE 事件。

    事件类型：
    - status: 节点完成通知（supervisor、retrieval）
    - answer_chunk: LLM 生成 token
    - references: 引用数组
    - done: 完成信号（含 conversation_id、elapsed_ms）
    - error: 错误信息

    Args:
        req: 解析后的聊天请求
        input_state: Graph 输入状态
        conv_id: 会话 ID
        trace_id: 链路追踪 ID

    Yields:
        str: SSE 格式的事件帧
    """
    t0 = time.perf_counter()
    final_answer: list[str] = []
    final_state: dict = {}

    try:
        # LangGraph astream 同时用两种 stream_mode：
        #   "custom"  → generator 节点通过 get_stream_writer() 发出的 token
        #   "updates" → 每个节点完成后的状态更新（supervisor 意图、检索状态）
        async for mode, chunk in _graph.astream(
            input_state,
            stream_mode=["custom", "updates"],
        ):
            if mode == "custom":
                # generator 节点逐 token 发出的自定义事件
                event = chunk if isinstance(chunk, dict) else {}
                event_type = event.get("event", "answer_chunk")

                if event_type == "answer_chunk":
                    token = event.get("data", "")
                    final_answer.append(token)
                    yield f"event: answer_chunk\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
                elif event_type == "error":
                    err_msg = event.get("data", "unknown")
                    yield f"event: error\ndata: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"
                    return  # 流式出错立即终止

            elif mode == "updates":
                # 每个节点完成后的状态快照，用于向前端推送进度通知
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        final_state.update(node_output)

                    if node_name == "supervisor":
                        query_type = (
                            node_output.get("query_type", "")
                            if isinstance(node_output, dict)
                            else ""
                        )
                        sub_count = (
                            len(node_output.get("sub_questions", []))
                            if isinstance(node_output, dict)
                            else 0
                        )
                        yield f"event: status\ndata: {json.dumps({'node': 'supervisor', 'query_type': query_type, 'sub_questions': sub_count}, ensure_ascii=False)}\n\n"

                    elif node_name == "call_tools":
                        # 汇总所有子问题的检索命中数
                        sub_questions = (
                            node_output.get("sub_questions", [])
                            if isinstance(node_output, dict)
                            else []
                        )
                        total_results = sum(
                            len(sq.get("results", [])) for sq in sub_questions
                        )
                        yield f"event: status\ndata: {json.dumps({'node': 'retrieval', 'total_results': total_results}, ensure_ascii=False)}\n\n"

        # ── 推送引用 ──
        citations = final_state.get("citations", [])
        if citations:
            yield f"event: references\ndata: {json.dumps(citations, ensure_ascii=False)}\n\n"

        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        answer = "".join(final_answer) or final_state.get("answer", "")

        yield f"event: done\ndata: {json.dumps({'conversation_id': conv_id, 'trace_id': trace_id, 'elapsed_ms': elapsed_ms}, ensure_ascii=False)}\n\n"

        # ── 存储会话 ──
        try:
            await _store.append_messages(
                conv_id,
                [
                    ConversationMessage(role="user", content=req.query),
                    ConversationMessage(role="assistant", content=answer),
                ],
            )
        except Exception as exc:
            warn(SERVICE, "failed to store conversation", trace_id, error=str(exc))

    except Exception as exc:
        log_error(SERVICE, "stream execution failed", trace_id, error=str(exc))
        traceback.print_exc()
        yield f"event: error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"


# ══════════════════════════════════════════════════════════════
# POST /api/v1/llm/completion — LLM 调用工厂（内部共享服务）
# ══════════════════════════════════════════════════════════════


@app.post("/api/v1/llm/completion")
async def llm_completion(request: Request):
    """LLM 调用工厂接口。

    为 graph-engine 等内部服务提供统一的 LLM 调用中转。
    所有调用通过 llm-gateway 代理，支持 DeepSeek API 和本地 vLLM。

    Args:
        request: FastAPI Request，JSON body 对应 LLMCompletionRequest

    Returns:
        JSONResponse: 含 content、usage、latency_ms 的响应
    """
    trace_id = get_or_generate_trace_id(request, "agent-reasoning")
    body = await request.json()

    try:
        req = LLMCompletionRequest(**body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"code": 1002, "message": str(exc), "trace_id": trace_id},
        )

    info(
        SERVICE,
        "llm completion",
        trace_id,
        model=req.model,
        caller=req.caller,
        priority=req.priority,
    )

    try:
        result = await _llm.completion(
            model=req.model,
            messages=[m.model_dump() for m in req.messages],
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

    return LLMCompletionResponse(
        code=0,
        data=LLMCompletionData(
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


@app.get("/metrics")
async def metrics():
    """Prometheus 指标暴露端点。

    Returns:
        PlainTextResponse: Prometheus 格式指标
    """
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
