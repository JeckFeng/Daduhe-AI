"""Integration tests for Issue #2: call_tools → fusion → citation pipeline.

Uses real search-engine (localhost:8002) + stub supervisor/generator.
"""

import pytest
from src.graph.state import SubQuestion
from src.graph.call_tools import call_tools_node
from src.graph.fusion import fusion_node
from src.graph.citation import citation_node
from src.tools.registry import ToolRegistry
from src.tools.vector_search import VECTOR_SEARCH_TOOL, vector_search_handler
from src.settings import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def registry(httpx_client):
    import functools

    r = ToolRegistry()
    handler = functools.partial(vector_search_handler, client=httpx_client)
    r.register(VECTOR_SEARCH_TOOL, handler)
    return r


def _make_state(*, query_type="knowledge_qa", sub_questions, retrieval_mode="hybrid"):
    """Build a minimal AgentState with pre-populated sub_questions."""
    return {
        "query": "混凝土坝裂缝宽度超过多少需要处理",
        "conversation_id": "test-conv-1",
        "trace_id": "test-trace-issue2",
        "retrieval_mode": retrieval_mode,
        "query_type": query_type,
        "sub_questions": [sq.model_dump() for sq in sub_questions],
        "fused_context": "",
        "answer": "",
        "citations": [],
        "messages": [],
    }


class TestCallTools:
    async def test_single_sub_question_retrieves_results(self, registry, settings):
        sq = SubQuestion(
            id="q1",
            question="混凝土坝裂缝宽度超过多少需要处理",
            topic="裂缝宽度处理标准",
        )
        state = _make_state(sub_questions=[sq])

        result = await call_tools_node(state, registry=registry, settings=settings)

        assert "sub_questions" in result
        sq_dict = result["sub_questions"][0]
        assert sq_dict["id"] == "q1"
        assert len(sq_dict["results"]) > 0, "Should retrieve at least 1 chunk"
        assert "chunk_id" in sq_dict["results"][0]
        assert "text" in sq_dict["results"][0]
        assert "score" in sq_dict["results"][0]

    async def test_multiple_sub_questions_parallel_retrieval(self, registry, settings):
        sq1 = SubQuestion(
            id="q1",
            question="混凝土坝裂缝宽度超过多少需要处理",
            topic="裂缝宽度处理标准",
        )
        sq2 = SubQuestion(
            id="q2",
            question="渗漏处理技术有哪些",
            topic="渗漏处理技术",
        )
        state = _make_state(sub_questions=[sq1, sq2])

        result = await call_tools_node(state, registry=registry, settings=settings)

        sqs = result["sub_questions"]
        assert len(sqs) == 2
        for sq in sqs:
            assert len(sq["results"]) > 0, f"Sub-question {sq['id']} got no results"

        # q1 and q2 should have different results (different topics)
        q1_chunks = {r["chunk_id"] for r in sqs[0]["results"]}
        q2_chunks = {r["chunk_id"] for r in sqs[1]["results"]}
        # Not all identical — some chunks should differ
        assert not q1_chunks == q2_chunks or len(q1_chunks) == 0

    async def test_resolved_query_takes_precedence(self, registry, settings):
        sq = SubQuestion(
            id="q1",
            question="原始问题表述",
            topic="测试主题",
            resolved_query="混凝土坝裂缝宽度超过多少需要处理",
        )
        state = _make_state(sub_questions=[sq])

        result = await call_tools_node(state, registry=registry, settings=settings)
        assert len(result["sub_questions"][0]["results"]) > 0


class TestFusion:
    async def test_dedup_by_chunk_id(self):
        """Same chunk from two sub-questions: keep higher score."""
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [
                {
                    "id": "q1",
                    "question": "q1",
                    "topic": "t1",
                    "results": [
                        {
                            "chunk_id": "c1",
                            "text": "text1",
                            "score": 0.9,
                            "metadata": {"title": "T1"},
                        },
                        {
                            "chunk_id": "c2",
                            "text": "text2",
                            "score": 0.7,
                            "metadata": {"title": "T2"},
                        },
                    ],
                },
                {
                    "id": "q2",
                    "question": "q2",
                    "topic": "t2",
                    "results": [
                        {
                            "chunk_id": "c1",
                            "text": "text1-dup",
                            "score": 0.5,
                            "metadata": {"title": "T1"},
                        },
                        {
                            "chunk_id": "c3",
                            "text": "text3",
                            "score": 0.8,
                            "metadata": {"title": "T3"},
                        },
                    ],
                },
            ],
            "fused_context": "",
            "answer": "",
            "citations": [],
            "messages": [],
        }

        result = await fusion_node(state, settings=Settings())

        # c1 appears in both, keep 0.9 version. c2 (0.7), c3 (0.8). Total 3 unique.
        assert "fused_results" in result
        assert len(result["fused_results"]) == 3

        # Sort order: c1(0.9), c3(0.8), c2(0.7)
        assert result["fused_results"][0]["chunk_id"] == "c1"
        assert result["fused_results"][0]["score"] == 0.9
        assert result["fused_results"][1]["chunk_id"] == "c3"
        assert result["fused_results"][2]["chunk_id"] == "c2"

    async def test_top_k_truncation(self):
        """More results than top_k: only keep top K."""
        chunks = [
            {
                "chunk_id": f"c{i}",
                "text": f"text{i}",
                "score": 1.0 - i * 0.05,
                "metadata": {},
            }
            for i in range(15)
        ]
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [
                {"id": "q1", "question": "q1", "topic": "t1", "results": chunks}
            ],
            "fused_context": "",
            "answer": "",
            "citations": [],
            "messages": [],
        }

        result = await fusion_node(state, settings=Settings(fusion_top_k=5))

        assert len(result["fused_results"]) == 5
        assert result["fused_results"][0]["score"] == 1.0

    async def test_fused_context_format(self):
        """fused_context should contain [N] markers."""
        chunks = [
            {
                "chunk_id": "c1",
                "text": "重要的裂缝处理标准文本",
                "score": 0.95,
                "metadata": {"title": "规范A"},
            },
            {
                "chunk_id": "c2",
                "text": "次要的渗漏处理技术说明",
                "score": 0.80,
                "metadata": {"title": "规范B"},
            },
        ]
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [
                {"id": "q1", "question": "q1", "topic": "t1", "results": chunks}
            ],
            "fused_context": "",
            "answer": "",
            "citations": [],
            "messages": [],
        }

        result = await fusion_node(state, settings=Settings())

        assert "[1]" in result["fused_context"]
        assert "重要的裂缝处理标准文本" in result["fused_context"]
        assert "[2]" in result["fused_context"]


class TestCitation:
    async def test_extracts_references_from_answer(self):
        """Citation node maps [1] [2] to fused results by index."""
        fused_results = [
            {
                "chunk_id": "seed-chunk-001",
                "text": "第一条原文",
                "score": 0.95,
                "metadata": {
                    "doc_id": "seed-doc-001",
                    "doc_type": "规范",
                    "title": "DL/T 2628-2023",
                    "section_number": "5.2.3",
                    "section_title": "裂缝处理标准",
                    "page_number": 12,
                },
            },
            {
                "chunk_id": "seed-chunk-002",
                "text": "第二条原文" * 20,
                "score": 0.80,
                "metadata": {
                    "doc_id": "seed-doc-002",
                    "doc_type": "规范",
                    "title": "SL 230-2015",
                    "section_number": "3.1",
                    "section_title": "",
                    "page_number": 8,
                },
            },
        ]
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [],
            "fused_context": "",
            "fused_results": fused_results,
            "answer": "根据标准[1]，裂缝处理需要...同时参考[2]的规定。",
            "citations": [],
            "messages": [],
        }

        result = await citation_node(state, settings=Settings())

        assert "citations" in result
        citations = result["citations"]
        assert len(citations) == 2

        # Citation 1
        assert citations[0]["index"] == 1
        assert citations[0]["chunk_id"] == "seed-chunk-001"
        assert citations[0]["doc_title"] == "DL/T 2628-2023"
        assert citations[0]["doc_type"] == "规范"
        assert citations[0]["section"] == "5.2.3 裂缝处理标准"
        assert citations[0]["page"] == 12
        assert "localhost:8002" in citations[0]["download_url"]
        assert "第一条原文" in citations[0]["excerpt"]

        # Citation 2
        assert citations[1]["index"] == 2
        assert citations[1]["chunk_id"] == "seed-chunk-002"

    async def test_excerpt_max_150_chars(self):
        """Excerpt should not exceed 150 characters."""
        long_text = "X" * 300
        fused_results = [
            {
                "chunk_id": "c1",
                "text": long_text,
                "score": 0.9,
                "metadata": {
                    "doc_id": "d1",
                    "doc_type": "",
                    "title": "",
                    "section_number": "",
                    "page_number": None,
                },
            }
        ]
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [],
            "fused_context": "",
            "fused_results": fused_results,
            "answer": "参考[1]。",
            "citations": [],
            "messages": [],
        }

        result = await citation_node(state, settings=Settings())
        excerpt = result["citations"][0]["excerpt"]
        assert len(excerpt) <= 150

    async def test_no_citations_for_answers_without_markers(self):
        """Answers without [N] markers produce empty citations."""
        fused_results = [
            {
                "chunk_id": "c1",
                "text": "text",
                "score": 0.9,
                "metadata": {
                    "doc_id": "d1",
                    "doc_type": "",
                    "title": "",
                    "section_number": "",
                    "page_number": None,
                },
            }
        ]
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [],
            "fused_context": "",
            "fused_results": fused_results,
            "answer": "纯文本回答，没有引用标记。",
            "citations": [],
            "messages": [],
        }

        result = await citation_node(state, settings=Settings())
        assert result["citations"] == []

    async def test_download_url_construction(self):
        """download_url should use search_engine_url base."""
        fused_results = [
            {
                "chunk_id": "c1",
                "text": "text",
                "score": 0.9,
                "metadata": {
                    "doc_id": "seed-doc-001",
                    "doc_type": "",
                    "title": "",
                    "section_number": "",
                    "page_number": None,
                },
            }
        ]
        state = {
            "query": "test",
            "conversation_id": "c1",
            "trace_id": "t1",
            "retrieval_mode": "hybrid",
            "query_type": "knowledge_qa",
            "sub_questions": [],
            "fused_context": "",
            "fused_results": fused_results,
            "answer": "[1]",
            "citations": [],
            "messages": [],
        }

        result = await citation_node(
            state, settings=Settings(search_engine_url="http://example.com:8002")
        )
        assert (
            result["citations"][0]["download_url"]
            == "http://example.com:8002/api/v1/documents/seed-doc-001/download"
        )


class TestEndToEndRetrievalPipeline:
    """End-to-end: stub supervisor + call_tools + fusion + stub generator + citation."""

    async def test_full_pipeline_with_real_search_engine(self, registry, settings):
        from src.graph.call_tools import call_tools_node as ct
        from src.graph.fusion import fusion_node as fn
        from src.graph.citation import citation_node as cn

        # 1. Stub supervisor: 2 sub-questions
        sq1 = SubQuestion(
            id="q1",
            question="混凝土坝裂缝宽度超过多少需要处理",
            topic="裂缝宽度处理标准",
        )
        sq2 = SubQuestion(id="q2", question="渗漏处理技术有哪些", topic="渗漏处理技术")
        state = _make_state(sub_questions=[sq1, sq2])

        # 2. call_tools
        state.update(await ct(state, registry=registry, settings=settings))
        for sq in state["sub_questions"]:
            assert len(sq["results"]) > 0, f"{sq['id']} should have results"

        # 3. fusion
        state.update(await fn(state, settings=settings))
        assert len(state["fused_results"]) > 0
        assert state["fused_context"].startswith("[1]")

        # 4. Stub generator: mock answer with citations
        fused = state["fused_results"]
        answer_parts = []
        for i, r in enumerate(fused[:3]):
            answer_parts.append(
                f"关于{r['metadata'].get('title', '未知')}的分析[{i + 1}]。"
            )
        state["answer"] = " ".join(answer_parts)

        # 5. citation
        state.update(await cn(state, settings=settings))
        assert len(state["citations"]) == min(3, len(fused))
        for c in state["citations"]:
            assert c["chunk_id"]
            assert c["download_url"]
            assert len(c["excerpt"]) > 0
