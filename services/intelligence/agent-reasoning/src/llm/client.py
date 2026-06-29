"""LLM 调用客户端 — 通过 llm-gateway 统一调用 LLM 服务。

提供两个核心能力：
- completion(): 非流式 LLM 调用，返回完整响应
- completion_stream(): 流式 SSE 调用，逐 token 产出

所有调用通过 llm-gateway 的 /api/v1/completion 和 /api/v1/completion/stream 端点中转。
"""

import json
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx

from src.settings import Settings


class LLMClient:
    """LLM 调用客户端，封装 llm-gateway 的非流式和流式接口。

    Attributes:
        _url: 非流式 completion 端点地址
        _stream_url: 流式 SSE 端点地址
        _timeout: HTTP 请求超时时间（秒）
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化 LLM 客户端。

        Args:
            settings: 服务配置，为 None 时使用默认配置
        """
        self._settings = settings or Settings()
        base = self._settings.llm_gateway_url.rstrip("/")
        self._url = f"{base}/api/v1/completion"
        self._stream_url = f"{base}/api/v1/completion/stream"
        self._timeout = 120.0

    async def completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2000,
        priority: str = "batch",
    ) -> dict[str, str | int | float]:
        """非流式 LLM 调用，等待完整响应后返回。

        Args:
            model: 模型名称，如 "deepseek-chat"、"vllm-local"
            messages: 对话消息列表，每条为 {"role": ..., "content": ...}
            temperature: 采样温度，0-1 之间，越低越确定
            max_tokens: 最大输出 token 数
            priority: 优先级，"realtime"（低延迟）或 "batch"（高吞吐）

        Returns:
            dict: {"content": str, "model": str, "prompt_tokens": int,
                   "completion_tokens": int, "latency_ms": float}

        Raises:
            RuntimeError: llm-gateway 返回错误码时抛出
        """
        trace_id = f"agent-reasoning-{uuid4()}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                self._url,
                json={
                    "model": model,
                    "messages": messages,
                    "caller": "agent-reasoning",
                    "priority": priority,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={"X-Trace-Id": trace_id},
            )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"LLM call failed: code={data.get('code')} message={data.get('message')}"
            )

        inner = data["data"]
        return {
            "content": inner["content"],
            "model": model,
            "prompt_tokens": inner["usage"]["prompt_tokens"],
            "completion_tokens": inner["usage"]["completion_tokens"],
            "latency_ms": inner["latency_ms"],
        }

    async def completion_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2000,
        priority: str = "batch",
    ) -> AsyncIterator[str]:
        """流式 LLM 调用，逐 token 产出。

        通过 llm-gateway 的 SSE 端点获取流式响应，解析每帧 SSE 事件，
        产出 content token 字符串。

        Args:
            model: 模型名称
            messages: 对话消息列表
            temperature: 采样温度
            max_tokens: 最大输出 token 数
            priority: 优先级，"realtime" 或 "batch"

        Yields:
            str: 每个 content token

        Raises:
            RuntimeError: 流式连接失败或服务端返回错误时抛出
        """
        trace_id = f"agent-reasoning-{uuid4()}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                self._stream_url,
                json={
                    "model": model,
                    "messages": messages,
                    "caller": "agent-reasoning",
                    "priority": priority,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={"X-Trace-Id": trace_id},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"LLM stream failed: status={resp.status_code} body={body.decode()[:500]}"
                    )

                async for line in resp.aiter_lines():
                    # 跳过空行和 SSE 注释行（以 : 开头）
                    if not line or line.startswith(":"):
                        continue

                    # 提取 data 字段：兼容 "data: " 和 "data:"（无空格）两种格式
                    if line.startswith("data: "):
                        payload = line[6:]
                    elif line.startswith("data:"):
                        payload = line[5:]
                    else:
                        continue

                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    # token 和 error 互斥，正常流只有 token
                    if "token" in data:
                        yield data["token"]
                    elif "error" in data:
                        raise RuntimeError(f"LLM stream error: {data['error']}")
