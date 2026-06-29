"""Tests for Issue #3: Generator node — LLM answer generation."""

import pytest
from src.graph.generator import generator_node
from src.graph.state import SubQuestion

pytestmark = pytest.mark.anyio


def _make_state(
    *,
    query="混凝土坝裂缝宽度超过多少需要处理",
    fused_context,
    sub_questions,
    fused_results=None,
):
    return {
        "query": query,
        "conversation_id": "test-conv-gen",
        "trace_id": "test-trace-issue3",
        "retrieval_mode": "hybrid",
        "query_type": "knowledge_qa",
        "sub_questions": [sq.model_dump() for sq in sub_questions],
        "fused_context": fused_context,
        "fused_results": fused_results or [],
        "answer": "",
        "citations": [],
        "messages": [],
    }


class TestGenerator:
    async def test_generates_answer_with_citation_markers(self, llm, settings):
        """Generator produces non-empty answer with [N] markers."""
        sq = SubQuestion(
            id="q1",
            question="混凝土坝裂缝宽度超过多少需要处理",
            topic="裂缝宽度处理标准",
        )
        fused_context = (
            "[1] 混凝土裂缝根据宽度分为三个等级：宽度小于0.2mm为细微裂缝，"
            "可采用表面封闭法处理；宽度0.2-0.5mm为中等裂缝，应采用灌浆或表面封闭法处理；"
            "宽度大于0.5mm为严重裂缝，必须进行灌浆处理。\n\n"
            "[2] 贯穿性裂缝应采用灌浆处理，灌浆材料根据裂缝宽度选择："
            "宽度小于0.5mm采用环氧树脂灌浆，宽度大于0.5mm采用水泥基灌浆料。"
        )
        state = _make_state(fused_context=fused_context, sub_questions=[sq])

        result = await generator_node(state, llm=llm, settings=settings)

        assert "answer" in result
        answer = result["answer"]
        assert len(answer) > 0, "Answer should not be empty"
        import re

        markers = re.findall(r"\[(\d+)\]", answer)
        assert len(markers) > 0, (
            f"Answer should contain [N] markers, got: {answer[:200]}"
        )

    async def test_empty_context_produces_not_found_response(self, llm, settings):
        """Empty fused_context should produce 'not found' style response."""
        sq = SubQuestion(id="q1", question="不存在的问题XYZ123", topic="测试")
        state = _make_state(fused_context="（未检索到相关知识）", sub_questions=[sq])

        result = await generator_node(state, llm=llm, settings=settings)

        answer = result["answer"]
        assert len(answer) > 0
        assert any(
            word in answer
            for word in ["未找到", "未检索到", "抱歉", "暂无", "没有找到"]
        ), f"Answer should indicate no info found: {answer[:200]}"


class TestEndToEndWithGenerator:
    """Tracer bullet: real search-engine + real LLM + citation assembly."""

    async def test_full_pipeline_with_real_llm(self, llm, settings, httpx_client):
        import functools
        from src.graph.call_tools import call_tools_node
        from src.graph.fusion import fusion_node
        from src.graph.citation import citation_node
        from src.tools.registry import ToolRegistry
        from src.tools.vector_search import VECTOR_SEARCH_TOOL, vector_search_handler

        registry = ToolRegistry()
        handler = functools.partial(vector_search_handler, client=httpx_client)
        registry.register(VECTOR_SEARCH_TOOL, handler)

        # 1. Sub-questions (stub supervisor output)
        sq1 = SubQuestion(
            id="q1",
            question="混凝土坝裂缝宽度超过多少需要处理",
            topic="裂缝宽度处理标准",
        )
        state = _make_state(fused_context="", sub_questions=[sq1])

        # 2. Retrieve
        state.update(await call_tools_node(state, registry=registry, settings=settings))
        assert len(state["sub_questions"][0]["results"]) > 0

        # 3. Fuse
        state.update(await fusion_node(state, settings=settings))
        assert len(state["fused_results"]) > 0
        assert "[1]" in state["fused_context"]

        # 4. Generate
        state.update(await generator_node(state, llm=llm, settings=settings))
        answer = state["answer"]
        assert len(answer) > 0
        import re

        markers = re.findall(r"\[(\d+)\]", answer)
        assert len(markers) > 0, f"Answer must cite sources: {answer[:200]}"

        # 5. Citation
        state.update(await citation_node(state, settings=settings))
        citations = state["citations"]
        assert len(citations) > 0
        # Every cited [N] should have a citation entry
        cited = {int(m) for m in markers}
        for n in cited:
            matching = [c for c in citations if c["index"] == n]
            assert len(matching) == 1, f"Citation [{n}] not found in citations"

    async def test_answer_uses_search_engine_context(self, llm, settings, httpx_client):
        """Answer should reference actual content from search-engine chunks."""
        import functools
        from src.graph.call_tools import call_tools_node
        from src.graph.fusion import fusion_node
        from src.tools.registry import ToolRegistry
        from src.tools.vector_search import VECTOR_SEARCH_TOOL, vector_search_handler

        registry = ToolRegistry()
        handler = functools.partial(vector_search_handler, client=httpx_client)
        registry.register(VECTOR_SEARCH_TOOL, handler)

        sq1 = SubQuestion(
            id="q1",
            question="混凝土坝裂缝宽度超过多少需要处理",
            topic="裂缝宽度处理标准",
        )
        state = _make_state(fused_context="", sub_questions=[sq1])

        state.update(await call_tools_node(state, registry=registry, settings=settings))
        state.update(await fusion_node(state, settings=settings))
        state.update(await generator_node(state, llm=llm, settings=settings))

        answer = state["answer"]
        # The answer should mention key terms from the retrieved chunks
        # (e.g., "裂缝", "宽度", "处理", "mm", "等级")
        assert any(term in answer for term in ["裂缝", "宽度", "处理"]), (
            f"Answer should use domain terms from context: {answer[:200]}"
        )
