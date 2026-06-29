"""Search-engine 检索工具 — 封装 search-engine 服务的 POST /api/v1/search。

通过 ToolRegistry 注册为 "search_engine" 工具（source_type="chunk"），
由 call_tools 节点按需调度。默认使用 hybrid 检索模式。
"""

import time

import httpx

from .base import ToolDef, ToolResult


SEARCH_ENGINE_TOOL = ToolDef(
    name="search_engine",
    description="检索文档 chunk。适用于自然语言问题，查询水工缺陷相关规范、案例、文献中的知识。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询语句"},
            "top_k": {"type": "integer", "default": 10},
            "doc_type": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
    },
    source_type="chunk",
)


async def search_engine_handler(
    query: str,
    top_k: int = 10,
    doc_type: list[str] | None = None,
    search_engine_url: str = "http://localhost:8002",
    trace_id: str = "",
    client: httpx.AsyncClient | None = None,
) -> ToolResult:
    """调用 search-engine 的 hybrid 检索模式，返回文档 chunk 结果。

    Args:
        query: 检索查询文本
        top_k: 返回结果数量上限
        doc_type: 按文档类型过滤，如 ["规范"]，None 不过滤
        search_engine_url: search-engine 服务基础 URL
        trace_id: 链路追踪 ID
        client: 可选的外部 httpx 客户端，用于连接复用

    Returns:
        ToolResult: 包含 chunk 检索命中列表的结果封装
    """
    filters: dict[str, str | list[str]] = {}
    if doc_type:
        filters["doc_type"] = doc_type

    payload = {
        "query": query,
        "mode": "hybrid",
        "top_k": top_k,
        "filters": filters,
        "include_sources": ["chunks"],
    }
    headers = {"X-Trace-Id": trace_id} if trace_id else {}

    if client is not None:
        t0 = time.perf_counter()
        resp = await client.post(
            f"{search_engine_url}/api/v1/search",
            json=payload,
            headers=headers,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000)
    else:
        async with httpx.AsyncClient(timeout=10) as own_client:
            t0 = time.perf_counter()
            resp = await own_client.post(
                f"{search_engine_url}/api/v1/search",
                json=payload,
                headers=headers,
            )
            latency_ms = round((time.perf_counter() - t0) * 1000)

    if resp.status_code != 200:
        return ToolResult(
            source_type="chunk",
            tool_name="search_engine",
            results=[],
            total_hits=0,
            latency_ms=latency_ms,
            error=f"search-engine returned {resp.status_code}",
        )

    body = resp.json()
    if body.get("code") != 0:
        return ToolResult(
            source_type="chunk",
            tool_name="search_engine",
            results=[],
            total_hits=0,
            latency_ms=latency_ms,
            error=body.get("message", "search-engine error"),
        )

    raw = body["data"]["results"]
    results: list[dict] = []
    for r in raw:
        # 过滤：仅保留 source_type="chunk" 的结果，排除 search-engine 可能混入的规则命中
        if r["source_type"] != "chunk":
            continue
        results.append(
            {
                "chunk_id": r["chunk_id"],
                "text": r["text"],
                "score": r["score"],
                "source_type": "chunk",
                "metadata": r["metadata"],
            }
        )

    return ToolResult(
        source_type="chunk",
        tool_name="search_engine",
        results=results,
        total_hits=len(results),
        latency_ms=latency_ms,
    )
