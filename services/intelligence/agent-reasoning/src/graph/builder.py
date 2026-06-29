"""Graph 构建器 — 组装 LangGraph StateGraph 流水线。

拓扑结构::

    START → supervisor → [条件路由]
                            │
                            ├─ chitchat → generator → END
                            │
                            └─ 其他 → context_resolution → call_tools → fusion
                                        → generator → citation → END

6 个节点以 StateGraph 形式编排，2 个条件路由，工具通过 ToolRegistry 注册。
"""

from functools import partial

from langgraph.graph import StateGraph, END

from src.graph.state import AgentState
from src.graph.supervisor import supervisor_node
from src.graph.router import route_after_supervisor
from src.graph.context_resolution import context_resolution_node
from src.graph.call_tools import call_tools_node
from src.graph.fusion import fusion_node
from src.graph.generator import generator_node
from src.graph.citation import citation_node
from src.tools.registry import ToolRegistry
from src.tools.search_engine_tool import SEARCH_ENGINE_TOOL, search_engine_handler
from src.tools.graph_search import GRAPH_SEARCH_TOOL, graph_search_handler
from src.llm.client import LLMClient
from src.settings import Settings
from src.store.conversation import InMemoryConversationStore


def build_graph(
    registry: ToolRegistry | None = None,
    llm: LLMClient | None = None,
    store: InMemoryConversationStore | None = None,
    settings: Settings | None = None,
) -> StateGraph:
    """构建并编译 agent-reasoning 的 LangGraph 流水线。

    节点以 partial 方式注入依赖（LLM、存储、配置），避免全局状态。

    Args:
        registry: 工具注册中心，为 None 时使用默认注册
        llm: LLM 客户端
        store: 会话存储
        settings: 服务配置

    Returns:
        StateGraph: 编译后的可执行图
    """
    if registry is None:
        registry = _default_registry()
    if settings is None:
        settings = Settings()

    graph = StateGraph(AgentState)

    # ── 节点注册 ──
    graph.add_node(
        "supervisor",
        partial(supervisor_node, llm=llm, store=store, settings=settings),
    )
    graph.add_node(
        "context_resolution",
        partial(context_resolution_node, llm=llm, store=store, settings=settings),
    )
    graph.add_node(
        "call_tools",
        partial(call_tools_node, registry=registry),
    )
    graph.add_node("fusion", fusion_node)
    graph.add_node(
        "generator",
        partial(generator_node, llm=llm, settings=settings),
    )
    graph.add_node("citation", citation_node)

    # ── 边：拓扑 = supervisor → [chitchat→generator / 其他→context_resolution→call_tools→fusion→generator] → [citation] → END ──
    graph.set_entry_point("supervisor")

    # 条件路由：chitchat 短路到 generator，跳过检索链
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "context_resolution": "context_resolution",
            "call_tools": "call_tools",
            "generator": "generator",
        },
    )

    # 检索流水线: context_resolution → call_tools → fusion → generator
    graph.add_edge("context_resolution", "call_tools")
    graph.add_edge("call_tools", "fusion")
    graph.add_edge("fusion", "generator")

    # chitchat 跳过 citation（无检索来源可引用）
    graph.add_conditional_edges(
        "generator",
        _route_after_generator,
        {
            "citation": "citation",
            END: END,
        },
    )
    graph.add_edge("citation", END)

    return graph.compile()


def _route_after_generator(state: AgentState) -> str:
    """Generator 之后的路由决策：chitchat 跳过引用节点。

    Args:
        state: 当前 AgentState

    Returns:
        str: "citation" 或 END
    """
    # 闲聊没有检索来源，直接结束，不进入 citation 节点
    if state.get("query_type") == "chitchat":
        return END
    return "citation"


def _default_registry() -> ToolRegistry:
    """创建预加载 search_engine 和 graph_search 的默认工具注册中心。

    Returns:
        ToolRegistry: 含两个默认工具的注册实例
    """
    registry = ToolRegistry()
    registry.register(SEARCH_ENGINE_TOOL, search_engine_handler)
    registry.register(GRAPH_SEARCH_TOOL, graph_search_handler)
    return registry
