"""LLMProvider 协议：LLM 后端的抽象接口。

定义了 completion() 方法签名，任何 LLM 客户端实现此协议后均可被抽取管线使用。
默认实现为 AgentReasoningLLMClient。
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 补全后端的协议抽象。

    定义了 completion() 方法签名。默认实现为 AgentReasoningLLMClient
    （通过 agent-reasoning 网关 /api/v1/completion 调用 LLM）。

    可通过 isinstance(client, LLMProvider) 进行运行时检查。
    """

    async def completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
        model: str = "vllm-local",
    ) -> dict:
        """执行 LLM 补全调用。

        Args:
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            response_format: 可选的 JSON schema 约束。
            model: 模型名称。

        Returns:
            dict: {"content": str, "model": str, "usage": dict, "latency_ms": float}
        """
        ...
