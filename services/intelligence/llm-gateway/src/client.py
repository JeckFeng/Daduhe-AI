"""OpenAI 兼容 LLM 客户端，支持模型路由。

deepseek-chat → DeepSeek API / vllm-local → 本地 vLLM。
两者均为 OpenAI 兼容接口，使用 openai.AsyncOpenAI 客户端，仅 base_url 不同。
客户端实例按 model 缓存，避免重复创建 AsyncOpenAI 对象。
"""

import time
from typing import AsyncGenerator
from openai import AsyncOpenAI

from src.settings import Settings


class LLMClient:
    """OpenAI 兼容 LLM 客户端工厂，按模型后端路由。

    客户端按 model 缓存到 self._clients dict 中，同一 model 复用同一个 AsyncOpenAI 实例。
    get_host() 返回模型对应的 base_url，用于缓存键计算。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化 LLM 客户端。

        Args:
            settings: 应用配置，None 时使用默认 Settings()。
        """
        self._settings = settings or Settings()
        self._clients: dict[str, AsyncOpenAI] = {}

    def get_host(self, model: str) -> str:
        """返回模型对应的 base_url（用于缓存键区分不同后端）。

        Args:
            model: 模型名称（"vllm-local" 或其他）。

        Returns:
            str: 模型对应的 API base_url。
        """
        if model == "vllm-local":
            return self._settings.vllm_url
        return self._settings.deepseek_api_url

    def _get_client(self, model: str) -> AsyncOpenAI:
        """获取或创建模型对应的 AsyncOpenAI 客户端。

        客户端实例按 model 缓存，避免重复创建。

        Args:
            model: 模型名称。

        Returns:
            AsyncOpenAI: 配置好 base_url 的客户端实例。
        """
        if model not in self._clients:
            if model == "vllm-local":
                # vLLM 不需要 API key
                self._clients[model] = AsyncOpenAI(
                    base_url=self._settings.vllm_url,
                    api_key="none",
                )
            else:
                kwargs = {"base_url": self._settings.deepseek_api_url}
                if self._settings.deepseek_api_key:
                    kwargs["api_key"] = self._settings.deepseek_api_key
                self._clients[model] = AsyncOpenAI(**kwargs)
        return self._clients[model]

    async def completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2000,
        priority: str = "batch",
    ) -> dict:
        """调用 LLM 完成补全（非流式）。

        Args:
            model: 模型名称（"vllm-local" 或 "deepseek-chat"）。
            messages: OpenAI 格式消息列表 [{"role": "user"/"system", "content": "..."}]。
            temperature: 生成温度（0-2），越低越确定。
            max_tokens: 最大生成 token 数。
            priority: "realtime"（30s 超时）或 "batch"（120s 超时）。

        Returns:
            dict: {"content": str, "model": str, "prompt_tokens": int,
                   "completion_tokens": int, "latency_ms": float}
        """
        client = self._get_client(model)
        timeout = (
            self._settings.realtime_timeout
            if priority == "realtime"
            else self._settings.batch_timeout
        )

        # vLLM 使用本地模型文件路径作为 api_model
        api_model = self._settings.vllm_model if model == "vllm-local" else model

        t0 = time.perf_counter()
        resp = await client.chat.completions.create(
            model=api_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000)

        choice = resp.choices[0]
        return {
            "content": choice.message.content or "",
            "model": model,
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            "latency_ms": latency_ms,
        }

    async def completion_stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2000,
        priority: str = "batch",
    ) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token yield。

        调用方负责拼接完整响应和计算 token 统计。

        Args:
            model: 模型名称（"vllm-local" 或 "deepseek-chat"）。
            messages: OpenAI 格式消息列表。
            temperature: 生成温度（0-2）。
            max_tokens: 最大生成 token 数。
            priority: "realtime"（30s 超时）或 "batch"（120s 超时）。

        Yields:
            str: 每个 content delta（单个 token 片段）。
        """
        client = self._get_client(model)
        timeout = (
            self._settings.realtime_timeout
            if priority == "realtime"
            else self._settings.batch_timeout
        )

        api_model = self._settings.vllm_model if model == "vllm-local" else model

        stream = await client.chat.completions.create(
            model=api_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
