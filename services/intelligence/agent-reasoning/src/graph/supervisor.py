"""Supervisor 节点 — LLM 驱动的查询分析与意图分类。

负责分析用户问题，归类为 4 种类型之一，并将复合问题拆解为子问题列表。
是 LangGraph 流水线的入口节点。
"""

import json

from src.graph.state import AgentState
from src.llm.client import LLMClient
from src.llm.prompts import SUPERVISOR_SYSTEM
from src.settings import Settings
from src.store.conversation import InMemoryConversationStore
from daduhe_common import info, error as log_error

SERVICE = "agent-reasoning"


async def supervisor_node(
    state: AgentState,
    llm: LLMClient | None = None,
    store: InMemoryConversationStore | None = None,
    settings: Settings | None = None,
) -> dict:
    """分析用户查询，分类意图并拆解为子问题。

    查询类型：
    - chitchat: 问候、自我介绍等非专业闲聊
    - spec_lookup: 指向具体规范条文的查询
    - knowledge_qa: 需要领域知识的专业问题
    - comparison: 多个实体的对比类问题

    Args:
        state: LangGraph 共享状态，含 query、trace_id、conversation_id
        llm: LLM 客户端，为 None 时自动创建
        store: 会话存储，用于获取近期对话历史
        settings: 服务配置

    Returns:
        dict: {"query_type": str, "sub_questions": list[dict]}
        LLM 失败时通过 _error 标记或在 sub_questions 中降级为单子问题
    """
    query = state["query"]
    trace_id = state.get("trace_id", "")
    conversation_id = state.get("conversation_id", "")

    _llm = llm or LLMClient(settings)
    _settings = settings or Settings()

    # ── 构建消息：注入近期对话历史 ──
    history_text = ""
    if store is not None:
        try:
            recent = await store.get_recent(conversation_id, turns=5)
            if recent:
                lines = [f"{m.role}: {m.content}" for m in recent]
                history_text = (
                    "近期对话历史（仅用于语义判断，不做指代消解）:\n" + "\n".join(lines)
                )
        except Exception:
            pass

    if history_text:
        user_message = f"{history_text}\n\n用户当前问题: {query}\n\n请分析并输出 JSON。"
    else:
        user_message = f"用户问题: {query}\n\n请分析并输出 JSON。"

    messages = [
        {"role": "system", "content": SUPERVISOR_SYSTEM},
        {"role": "user", "content": user_message},
    ]

    info(SERVICE, "supervisor analysing", trace_id, query=query[:80])

    # ── 调用 LLM ──
    try:
        result = await _llm.completion(
            model=_settings.default_model,
            messages=messages,
            temperature=_settings.supervisor_temperature,
            max_tokens=_settings.supervisor_max_tokens,
            priority="realtime",
        )
    except Exception as exc:
        log_error(SERVICE, "supervisor LLM failed", trace_id, error=str(exc))
        return {
            "query_type": "",
            "sub_questions": [],
            "_error": f"Supervisor LLM call failed: {exc}",
        }

    # ── 解析 JSON（LLM 可能用 markdown 代码块包裹）──
    raw = result["content"]
    try:
        parsed = _extract_json(raw)
        query_type = parsed.get("query_type", "knowledge_qa")
        sub_questions = parsed.get("sub_questions", [])
    except (json.JSONDecodeError, KeyError) as exc:
        log_error(
            SERVICE,
            "supervisor JSON parse failed",
            trace_id,
            error=str(exc),
            raw=raw[:200],
        )
        # 降级：LLM 解析失败时退化为 knowledge_qa 单子问题，避免整个请求中断
        return {
            "query_type": "knowledge_qa",
            "sub_questions": [
                {
                    "id": "q1",
                    "question": query,
                    "topic": "通用",
                    "requires_history": False,
                    "history_reference": None,
                }
            ],
            "_parse_error": str(exc),
        }

    # ── 校验：确保 query_type 在合法枚举内 ──
    valid_types = {"chitchat", "spec_lookup", "knowledge_qa", "comparison"}
    if query_type not in valid_types:
        query_type = "knowledge_qa"

    # 空子问题降级：直接将用户问题包装为 q1，保证后续节点有内容可检索
    if not sub_questions:
        sub_questions = [
            {
                "id": "q1",
                "question": query,
                "topic": "通用",
                "requires_history": False,
                "history_reference": None,
            }
        ]

    for sq in sub_questions:
        sq.setdefault("requires_history", False)
        sq.setdefault("history_reference", None)

    info(
        SERVICE,
        "supervisor complete",
        trace_id,
        query_type=query_type,
        sub_count=len(sub_questions),
    )

    return {
        "query_type": query_type,
        "sub_questions": sub_questions,
    }


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON，自动处理 markdown 代码围栏。

    支持 `` ```json ... ``` `` 和 `` ``` ... ``` `` 两种格式。

    Args:
        text: LLM 原始响应文本

    Returns:
        dict: 解析后的 JSON 字典
    """
    text = text.strip()
    # 处理 markdown 代码围栏 ```json ... ``` 或 ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行（```json 或 ```）
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 去掉末行（```）
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)
