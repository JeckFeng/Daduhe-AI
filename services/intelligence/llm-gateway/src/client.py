"""OpenAI-compatible LLM client with model routing.

deepseek-chat → DeepSeek API / vllm-local → local vLLM.
Both are OpenAI-compatible, using a single openai.AsyncOpenAI client
with different base_url values.
"""

import time
from openai import AsyncOpenAI

from src.settings import Settings


class LLMClient:
    """Factory that creates OpenAI-compatible clients per model backend."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._clients: dict[str, AsyncOpenAI] = {}

    def get_host(self, model: str) -> str:
        """Return the base_url used for this model (for cache identity)."""
        if model == "vllm-local":
            return self._settings.vllm_url
        return self._settings.deepseek_api_url

    def _get_client(self, model: str) -> AsyncOpenAI:
        if model not in self._clients:
            if model == "vllm-local":
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
        """Call LLM and return {content, model, prompt_tokens, completion_tokens,
        latency_ms}.
        """
        client = self._get_client(model)
        timeout = (
            self._settings.realtime_timeout
            if priority == "realtime"
            else self._settings.batch_timeout
        )

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
    ):
        """Stream LLM tokens via OpenAI-compatible streaming API.

        Yields each content delta as a string. The caller is responsible for
        assembling the full response if needed.
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
