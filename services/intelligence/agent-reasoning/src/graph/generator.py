"""Generator 节点 — LLM 答案生成，支持流式和非流式两种模式。

使用融合后的检索上下文（chunk + graph）调用 LLM 生成带引用的最终答案。
流式模式通过 LangGraph stream writer 逐 token 推送；非流式模式直接返回完整答案。
"""

from src.graph.state import AgentState
from src.llm.client import LLMClient
from src.llm.prompts import GENERATOR_SYSTEM
from src.settings import Settings
from daduhe_common import info, error as log_error

SERVICE = "agent-reasoning"


async def generator_node(
    state: AgentState,
    llm: LLMClient | None = None,
    settings: Settings | None = None,
) -> dict:
    """基于融合上下文生成最终答案。

    支持两种调用方式：
    - astream(): 通过 LangGraph get_stream_writer 逐 token 推送
    - ainvoke(): 同步等待完整响应后返回

    Args:
        state: 当前 AgentState，含 query、fused_context、fused_graph_context 等
        llm: LLM 客户端
        settings: 服务配置

    Returns:
        dict: {"answer": str} 完整答案文本
    """
    query = state["query"]
    fused_context = state.get("fused_context", "")
    fused_graph_context = state.get("fused_graph_context", {})
    trace_id = state.get("trace_id", "")
    query_type = state.get("query_type", "")
    sub_questions = state.get("sub_questions", [])

    _llm = llm or LLMClient(settings)
    _settings = settings or Settings()

    # ── 构建图谱上下文文本 ──
    kg_context_text = _format_kg_context(fused_graph_context)

    # ── 构建用户消息 ──
    user_message = _build_user_message(
        query=query,
        query_type=query_type,
        fused_context=fused_context,
        kg_context_text=kg_context_text,
        sub_questions=sub_questions,
    )

    messages = [
        {"role": "system", "content": GENERATOR_SYSTEM},
        {"role": "user", "content": user_message},
    ]

    info(SERVICE, "generator calling LLM", trace_id, query=query[:80])

    # ── 流式模式：仅在 graph.astream() 上下文中可用 ──
    # _try_get_stream_writer 在 ainvoke() 调用时返回 None，自动走非流式路径
    writer = _try_get_stream_writer()
    if writer is not None:
        full_answer: list[str] = []
        try:
            async for token in _llm.completion_stream(
                model=_settings.default_model,
                messages=messages,
                temperature=_settings.generator_temperature,
                max_tokens=_settings.generator_max_tokens,
                priority="realtime",
            ):
                full_answer.append(token)
                writer({"event": "answer_chunk", "data": token})
            return {"answer": "".join(full_answer)}
        except Exception as exc:
            log_error(SERVICE, "generator stream failed", trace_id, error=str(exc))
            writer({"event": "error", "data": str(exc)})
            return {"answer": f"抱歉，系统暂时无法处理您的问题。（错误: {exc}）"}
    else:
        # ── 非流式模式 ──
        try:
            result = await _llm.completion(
                model=_settings.default_model,
                messages=messages,
                temperature=_settings.generator_temperature,
                max_tokens=_settings.generator_max_tokens,
                priority="realtime",
            )
            return {"answer": result["content"]}
        except Exception as exc:
            log_error(SERVICE, "generator LLM failed", trace_id, error=str(exc))
            return {"answer": f"抱歉，系统暂时无法处理您的问题。（错误: {exc}）"}


def _try_get_stream_writer():
    """尝试获取 LangGraph 流写入器。

    仅在 graph.astream() 上下文中可获取；否则返回 None。

    Returns:
        流写入器 callable 或 None
    """
    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()
    except (RuntimeError, ImportError):
        return None


def _build_user_message(
    query: str,
    query_type: str,
    fused_context: str,
    kg_context_text: str,
    sub_questions: list[dict],
) -> str:
    """组装发送给 LLM 的用户消息。

    根据 query_type 选择不同模板：
    - chitchat: 闲聊引导模式
    - 其他: 综合图谱上下文和检索参考资料的问答模式

    Args:
        query: 用户原始问题
        query_type: 查询类型
        fused_context: chunk 检索上下文（带 [N] 标记）
        kg_context_text: 图谱上下文文本
        sub_questions: 子问题列表

    Returns:
        str: 组装好的用户消息文本
    """
    # 闲聊模式：不引用资料，仅做友好回复
    if query_type == "chitchat":
        return (
            "这是用户和你的一次闲聊互动。\n"
            f"用户说: {query}\n\n"
            "请以水工建筑物缺陷诊疗专家助手的身份，进行友好、专业的简短回复。"
        )

    topics = [sq.get("topic", sq.get("question", "")) for sq in sub_questions]
    topics_str = "、".join(topics) if topics else "通用"

    parts = [f"用户问题: {query}", f"涉及主题: {topics_str}"]

    if kg_context_text:
        parts.append(f"知识图谱上下文（实体与关系）:\n{kg_context_text}")

    # fused_context 以 "（未检索到" 开头时说明 fusion 无结果，不引用
    if fused_context and not fused_context.startswith("（未检索到"):
        parts.append(f"检索到的参考资料:\n{fused_context}")
        parts.append("请综合知识图谱和参考资料回答问题，并在引用处标注 [N] 标记。")
    else:
        parts.append("注意: 未检索到相关知识，请诚实告知用户，不要编造信息。")

    return "\n\n".join(parts)


def _format_kg_context(graph_context: dict) -> str:
    """将图谱上下文格式化为 LightRAG 风格的文本表示。

    Args:
        graph_context: {"entities": [...], "edges": [...]}

    Returns:
        str: 格式化的图谱上下文文本，无实体无边时返回空字符串
    """
    entities = graph_context.get("entities", []) if graph_context else []
    edges = graph_context.get("edges", []) if graph_context else []

    if not entities and not edges:
        return ""

    lines: list[str] = []

    if entities:
        lines.append("Entities:")
        for e in entities:
            name = e.get("name", "")
            etype = e.get("type", "")
            desc = e.get("description", "")
            lines.append(f'("{name}", "{etype}"): "{desc}"')

    if edges:
        if lines:
            lines.append("")
        lines.append("Relationships:")
        for edge in edges:
            src = edge.get("from", "")
            tgt = edge.get("to", "")
            rel = edge.get("relation", "")
            kw = edge.get("keywords", "")
            desc = edge.get("description", "")
            lines.append(f'("{src}", "{tgt}"): "{rel}", {kw}, "{desc}"')

    return "\n".join(lines)
