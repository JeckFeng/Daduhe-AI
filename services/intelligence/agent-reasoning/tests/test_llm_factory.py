"""Tests for Issue #6: LLM Completion Factory — /llm/completion endpoint."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestLLMCompletionReal:
    def test_vllm_local_returns_content(self, client):
        """Call vllm-local via the endpoint, verify content returned."""
        resp = client.post(
            "/api/v1/llm/completion",
            json={
                "model": "vllm-local",
                "messages": [
                    {
                        "role": "user",
                        "content": "1+1等于几？请用中文回答，只需回答数字。",
                    }
                ],
                "caller": "test-issue6",
                "priority": "realtime",
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["code"] == 0
        assert "data" in body
        data = body["data"]
        assert len(data["content"]) > 0, "Should return non-empty content"
        assert data["model"] == "vllm-local"

    def test_response_includes_latency_and_usage(self, client):
        """Response should include latency_ms and token usage."""
        resp = client.post(
            "/api/v1/llm/completion",
            json={
                "model": "vllm-local",
                "messages": [{"role": "user", "content": "你好，请介绍你自己"}],
                "caller": "test-issue6",
                "priority": "realtime",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["latency_ms"] > 0, (
            f"Expected positive latency, got {data['latency_ms']}"
        )
        usage = data["usage"]
        assert usage["prompt_tokens"] > 0, f"Expected prompt_tokens > 0, got {usage}"
        assert usage["completion_tokens"] > 0, (
            f"Expected completion_tokens > 0, got {usage}"
        )


class TestLLMCompletionValidation:
    def test_missing_messages_returns_422(self, client):
        """Missing required 'messages' field should return 422."""
        resp = client.post(
            "/api/v1/llm/completion",
            json={
                "model": "vllm-local",
                "caller": "test-issue6",
            },
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing messages, got {resp.status_code}"
        )
        body = resp.json()
        assert body["code"] == 1002

    def test_invalid_priority_rejected(self, client):
        """Invalid priority value should be rejected."""
        resp = client.post(
            "/api/v1/llm/completion",
            json={
                "model": "vllm-local",
                "messages": [{"role": "user", "content": "test"}],
                "caller": "test-issue6",
                "priority": "invalid-priority",
            },
        )
        assert resp.status_code == 422
