"""工具层 — 统一工具注册、发现和执行。

base.py: ToolDef、ToolResult、ToolHandler 抽象定义
registry.py: ToolRegistry 注册中心，支持按 source_type 解析和并行执行
search_engine_tool.py: search-engine 检索工具（source_type="chunk"）
graph_search.py: graph-engine 图谱检索工具（source_type="graph"）
"""

from .base import ToolDef, ToolResult
from .registry import ToolRegistry

__all__ = ["ToolDef", "ToolResult", "ToolRegistry"]
