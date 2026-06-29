"""Integration tests for LLM client + cache.

Requires agent-reasoning running at GRAPH_AGENT_LLM_URL (default http://localhost:8003).
"""

import pytest

from src.settings import Settings
from src.llm.provider import LLMProvider
from src.llm.client import AgentReasoningLLMClient
from src.llm.cache import LLMCache

pytestmark = pytest.mark.integration


# ── Protocol compliance ─────────────────────────────────────────


def test_llm_client_satisfies_protocol(llm_client):
    """AgentReasoningLLMClient implements the LLMProvider protocol."""
    assert isinstance(llm_client, LLMProvider)


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def llm_client(settings):
    return AgentReasoningLLMClient(settings)


@pytest.fixture
def llm_cache(settings):
    """LLMCache connected to PG for cache verification."""
    return LLMCache(settings)


# ── Tracer Bullet: real LLM call ─────────────────────────────────


async def test_llm_completion_returns_content(llm_client):
    """Call real LLM via agent-reasoning, verify response structure."""
    result = await llm_client.completion(
        system_prompt="你是一个有用的助手。用中文回答。",
        user_prompt="1+1等于几？只需回答数字。",
    )
    assert "content" in result
    assert len(result["content"]) > 0
    assert "model" in result
    assert "usage" in result


# ── Cache tests ──────────────────────────────────────────────────


async def test_cache_hit_on_second_call(llm_client, llm_cache):
    """First call goes to LLM + caches; second call returns from cache."""
    system = "你是一个数学助手。"
    user = "2+2等于几？只回答数字。"

    # Clear any existing cache entry for this test
    import hashlib

    cache_key = hashlib.md5((system + user + "vllm-local").encode("utf-8")).hexdigest()
    llm_cache.delete(cache_key)

    # First call — should go to LLM
    result1 = await llm_client.completion(
        system_prompt=system,
        user_prompt=user,
    )
    llm_cache.set("vllm-local", system, user, result1)

    # Second call with same params — should be same content from cache
    cached = llm_cache.get("vllm-local", system, user)
    assert cached is not None, "Cache should have been written"
    assert cached["content"] == result1["content"]


async def test_different_prompts_different_cache_keys(llm_cache):
    """Different prompts produce different cache keys."""
    system = "助手"
    user_a = "问题A"
    user_b = "问题B"

    llm_cache.set("vllm-local", system, user_a, {"content": "A"})
    llm_cache.set("vllm-local", system, user_b, {"content": "B"})

    cached_a = llm_cache.get("vllm-local", system, user_a)
    cached_b = llm_cache.get("vllm-local", system, user_b)

    assert cached_a["content"] == "A"
    assert cached_b["content"] == "B"


async def test_cache_miss_returns_none(llm_cache):
    """Non-existent cache key returns None."""
    result = llm_cache.get("nonexistent-model", "no-such-system", "no-such-user")
    assert result is None


async def test_llm_error_raises_exception(llm_client):
    """Invalid model or connection failure raises exception."""
    with pytest.raises(Exception):
        await llm_client.completion(
            system_prompt="test",
            user_prompt="test",
            model="nonexistent-model-xyz",
        )
