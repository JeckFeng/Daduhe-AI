"""LangGraph AgentState 与 SubQuestion — 贯穿 Graph 节点的共享状态。

SubQuestion 采用逐节点富化模式（State Enrichment pattern）：
    1. Supervisor → (id, question, topic, requires_history)
    2. Context Resolution → (+resolved_query, resolved_context)
    3. call_tools → (+results)

AgentState 承载完整流水线的输入输出，由 LangGraph 管理的 messages
字段支持多轮对话。
"""

from typing import Annotated, TypedDict, Optional

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    """Supervisor 拆解的子问题，在流水线各节点逐步富化。

    Attributes:
        id: 唯一标识，如 "q1"、"q2"
        question: 原始子问题文本
        topic: 主题摘要，用于检索定向
        requires_history: 是否需要利用对话历史做指代消解
        history_reference: 需要在历史中消解什么的描述
        resolved_query: 指代消解后的查询文本
        resolved_context: 从历史中消解出的结构化实体
        results: 检索结果列表
    """

    id: str = Field(description="唯一标识，如 'q1'、'q2'")
    question: str = Field(description="原始子问题文本")
    topic: str = Field(description="主题摘要，用于检索定向")

    requires_history: bool = Field(
        default=False,
        description="是否需要指代消解",
    )
    history_reference: Optional[str] = Field(
        default=None,
        description="需要在历史中消解的内容描述",
    )

    # ── Context Resolution 富化 ──
    resolved_query: Optional[str] = Field(
        default=None,
        description="指代消解后的查询文本",
    )
    resolved_context: Optional[dict] = Field(
        default=None,
        description="从对话历史中消解出的结构化实体",
    )

    # ── call_tools 富化 ──
    results: list[dict] = Field(
        default_factory=list,
        description="此子问题的检索结果",
    )


class AgentState(TypedDict):
    """多源 RAG 流水线共享状态。

    ┌─────────────────┬──────────────────────────────────────┐
    │ 字段            │ 填充节点                             │
    ├─────────────────┼──────────────────────────────────────┤
    │ query           │ Chat 路由（初始输入）                │
    │ conversation_id │ Chat 路由                            │
    │ trace_id        │ TraceMiddleware / Chat 路由          │
    │ retrieval_mode  │ Chat 路由                            │
    │ query_type      │ Supervisor                           │
    │ sub_questions   │ Supervisor → ContextRes → call_tools │
    │ fused_context   │ Fusion                               │
    │ answer          │ Generator                            │
    │ citations       │ Citation                             │
    │ messages        │ 所有节点（LangGraph add_messages）   │
    └─────────────────┴──────────────────────────────────────┘
    """

    # ── 输入（Chat 路由）──
    query: str
    conversation_id: str
    trace_id: str
    retrieval_mode: str

    # ── Supervisor 输出 ──
    query_type: str
    sub_questions: list[dict]  # SubQuestion.model_dump() 列表

    # ── Fusion 输出 ──
    fused_context: str
    fused_results: list[dict]  # 去重排序后的 chunk 结果，供 Citation 索引
    fused_graph_context: dict  # 合并后的 entities + edges

    # ── Generator 输出 ──
    answer: str

    # ── Citation 输出 ──
    citations: list[dict]

    # ── 对话历史（多轮，LangGraph 管理）──
    messages: Annotated[list[BaseMessage], add_messages]
