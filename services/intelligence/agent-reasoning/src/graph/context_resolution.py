"""Context Resolution 节点 — 对子问题进行指代消解。

利用对话历史，将子问题中的代词（"它"、"上面那个"）和模糊引用
（"之前那本规范"）替换为具体实体名称，产出 resolved_query。
"""

import json

from src.graph.state import AgentState
from src.llm.client import LLMClient
from src.llm.prompts import CONTEXT_RESOLUTION_SYSTEM
from src.settings import Settings
from src.store.conversation import InMemoryConversationStore
from daduhe_common import info, warn, error as log_error

SERVICE = "agent-reasoning"


async def context_resolution_node(
    state: AgentState,
    llm: LLMClient | None = None,
    store: InMemoryConversationStore | None = None,
    settings: Settings | None = None,
) -> dict:
    """对需要指代消解的子问题进行上下文消解。

    仅当子问题标记了 requires_history=True 或提供了 history_reference 时
    才调用 LLM 做消解，否则直接透传原始 question 作为 resolved_query。

    Args:
        state: 当前 AgentState，含 sub_questions、conversation_id
        llm: LLM 客户端
        store: 会话存储，用于获取对话历史
        settings: 服务配置

    Returns:
        dict: {"sub_questions": [含 resolved_query + resolved_context 的子问题列表]}
        LLM 失败时降级为原始 question
    """
    trace_id = state.get("trace_id", "")
    conversation_id = state.get("conversation_id", "")
    sub_questions = state.get("sub_questions", [])

    _llm = llm or LLMClient(settings)
    _settings = settings or Settings()

    # ── 快速判断：所有子问题都不需要消解时直接透传，省一次 LLM 调用 ──
    needs_resolution = any(
        sq.get("requires_history") or sq.get("history_reference")
        for sq in sub_questions
    )
    if not needs_resolution and sub_questions:
        for sq in sub_questions:
            if "resolved_query" not in sq or sq["resolved_query"] is None:
                sq["resolved_query"] = sq["question"]
            if "resolved_context" not in sq:
                sq["resolved_context"] = None
        info(SERVICE, "context resolution skipped (no history needed)", trace_id)
        return {"sub_questions": sub_questions}

    # ── 获取对话历史 ──
    history_text = ""
    if store is not None:
        try:
            recent = await store.get_recent(conversation_id, turns=5)
            if recent:
                lines = [f"{m.role}: {m.content}" for m in recent]
                history_text = "对话历史:\n" + "\n".join(lines)
        except Exception:
            pass

    # ── 构建 LLM 提示 ──
    sq_list = []
    for sq in sub_questions:
        sq_list.append(
            {
                "id": sq["id"],
                "question": sq["question"],
                "requires_history": sq.get("requires_history", False),
                "history_reference": sq.get("history_reference"),
            }
        )
    sq_json = json.dumps(sq_list, ensure_ascii=False, indent=2)

    if history_text:
        user_message = (
            f"{history_text}\n\n"
            f"用户当前问题: {state['query']}\n\n"
            f"待消解的子问题:\n{sq_json}\n\n"
            f"请对每个子问题进行指代消解，输出 JSON。"
        )
    else:
        user_message = (
            f"用户问题: {state['query']}\n\n"
            f"待消解的子问题:\n{sq_json}\n\n"
            f"请对每个子问题进行指代消解，输出 JSON。如果没有需要消解的指代，"
            f"resolved_query 等于原始 question。"
        )

    messages = [
        {"role": "system", "content": CONTEXT_RESOLUTION_SYSTEM},
        {"role": "user", "content": user_message},
    ]

    info(SERVICE, "context resolution running", trace_id, sub_count=len(sub_questions))

    # ── 调用 LLM ──
    try:
        result = await _llm.completion(
            model=_settings.default_model,
            messages=messages,
            temperature=_settings.context_resolution_temperature,
            max_tokens=_settings.context_resolution_max_tokens,
            priority="realtime",
        )
    except Exception as exc:
        log_error(SERVICE, "context resolution LLM failed", trace_id, error=str(exc))
        return _fallback(sub_questions, trace_id)

    # ── 解析 LLM 响应 ──
    try:
        parsed = _extract_json(result["content"])
        resolved_list = parsed.get("resolved_questions", [])
    except (json.JSONDecodeError, KeyError) as exc:
        log_error(
            SERVICE, "context resolution JSON parse failed", trace_id, error=str(exc)
        )
        return _fallback(sub_questions, trace_id)

    # ── 合并消解结果 ──
    resolved_map = {r["id"]: r for r in resolved_list}
    for sq in sub_questions:
        sq_id = sq["id"]
        if sq_id in resolved_map:
            r = resolved_map[sq_id]
            sq["resolved_query"] = r.get("resolved_query", sq["question"])
            sq["resolved_context"] = r.get("resolved_context")
        else:
            sq["resolved_query"] = sq["question"]
            sq["resolved_context"] = None

    info(
        SERVICE,
        "context resolution complete",
        trace_id,
        resolved_count=sum(
            1 for sq in sub_questions if sq.get("resolved_query") != sq.get("question")
        ),
    )

    return {"sub_questions": sub_questions}


def _fallback(sub_questions: list[dict], trace_id: str) -> dict:
    """LLM 失败时的降级策略：将 resolved_query 设为原始 question。

    Args:
        sub_questions: 子问题列表
        trace_id: 链路追踪 ID

    Returns:
        dict: {"sub_questions": [resolve_query=原始question 的子问题]}
    """
    warn(
        SERVICE,
        "context resolution fallback",
        trace_id,
        reason="LLM failed, using original questions",
    )
    # 降级：LLM 失败时不对所有子问题做指代消解，直接使用原始 question
    for sq in sub_questions:
        sq["resolved_query"] = sq["question"]
        sq["resolved_context"] = None
    return {"sub_questions": sub_questions}


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON，自动处理 markdown 代码围栏。

    Args:
        text: LLM 原始响应文本

    Returns:
        dict: 解析后的 JSON 字典
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)
