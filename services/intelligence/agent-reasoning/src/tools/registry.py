"""工具注册中心 — 工具的注册、发现和并行执行。

ToolRegistry 是工具层的核心编排器：
- 按 source_type 解析匹配的工具集合
- 支持单工具执行和并行多工具执行
- 统一错误处理，单个工具失败不影响其他工具
"""

import asyncio
from typing import Optional

from .base import ToolDef, ToolResult, ToolHandler
from daduhe_common import info, error as log_error

SERVICE = "agent-reasoning"


class ToolRegistry:
    """工具注册中心，管理所有可用工具的定义和执行。

    使用方式::

        registry = ToolRegistry()
        registry.register(
            ToolDef(name="search_engine", ...),
            handler=search_engine_handler,
        )
        tools = registry.resolve(["chunk", "graph"])
        results = await registry.execute_many(tools, trace_id, query="...")
    """

    def __init__(self) -> None:
        """初始化空的工具注册表。"""
        self._tools: dict[str, ToolDef] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, tool: ToolDef, handler: ToolHandler) -> None:
        """注册一个工具及其执行处理器。

        Args:
            tool: 工具定义（名称、描述、来源类型等）
            handler: 异步执行函数，接收关键字参数返回 ToolResult
        """
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

    def get_def(self, name: str) -> Optional[ToolDef]:
        """按名称获取工具定义。

        Args:
            name: 工具名称

        Returns:
            ToolDef | None: 工具定义，不存在时返回 None
        """
        return self._tools.get(name)

    def list_defs(self) -> list[ToolDef]:
        """列出所有已注册工具的定义。

        Returns:
            list[ToolDef]: 所有工具定义列表
        """
        return list(self._tools.values())

    def resolve(self, source_types: list[str]) -> list[str]:
        """按来源类型解析匹配的工具名称列表。

        筛选出 source_type 在 source_types 列表中的工具。

        Args:
            source_types: 来源类型列表，如 ["chunk", "graph"]

        Returns:
            list[str]: 匹配的工具名称列表
        """
        return [
            name for name, t in self._tools.items() if t.source_type in source_types
        ]

    async def execute(
        self,
        tool_name: str,
        trace_id: str,
        **params,
    ) -> ToolResult:
        """执行单个工具。

        工具执行期间出现的异常会被捕获并封装在 ToolResult.error 中，
        不会向上层抛出。

        Args:
            tool_name: 工具名称
            trace_id: 链路追踪 ID
            **params: 传递给工具 handler 的关键字参数

        Returns:
            ToolResult: 工具执行结果，含状态和数据
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return ToolResult(
                source_type="unknown",
                tool_name=tool_name,
                results=[],
                total_hits=0,
                error=f"Tool not found: {tool_name}",
            )
        try:
            info(SERVICE, "tool executing", trace_id, tool=tool_name)
            result = await handler(**params)
            return result
        except Exception as exc:
            log_error(SERVICE, f"tool failed: {tool_name}", trace_id, error=str(exc))
            return ToolResult(
                source_type=self._tools[tool_name].source_type,
                tool_name=tool_name,
                results=[],
                total_hits=0,
                error=str(exc),
            )

    async def execute_many(
        self,
        tool_names: list[str],
        trace_id: str,
        **params,
    ) -> list[ToolResult]:
        """并行执行多个工具。

        所有工具通过 asyncio.gather 并发执行，每个工具独立容错。

        Args:
            tool_names: 待执行工具名称列表
            trace_id: 链路追踪 ID
            **params: 传递给每个工具 handler 的关键字参数

        Returns:
            list[ToolResult]: 各工具执行结果列表，顺序与 tool_names 一致
        """
        tasks = [self.execute(name, trace_id, **params) for name in tool_names]
        return list(await asyncio.gather(*tasks))
