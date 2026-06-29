"""工具抽象层 — 统一的工具定义、结果和注册机制。

每个数据源或能力都以 Tool 的形式封装，提供统一接口供 Agent 调用。
新增数据源只需在此注册，无需修改 Graph 节点代码。

核心概念：
- ToolDef: 工具的元数据描述（名称、来源类型、参数 schema）
- ToolResult: 工具执行结果的统一封装
- ToolHandler: 工具执行函数签名
"""

from collections.abc import Awaitable
from typing import Any, Callable

from pydantic import BaseModel


class ToolDef(BaseModel):
    """工具定义 — Supervisor 用于决策是否调用的元数据。

    Attributes:
        name: 工具唯一名称，如 "search_engine"、"graph_search"
        description: 工具功能描述，供 LLM 理解何时使用
        parameters: JSON Schema 格式的参数定义
        source_type: 数据来源类型，"chunk"、"rule"、"graph" 或 "param"
    """

    name: str
    description: str
    parameters: dict[str, Any] = {}
    source_type: str  # "chunk" | "rule" | "graph" | "param"


class ToolResult(BaseModel):
    """工具执行结果的统一封装。

    Fusion 节点负责对不同工具的 results 做 schema 对齐、去重和排序。

    Attributes:
        source_type: 数据来源类型
        tool_name: 工具名称
        results: 检索命中结果列表
        total_hits: 命中总数
        latency_ms: 执行耗时（毫秒）
        error: 错误信息，成功时为 None
    """

    source_type: str
    tool_name: str
    results: list[dict[str, Any]]
    total_hits: int
    latency_ms: float = 0
    error: str | None = None


ToolHandler = Callable[..., Awaitable[ToolResult]]
"""异步工具执行函数签名。接收关键字参数，返回 ToolResult。"""
