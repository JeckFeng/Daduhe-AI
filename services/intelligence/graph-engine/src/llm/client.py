"""LLM 客户端：通过 agent-reasoning 网关 /api/v1/completion 统一调用 LLM。

所有 LLM 调用均通过此客户端，携带 caller="graph-engine" 和 X-Trace-Id 链路追踪头。
"""

from uuid import uuid4

import httpx

from src.settings import Settings


class AgentReasoningLLMClient:
    """通过 agent-reasoning（llm-gateway）的 /api/v1/completion 调用 LLM。

    Attributes:
        _url: LLM 网关地址。
        _timeout: HTTP 请求超时时间（秒），batch 优先级为 120s。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 LLM 客户端。

        Args:
            settings: 应用配置，读取 llm_gateway_url。
        """
        self._settings = settings
        self._url = f"{settings.llm_gateway_url.rstrip('/')}/api/v1/completion"
        self._timeout = 120.0

    async def completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
        model: str = "vllm-local",
        max_tokens: int | None = None,
    ) -> dict:
        """调用 LLM 执行单轮对话补全。

        Args:
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            response_format: 可选的 JSON schema 约束。
            model: 模型名称，默认 vllm-local。
            max_tokens: 最大输出 token 数，默认使用配置中的 extraction_llm_max_tokens。

        Returns:
            dict: {"content": str, "model": str, "usage": dict, "latency_ms": float}

        Raises:
            RuntimeError: LLM 返回非 0 code 时抛出。
        """
        trace_id = f"graph-engine-{uuid4()}"
        messages = [{"role": "user", "content": user_prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                self._url,
                json={
                    "model": model,
                    "messages": messages,
                    "caller": "graph-engine",
                    "priority": "batch",
                    "max_tokens": max_tokens
                    or self._settings.extraction_llm_max_tokens,
                },
                headers={"X-Trace-Id": trace_id},
            )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"LLM call failed: code={data.get('code')} message={data.get('message')}"
            )
        return data["data"]
