"""Citation 节点 — 从答案中提取 [N] 引用标记，映射到 chunk 元数据。

构建符合 ICD-03 §6.1 规范的引用数组，供前端渲染可点击的引用角标。
"""

import re

from src.graph.state import AgentState
from src.settings import Settings
from daduhe_common import info

SERVICE = "agent-reasoning"


async def citation_node(
    state: AgentState,
    settings: Settings | None = None,
) -> dict:
    """从答案文本解析 [N] 标记，构建引用数组。

    通过正则提取答案中的 [1]、[2] 等标记，映射到 fused_results
    中对应索引的 chunk，生成含 doc_title、section、page、download_url
    的完整引用对象。

    Args:
        state: 当前 AgentState，含 answer、fused_results
        settings: 服务配置

    Returns:
        dict: {"citations": [{"index": int, "doc_title": str, ...}]}
    """
    _settings = settings or Settings()
    trace_id = state.get("trace_id", "")
    answer = state.get("answer", "")
    fused_results = state.get("fused_results", [])

    # ── 从答案中提取 [N] 标记 ──
    # 匹配 LLM 在答案中标注的引用编号，如 "根据规范 [1]"、"采用灌浆法 [2]"
    marker_ids: set[int] = set()
    for m in re.finditer(r"\[(\d+)\]", answer):
        marker_ids.add(int(m.group(1)))

    if not marker_ids or not fused_results:
        return {"citations": []}

    base_url = _settings.search_engine_url.rstrip("/")

    # ── 构建引用数组：[N] → fused_results[N-1] 映射 ──
    # fused_results 是 0-based，LLM 输出的 [N] 是 1-based
    citations: list[dict] = []
    for n in sorted(marker_ids):
        idx = n - 1  # 1-based → 0-based
        if idx < 0 or idx >= len(fused_results):
            continue

        hit = fused_results[idx]
        meta = hit.get("metadata", {})

        section_parts: list[str] = []
        if meta.get("section_number"):
            section_parts.append(meta["section_number"])
        if meta.get("section_title"):
            section_parts.append(meta["section_title"])
        section = " ".join(section_parts)

        doc_id = meta.get("doc_id", "")
        download_url = f"{base_url}/api/v1/documents/{doc_id}/download"

        excerpt = hit.get("text", "")[:150]

        citations.append(
            {
                "index": n,
                "chunk_id": hit.get("chunk_id", ""),
                "doc_title": meta.get("title", "未知"),
                "doc_type": meta.get("doc_type", ""),
                "section": section,
                "page": meta.get("page_number"),
                "download_url": download_url,
                "excerpt": excerpt,
            }
        )

    info(SERVICE, "citation built", trace_id, count=len(citations))
    return {"citations": citations}
