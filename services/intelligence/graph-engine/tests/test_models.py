"""Test Pydantic data models for graph-engine."""

from src.models import (
    ExtractionTaskRequest,
    GraphQueryRequest,
    ExtractionTask,
    Chunk,
)


class TestExtractionTaskRequest:
    def test_minimal_request(self):
        req = ExtractionTaskRequest(doc_id="seed-doc-001")
        assert req.doc_id == "seed-doc-001"

    def test_rejects_empty_doc_id(self):
        from pydantic import ValidationError
        import pytest

        with pytest.raises(ValidationError):
            ExtractionTaskRequest(doc_id="")


class TestGraphQueryRequest:
    def test_entity_search_query(self):
        req = GraphQueryRequest(
            query_type="entity_search",
            params={"query": "裂缝处理标准"},
        )
        assert req.query_type == "entity_search"
        assert req.params == {"query": "裂缝处理标准"}

    def test_relation_search_query(self):
        req = GraphQueryRequest(
            query_type="relation_search",
            params={"query": "裂缝与灌浆的关系"},
        )
        assert req.query_type == "relation_search"

    def test_rejects_invalid_query_type(self):
        from pydantic import ValidationError
        import pytest

        with pytest.raises(ValidationError):
            GraphQueryRequest(query_type="invalid_type", params={})

    def test_entity_search_with_optional_top_k(self):
        req = GraphQueryRequest(
            query_type="entity_search",
            params={"query": "裂缝", "top_k": 5},
        )
        assert req.params["top_k"] == 5


class TestExtractionTask:
    def test_default_status_is_pending(self):
        task = ExtractionTask(task_id="g-task-001", doc_id="seed-doc-001")
        assert task.status == "pending"

    def test_fields(self):
        task = ExtractionTask(
            task_id="g-task-001",
            doc_id="seed-doc-001",
            status="completed",
            progress={"extracted": 10, "total": 10, "phase": "done"},
            result={"entities": 42, "relationships": 38},
        )
        assert task.task_id == "g-task-001"
        assert task.doc_id == "seed-doc-001"
        assert task.status == "completed"
        assert task.result == {"entities": 42, "relationships": 38}


class TestChunk:
    def test_minimal_chunk(self):
        chunk = Chunk(
            chunk_id="seed-chunk-001",
            doc_id="seed-doc-001",
            content="混凝土坝裂缝宽度超过0.3mm时需要进行灌浆处理。",
        )
        assert chunk.chunk_id == "seed-chunk-001"
        assert chunk.doc_id == "seed-doc-001"
        assert len(chunk.content) > 0

    def test_chunk_with_metadata(self):
        chunk = Chunk(
            chunk_id="seed-chunk-002",
            doc_id="seed-doc-001",
            content="测试内容",
            page_number=23,
            section_title="§5.2.3 裂缝处理标准",
            doc_title="DL/T 2628-2023",
        )
        assert chunk.page_number == 23
        assert "裂缝" in chunk.section_title
