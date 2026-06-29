"""Tests for Issue #4: Supervisor — query analysis and decomposition."""

import pytest
from src.graph.state import SubQuestion

pytestmark = pytest.mark.anyio


def _make_state(
    *, query, conversation_id="test-conv-sup", trace_id="test-trace-issue4"
):
    return {
        "query": query,
        "conversation_id": conversation_id,
        "trace_id": trace_id,
        "retrieval_mode": "hybrid",
        "query_type": "",
        "sub_questions": [],
        "fused_context": "",
        "fused_results": [],
        "answer": "",
        "citations": [],
        "messages": [],
    }


class TestSupervisorClassification:
    async def test_knowledge_qa_simple_query(self, llm, settings):
        """Supervisor classifies a simple domain question as knowledge_qa."""
        from src.graph.supervisor import supervisor_node

        state = _make_state(query="混凝土坝裂缝宽度超过多少需要处理")

        result = await supervisor_node(state, llm=llm, settings=settings)

        assert result["query_type"] == "knowledge_qa", (
            f"Expected knowledge_qa, got {result.get('query_type')}"
        )
        sqs = result["sub_questions"]
        assert len(sqs) >= 1, "Should have at least 1 sub_question"
        sq0 = sqs[0]
        assert "id" in sq0
        assert "question" in sq0
        assert "topic" in sq0
        # Validate it deserializes to SubQuestion
        sq = SubQuestion.model_validate(sq0)
        assert len(sq.question) > 0
        assert len(sq.topic) > 0

    async def test_chitchat_classification(self, llm, settings):
        """Greetings and casual talk are classified as chitchat."""
        from src.graph.supervisor import supervisor_node

        chitchat_queries = ["你好", "你是谁", "今天天气怎么样"]

        for q in chitchat_queries:
            state = _make_state(query=q)
            result = await supervisor_node(state, llm=llm, settings=settings)
            assert result["query_type"] == "chitchat", (
                f"Query '{q}' should be chitchat, got {result.get('query_type')}"
            )
            sqs = result["sub_questions"]
            assert len(sqs) == 1
            assert sqs[0]["id"] == "q1"

    async def test_spec_lookup_classification(self, llm, settings):
        """Queries referencing specific standards are spec_lookup."""
        from src.graph.supervisor import supervisor_node

        state = _make_state(query="DL/T 2628 对裂缝处理怎么规定的")

        result = await supervisor_node(state, llm=llm, settings=settings)
        assert result["query_type"] == "spec_lookup", (
            f"Expected spec_lookup, got {result.get('query_type')}"
        )

    async def test_comparison_classification(self, llm, settings):
        """Comparison questions are classified as comparison with 2+ sub-questions."""
        from src.graph.supervisor import supervisor_node

        state = _make_state(query="水泥灌浆和环氧灌浆有什么区别")

        result = await supervisor_node(state, llm=llm, settings=settings)
        assert result["query_type"] == "comparison", (
            f"Expected comparison, got {result.get('query_type')}"
        )
        sqs = result["sub_questions"]
        assert len(sqs) >= 2, (
            f"Comparison should produce 2+ sub_questions, got {len(sqs)}"
        )


class TestSupervisorDecomposition:
    async def test_compound_knowledge_qa_decomposes(self, llm, settings):
        """Multi-aspect knowledge QA should decompose into 2+ sub-questions."""
        from src.graph.supervisor import supervisor_node

        state = _make_state(query="混凝土坝裂缝的分类标准有哪些，各等级应如何处理")

        result = await supervisor_node(state, llm=llm, settings=settings)
        assert result["query_type"] == "knowledge_qa", (
            f"Expected knowledge_qa, got {result.get('query_type')}"
        )
        sqs = result["sub_questions"]
        assert len(sqs) >= 2, (
            f"Compound query should produce 2+ sub_questions, got {len(sqs)}"
        )
        # Each sub_question should have valid structure
        for sq in sqs:
            assert "id" in sq
            assert "question" in sq
            assert "topic" in sq
            assert len(sq["question"]) > 0
            assert len(sq["topic"]) > 0


class TestRouter:
    def test_chitchat_routes_to_generator(self):
        """Chitchat queries skip retrieval and go directly to generator."""
        from src.graph.router import route_after_supervisor

        state = _make_state(query="你好")
        state["query_type"] = "chitchat"
        assert route_after_supervisor(state) == "generator"

    def test_non_chitchat_routes_to_context_resolution(self):
        """All non-chitchat query types go through context_resolution then retrieval."""
        from src.graph.router import route_after_supervisor

        for qt in ("knowledge_qa", "spec_lookup", "comparison"):
            state = _make_state(query="test")
            state["query_type"] = qt
            assert route_after_supervisor(state) == "context_resolution", (
                f"query_type={qt} should route to context_resolution"
            )

    def test_missing_query_type_defaults_to_context_resolution(self):
        """Empty/missing query_type should default to retrieval path."""
        from src.graph.router import route_after_supervisor

        state = _make_state(query="test")
        # query_type is "" by default
        assert route_after_supervisor(state) == "context_resolution"


class TestSupervisorFailure:
    async def test_llm_failure_returns_error(self, settings):
        """Supervisor returns _error when LLM call fails."""
        from src.graph.supervisor import supervisor_node
        from src.llm.client import LLMClient
        from src.settings import Settings as S

        # Create LLMClient with invalid URL to force failure
        bad_settings = S(llm_gateway_url="http://nonexistent-host:9999/v1")
        bad_llm = LLMClient(bad_settings)

        state = _make_state(query="test query")
        result = await supervisor_node(state, llm=bad_llm, settings=bad_settings)

        assert "_error" in result, (
            f"Should have _error on LLM failure, got keys: {list(result.keys())}"
        )
        assert len(result.get("_error", "")) > 0


class TestGraphIntegration:
    """Verify the compiled graph has correct topology for chitchat shortcut."""

    def test_graph_has_chitchat_route(self):
        """Graph must include a route from supervisor to generator for chitchat."""
        from src.graph.builder import build_graph

        g = build_graph()
        # All expected nodes exist
        nodes = set(g.nodes.keys())
        assert "supervisor" in nodes
        assert "call_tools" in nodes
        assert "generator" in nodes
        assert "citation" in nodes

    async def test_graph_chitchat_flow(self, llm, settings):
        """Chitchat query should flow through graph without error."""
        from src.graph.builder import build_graph

        g = build_graph(llm=llm, settings=settings)
        state = _make_state(query="你好")
        result = await g.ainvoke(state)
        assert "answer" in result
        assert len(result["answer"]) > 0
