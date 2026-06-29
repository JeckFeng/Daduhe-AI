"""知识图谱检索工具 — 封装 graph-engine 服务的 POST /api/v1/graph/query。

通过 ToolRegistry 注册为 "graph_search" 工具（source_type="graph"），
并行调用 entity_search + relation_search 并合并去重结果。
"""

import asyncio
import time

import httpx

from .base import ToolDef, ToolResult

GRAPH_SEARCH_TOOL = ToolDef(
    name="graph_search",
    description=(
        "知识图谱向量检索。检索水工缺陷相关的实体（缺陷类型、材料、结构部位、"
        "处理措施等）和关系（规范约束、因果关系、分类关系等），返回知识图谱中"
        "的节点和边。适用于实体关系查询、多实体关联发现、规范条文涉及的实体探索。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询语句"},
            "top_k": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    source_type="graph",
)


async def graph_search_handler(
    query: str,
    top_k: int = 10,
    graph_engine_url: str = "http://localhost:8001",
    trace_id: str = "",
    client: httpx.AsyncClient | None = None,
) -> ToolResult:
    """调用 graph-engine 的 entity_search + relation_search，合并去重结果。

    并行发起实体检索和关系检索，分别得到实体节点和关系边后，
    按 id（实体）和 (from, to, relation)（边）去重合并。

    Args:
        query: 检索查询文本
        top_k: 每种检索返回结果数量上限
        graph_engine_url: graph-engine 服务基础 URL
        trace_id: 链路追踪 ID
        client: 可选的外部 httpx 客户端，用于连接复用

    Returns:
        ToolResult: 包含 entities 和 edges 合并结果
    """
    t0 = time.perf_counter()

    headers = {"X-Trace-Id": trace_id} if trace_id else {}
    base = graph_engine_url.rstrip("/")

    async def _call(query_type: str) -> dict:
        """调用 graph-engine 的单个查询类型。

        Args:
            query_type: "entity_search" 或 "relation_search"

        Returns:
            dict: {"entities": [...], "edges": [...], "error": str | None}
        """
        payload = {"query_type": query_type, "params": {"query": query, "top_k": top_k}}
        if client is not None:
            resp = await client.post(
                f"{base}/api/v1/graph/query",
                json=payload,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient(timeout=15) as own:
                resp = await own.post(
                    f"{base}/api/v1/graph/query",
                    json=payload,
                    headers=headers,
                )
        if resp.status_code != 200:
            return {
                "entities": [],
                "edges": [],
                "error": f"graph-engine returned {resp.status_code}",
            }
        body = resp.json()
        if body.get("code") != 0:
            return {
                "entities": [],
                "edges": [],
                "error": body.get("message", "graph-engine error"),
            }
        return body["data"]

    # 并行发起 entity_search + relation_search（= LightRAG local + global）
    entity_result, relation_result = await asyncio.gather(
        _call("entity_search"),
        _call("relation_search"),
    )

    latency_ms = round((time.perf_counter() - t0) * 1000)

    # ── 实体去重：按 id，首次出现优先（entity_search 结果在前）──
    # entity_search 和 relation_search 都可能返回重叠实体，保留首次出现
    entities: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}

    for result in (entity_result, relation_result):
        for e in result.get("entities", []):
            eid = e.get("id", e.get("name", ""))
            if eid and eid not in entities:
                entities[eid] = {
                    "id": e.get("id", ""),
                    "type": e.get("type", ""),
                    "name": e.get("name", ""),
                    "description": e.get("description", ""),
                    "source_type": "graph",
                }
        for edge in result.get("edges", []):
            # 边的复合键：(from, to, relation)，三者相同视为同一条边
            key = (edge.get("from", ""), edge.get("to", ""), edge.get("relation", ""))
            if key not in edges:
                edges[key] = {
                    "from": edge.get("from", ""),
                    "to": edge.get("to", ""),
                    "relation": edge.get("relation", ""),
                    "keywords": edge.get("keywords", ""),
                    "description": edge.get("description", ""),
                    "source_type": "graph",
                }

    merged = {
        "entities": list(entities.values()),
        "edges": list(edges.values()),
        "source_type": "graph",
    }

    total = len(merged["entities"]) + len(merged["edges"])

    errors: list[str] = []
    if entity_result.get("error"):
        errors.append(f"entity_search: {entity_result['error']}")
    if relation_result.get("error"):
        errors.append(f"relation_search: {relation_result['error']}")

    return ToolResult(
        source_type="graph",
        tool_name="graph_search",
        results=[merged] if total > 0 else [],
        total_hits=total,
        latency_ms=latency_ms,
        error="; ".join(errors) if errors else None,
    )
