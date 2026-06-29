"""Fusion 节点 — 多源检索结果去重、排序、截断与上下文格式化。

从所有子问题的 results 中收集 chunk 和 graph 两类命中，
分别按 chunk_id（保留最高分）和 entity_id / edge_key 去重，
排序截断后生成带 [N] 标记的上下文文本。
"""

from src.graph.state import AgentState
from src.settings import Settings
from daduhe_common import info

SERVICE = "agent-reasoning"


async def fusion_node(
    state: AgentState,
    settings: Settings | None = None,
) -> dict:
    """融合所有子问题的多源检索结果。

    将命中按 source_type 分为 chunk 和 graph 两类：
    - chunk: 按 chunk_id 去重（保留最高分），排序截断至 fusion_top_k，
      格式化为 "[N] 文本" 的引用标记格式
    - graph: 按 entity id 和 edge (from, to, relation) 去重合并

    Args:
        state: 当前 AgentState，含 sub_questions
        settings: 服务配置

    Returns:
        dict: {"fused_context": str, "fused_results": list[dict],
               "fused_graph_context": dict}
    """
    _settings = settings or Settings()
    trace_id = state.get("trace_id", "")
    sub_questions = state.get("sub_questions", [])

    # ── 收集所有命中 ──
    all_hits: list[dict] = []
    for sq in sub_questions:
        all_hits.extend(sq.get("results", []))

    # ── 按 source_type 分流：chunk 和 graph 采用不同的去重策略 ──
    # chunk 按 chunk_id 去重（同一 chunk 可能被多个 sub_question 命中），graph 按 entity/edge id 去重
    chunk_hits = [h for h in all_hits if h.get("source_type", "chunk") == "chunk"]
    graph_hits = [h for h in all_hits if h.get("source_type") == "graph"]

    # ── Chunk 去重：同一 chunk_id 保留最高分 ──
    # 多子问题可能命中同一个 chunk，score 由 search-engine 计算，保留最高分避免重复推荐
    seen_chunks: dict[str, dict] = {}
    for h in chunk_hits:
        cid = h.get("chunk_id")
        if cid is None:
            continue
        if cid not in seen_chunks or h.get("score", 0) > seen_chunks[cid].get(
            "score", 0
        ):
            seen_chunks[cid] = h

    fused: list[dict] = sorted(
        seen_chunks.values(), key=lambda h: h.get("score", 0), reverse=True
    )
    top_k = _settings.fusion_top_k
    fused = fused[:top_k]

    # ── Chunk 上下文格式化：[N] 标记（1-based，与 citation 节点的正则匹配对齐）──
    blocks: list[str] = []
    for i, h in enumerate(fused):
        blocks.append(f"[{i + 1}] {h['text']}")
    fused_context = "\n\n".join(blocks) if blocks else "（未检索到相关知识）"

    # ── Graph 上下文去重合并 ──
    fused_graph_context = _merge_graph_results(graph_hits)

    info(
        SERVICE,
        "fusion complete",
        trace_id,
        chunk_input=len(chunk_hits),
        chunk_fused=len(fused),
        graph_input=len(graph_hits),
        graph_entities=len(fused_graph_context.get("entities", [])),
        graph_edges=len(fused_graph_context.get("edges", [])),
    )

    return {
        "fused_context": fused_context,
        "fused_results": fused,
        "fused_graph_context": fused_graph_context,
    }


def _merge_graph_results(graph_hits: list[dict]) -> dict:
    """合并多源图谱结果：实体按 id 去重，边按 (from, to, relation) 去重。

    Args:
        graph_hits: 图谱检索命中列表，每条含 entities 和 edges

    Returns:
        dict: {"entities": list[dict], "edges": list[dict]}
    """
    entities: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}

    for hit in graph_hits:
        for e in hit.get("entities", []):
            eid = e.get("id", e.get("name", ""))
            if eid and eid not in entities:
                entities[eid] = {
                    "id": e.get("id", ""),
                    "type": e.get("type", ""),
                    "name": e.get("name", ""),
                    "description": e.get("description", ""),
                }
        for edge in hit.get("edges", []):
            key = (edge.get("from", ""), edge.get("to", ""), edge.get("relation", ""))
            if key not in edges:
                edges[key] = {
                    "from": edge.get("from", ""),
                    "to": edge.get("to", ""),
                    "relation": edge.get("relation", ""),
                    "keywords": edge.get("keywords", ""),
                    "description": edge.get("description", ""),
                }

    return {
        "entities": list(entities.values()),
        "edges": list(edges.values()),
    }
