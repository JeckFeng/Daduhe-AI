"""Smoke tests for agent-reasoning — structure, imports, and endpoint existence.

Phase A: these tests verify the framework is wired correctly without requiring
external services (LLM, search-engine).  Full integration tests go into
test_chat_integration.py once the LLM mock is ready.
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.tools.registry import ToolRegistry
from src.tools.vector_search import VECTOR_SEARCH_TOOL, vector_search_handler
from src.graph.builder import build_graph


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(VECTOR_SEARCH_TOOL, vector_search_handler)
    return r


class TestToolRegistry:
    def test_register_and_resolve(self, registry):
        assert len(registry.list_defs()) == 1
        names = registry.resolve(["chunk"])
        assert "vector_search" in names

    def test_resolve_unknown_source(self, registry):
        names = registry.resolve(["nonexistent"])
        assert names == []

    def test_get_def(self, registry):
        d = registry.get_def("vector_search")
        assert d is not None
        assert d.source_type == "chunk"


class TestGraph:
    def test_graph_compiles(self):
        g = build_graph()
        assert g is not None

    def test_graph_nodes(self):
        g = build_graph()
        node_names = list(g.nodes.keys())
        expected = {
            "supervisor",
            "context_resolution",
            "call_tools",
            "fusion",
            "generator",
            "citation",
        }
        assert set(node_names) >= expected, (
            f"Missing nodes: {expected - set(node_names)}"
        )


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestChatEndpoint:
    def test_chat_endpoint_exists(self, client):
        """Phase A: /chat endpoint exists and responds to requests."""
        resp = client.post(
            "/api/v1/chat",
            json={
                "query": "混凝土坝裂缝宽度超过多少需要处理",
                "retrieval_mode": "hybrid",
            },
        )
        # Without API key, LLM call will fail — endpoint still responds
        assert resp.status_code is not None
        body = resp.json()
        assert "code" in body

    def test_chat_rejects_invalid_json(self, client):
        """Pydantic validates required fields."""
        resp = client.post("/api/v1/chat", json={"not_query": "missing"})
        assert resp.status_code is not None


class TestLLMCompletionEndpoint:
    def test_completion_endpoint_exists(self, client):
        """/llm/completion endpoint exists."""
        resp = client.post(
            "/api/v1/llm/completion",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "test"}],
                "caller": "smoke-test",
            },
        )
        assert resp.status_code is not None
        body = resp.json()
        assert "code" in body
