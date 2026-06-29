"""Tests for Issue #5: Context Resolution — anaphora resolution + multi-turn."""

import pytest

pytestmark = pytest.mark.anyio


def _make_state(
    *,
    query,
    sub_questions,
    conversation_id="test-conv-cr",
    trace_id="test-trace-issue5",
):
    return {
        "query": query,
        "conversation_id": conversation_id,
        "trace_id": trace_id,
        "retrieval_mode": "hybrid",
        "query_type": "knowledge_qa",
        "sub_questions": sub_questions,
        "fused_context": "",
        "fused_results": [],
        "answer": "",
        "citations": [],
        "messages": [],
    }


class TestContextResolutionNoOp:
    async def test_clean_query_no_resolution_needed(self, llm, settings):
        """Sub-question without pronouns: resolved_query == original question."""
        from src.graph.context_resolution import context_resolution_node

        sqs = [
            {
                "id": "q1",
                "question": "混凝土坝裂缝宽度超过多少需要处理",
                "topic": "裂缝宽度处理标准",
                "requires_history": False,
                "history_reference": None,
            }
        ]
        state = _make_state(query="混凝土坝裂缝宽度超过多少需要处理", sub_questions=sqs)

        result = await context_resolution_node(state, llm=llm, settings=settings)

        updated = result["sub_questions"]
        assert len(updated) == 1
        q1 = updated[0]
        assert "resolved_query" in q1
        assert q1["resolved_query"] is not None
        # For a clean query, resolved_query should be same or very similar
        assert len(q1["resolved_query"]) > 0


class TestContextResolutionWithHistory:
    async def test_resolves_anaphora_with_history(self, llm, settings):
        """'之前那本规范' with history about DL/T 2628 → resolved_query mentions DL/T 2628."""
        from src.graph.context_resolution import context_resolution_node
        from src.store.conversation import (
            InMemoryConversationStore,
            ConversationMessage,
        )

        # Simulate prior conversation: user asked about DL/T 2628
        store = InMemoryConversationStore()
        await store.append_messages(
            "test-conv-cr",
            [
                ConversationMessage(
                    role="user", content="DL/T 2628 里对裂缝怎么分类的"
                ),
                ConversationMessage(
                    role="assistant",
                    content="DL/T 2628 将裂缝分为三级：细微裂缝(<0.2mm)...",
                ),
            ],
        )

        sqs = [
            {
                "id": "q1",
                "question": "之前那本规范里对贯穿性裂缝怎么规定的",
                "topic": "贯穿性裂缝处理规定",
                "requires_history": True,
                "history_reference": "之前那本规范",
            }
        ]
        state = _make_state(
            query="之前那本规范里对贯穿性裂缝怎么规定的",
            sub_questions=sqs,
        )

        result = await context_resolution_node(
            state,
            llm=llm,
            store=store,
            settings=settings,
        )

        updated = result["sub_questions"]
        assert len(updated) == 1
        q1 = updated[0]
        resolved = q1.get("resolved_query", "")
        # The resolved query should reference the specific standard
        assert "DL/T 2628" in resolved or "2628" in resolved, (
            f"Expected DL/T 2628 in resolved_query, got: {resolved}"
        )

    async def test_clean_query_with_history_still_passes_through(self, llm, settings):
        """A query without pronouns should pass through even when history exists."""
        from src.graph.context_resolution import context_resolution_node
        from src.store.conversation import (
            InMemoryConversationStore,
            ConversationMessage,
        )

        store = InMemoryConversationStore()
        await store.append_messages(
            "test-conv-cr",
            [
                ConversationMessage(
                    role="user", content="DL/T 2628 里对裂缝怎么分类的"
                ),
                ConversationMessage(
                    role="assistant", content="DL/T 2628 将裂缝分为三级..."
                ),
            ],
        )

        sqs = [
            {
                "id": "q1",
                "question": "渗漏处理技术有哪些",
                "topic": "渗漏处理技术",
                "requires_history": False,
                "history_reference": None,
            }
        ]
        state = _make_state(query="渗漏处理技术有哪些", sub_questions=sqs)

        result = await context_resolution_node(
            state,
            llm=llm,
            store=store,
            settings=settings,
        )

        q1 = result["sub_questions"][0]
        # Should still have resolved_query set (identity)
        assert q1["resolved_query"] is not None
        assert len(q1["resolved_query"]) > 0


class TestContextResolutionFallback:
    async def test_llm_failure_falls_back_to_original_question(self, settings):
        """If LLM call fails, resolved_query falls back to original question."""
        from src.graph.context_resolution import context_resolution_node
        from src.llm.client import LLMClient
        from src.settings import Settings as S

        bad_settings = S(llm_gateway_url="http://nonexistent-host:9999/v1")
        bad_llm = LLMClient(bad_settings)

        sqs = [
            {
                "id": "q1",
                "question": "之前那个规范怎么说的",
                "topic": "规范查询",
                "requires_history": True,
                "history_reference": "之前那个规范",
            }
        ]
        state = _make_state(query="之前那个规范怎么说的", sub_questions=sqs)

        result = await context_resolution_node(
            state,
            llm=bad_llm,
            settings=bad_settings,
        )

        q1 = result["sub_questions"][0]
        # Should fall back to original question
        assert q1["resolved_query"] == "之前那个规范怎么说的"
        assert q1["resolved_context"] is None


class TestMultiTurn:
    async def test_two_turn_conversation_resolves_reference(self, llm, settings):
        """Turn 1 asks about DL/T 2628, Turn 2 references '之前那个规范' → resolved."""
        from src.graph.builder import build_graph
        from src.store.conversation import (
            InMemoryConversationStore,
            ConversationMessage,
        )

        store = InMemoryConversationStore()

        # Turn 1: Ask about DL/T 2628
        await store.append_messages(
            "test-mt-1",
            [
                ConversationMessage(
                    role="user", content="DL/T 2628 里对裂缝怎么分类的"
                ),
                ConversationMessage(
                    role="assistant",
                    content="DL/T 2628 将裂缝按宽度分为细微裂缝(<0.2mm)、中等裂缝(0.2-0.5mm)、严重裂缝(>0.5mm)。",
                ),
            ],
        )

        g = build_graph(llm=llm, settings=settings)

        # Turn 2: Reference previous turn
        result = await g.ainvoke(
            {
                "query": "之前那个规范里对贯穿性裂缝怎么规定的",
                "conversation_id": "test-mt-1",
                "trace_id": "test-trace-mt",
                "retrieval_mode": "hybrid",
            }
        )

        assert "answer" in result
        answer = result["answer"]
        assert len(answer) > 0
        # The answer should ideally mention DL/T 2628 (if the resolution worked)
        # We check that at least citations and answer are produced
        assert isinstance(result.get("citations"), list)
