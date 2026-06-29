"""call_tools 节点 — 对每个子问题并行执行所有匹配工具的检索。

工具通过 ToolRegistry 按 source_type 解析，所有匹配工具对每个子问题
并行执行。单个子问题或工具失败仅记录警告，不影响其他检索。
"""

import asyncio

from src.graph.state import AgentState, SubQuestion
from src.tools.registry import ToolRegistry
from src.settings import Settings
from daduhe_common import info, warn

SERVICE = "agent-reasoning"


async def call_tools_node(
    state: AgentState,
    registry: ToolRegistry,
    settings: Settings | None = None,
) -> dict:
    """对所有子问题执行多工具并行检索。

    当前硬编码解析 "chunk" 和 "graph" 两种 source_type，对应
    search_engine 和 graph_search 两个工具。每个子问题并行启动检索
    协程（受 asyncio.gather 保障），结果写回 sub_question.results。

    Args:
        state: 当前 AgentState，含 sub_questions
        registry: 工具注册中心
        settings: 服务配置

    Returns:
        dict: {"sub_questions": [enriched SubQuestion dicts]}
    """
    _settings = settings or Settings()
    trace_id = state.get("trace_id", "")
    sub_questions_raw = state.get("sub_questions", [])

    # 当前硬编码所有 source_type，后续由 Supervisor 按需选择
    source_types = ["chunk", "graph"]
    tool_names = registry.resolve(source_types)

    if not tool_names:
        warn(SERVICE, "no tools resolved", trace_id)
        return {"sub_questions": sub_questions_raw}

    async def _retrieve_one(sq_dict: dict) -> dict:
        """对单个子问题执行所有匹配工具的检索。

        Args:
            sq_dict: SubQuestion 的字典表示

        Returns:
            dict: 更新后的子问题字典（含 results）
        """
        sq = SubQuestion.model_validate(sq_dict)
        # 富化链：resolved_query（消解后）> question（原始），逐节点叠加
        query = sq.resolved_query or sq.question

        all_results: list[dict] = []
        for tool_name in tool_names:
            try:
                result = await registry.execute(
                    tool_name,
                    trace_id,
                    query=query,
                    top_k=_settings.fusion_top_k,
                )
                if result.error:
                    warn(
                        SERVICE,
                        "tool retrieval failed",
                        trace_id,
                        sub_id=sq.id,
                        tool=tool_name,
                        error=result.error,
                    )
                # 将每个工具的结果追加到同一个列表，后续由 fusion 统一去重
                all_results.extend(result.results)
            except Exception as exc:
                warn(
                    SERVICE,
                    "tool retrieval exception",
                    trace_id,
                    sub_id=sq.id,
                    tool=tool_name,
                    error=str(exc),
                )

        sq.results = all_results
        info(
            SERVICE,
            "sub-question retrieved",
            trace_id,
            sub_id=sq.id,
            query=query[:80],
            hits=len(sq.results),
        )
        return sq.model_dump()

    # 所有子问题并行检索，asyncio.gather 保证全部完成或第一个异常
    tasks = [_retrieve_one(sq) for sq in sub_questions_raw]
    updated = list(await asyncio.gather(*tasks))

    return {"sub_questions": updated}
