"""Router — 条件边路由：根据 query_type 决定下一节点。

chitchat 类型跳过检索链路直接进入生成节点，其他类型走完整检索流水线。
"""

from src.graph.state import AgentState


def route_after_supervisor(state: AgentState) -> str:
    """根据 Supervisor 的 query_type 决定路由目标。

    Args:
        state: 当前 AgentState，含 query_type 字段

    Returns:
        str: 下一节点名称——"generator"（闲聊短路）或 "context_resolution"（检索链路）
    """
    query_type = state.get("query_type", "")
    if query_type == "chitchat":
        return "generator"
    return "context_resolution"
