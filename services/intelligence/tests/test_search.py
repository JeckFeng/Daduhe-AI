"""Integration tests for search-engine.
Requires remote infrastructure (PostgreSQL, Milvus, Ollama).
Set SKIP_SEARCH_TESTS=1 to skip.
"""

import os

import pytest

_skip_reason = os.environ.get("SKIP_SEARCH_TESTS")
pytestmark = pytest.mark.skipif(
    bool(_skip_reason),
    reason=f"SKIP_SEARCH_TESTS={_skip_reason}",
)


@pytest.fixture(scope="module")
def db_conn():
    """PSQL connection via SSH tunnel."""
    import psycopg2

    conn = psycopg2.connect(
        host="localhost",
        port=5434,
        user="daduhe",
        password="gis31415",
        dbname="mydatabase",
    )
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def test_client():
    from src.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_keyword_search_returns_chunks_containing_query(test_client):
    """keyword mode should return chunks whose text contains the query term."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝",
            "mode": "keyword",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    results = body["data"]["results"]
    assert len(results) > 0, "expected at least one matching chunk"
    for item in results:
        assert "裂缝" in item["text"]
    assert body["data"]["mode_used"] == "keyword"


REQUIRED_CHUNK_METADATA = {
    "doc_id",
    "doc_type",
    "title",
    "section_number",
    "section_title",
    "page_number",
    "download_url",
}


def test_keyword_results_have_traceability_metadata(test_client):
    """Each result must include full metadata for traceability (ICD-03 §5.2)."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝",
            "mode": "keyword",
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) > 0
    for item in results:
        meta = item["metadata"]
        missing = REQUIRED_CHUNK_METADATA - set(meta.keys())
        assert not missing, f"chunk {item['chunk_id']} missing metadata: {missing}"
        assert item["source_type"] == "chunk"
        assert meta["doc_id"].startswith("seed-doc-")
        assert len(meta["title"]) > 0
        assert meta["download_url"] == f"/api/v1/documents/{meta['doc_id']}/download"


def test_keyword_top_k_limit(test_client):
    """top_k should limit the number of returned results."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "缺陷",
            "mode": "keyword",
            "top_k": 3,
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) <= 3
    assert r.json()["data"]["total_hits"] <= 3


def test_keyword_filters_by_doc_type(test_client):
    """filters.doc_type should restrict results to the given doc types."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "缺陷",
            "mode": "keyword",
            "filters": {"doc_type": ["规范"]},
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) > 0, "expected at least one 规范 result"
    for item in results:
        assert item["metadata"]["doc_type"] == "规范", (
            f"expected doc_type=规范, got {item['metadata']['doc_type']}"
        )


def test_keyword_filters_by_doc_ids(test_client):
    """filters.doc_ids should restrict results to only those documents."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "缺陷",
            "mode": "keyword",
            "filters": {"doc_ids": ["seed-doc-001"]},
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) > 0
    for item in results:
        assert item["metadata"]["doc_id"] == "seed-doc-001"


def test_keyword_empty_for_nonexistent_term(test_client):
    """Searching for a term not in any chunk should return empty results."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "XYZZY不存在的关键词",
            "mode": "keyword",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["results"] == []
    assert body["data"]["total_hits"] == 0


def test_health_endpoint(test_client):
    """GET /health should return 200."""
    r = test_client.get("/health")
    assert r.status_code == 200, r.text


# ═══════════════════════════════════════════════════════════════
# Fuzzy search (pg_trgm)
# ═══════════════════════════════════════════════════════════════


def test_fuzzy_search_returns_chunks(test_client):
    """fuzzy mode should return chunks with pg_trgm similarity scores."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝处理",
            "mode": "fuzzy",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    results = body["data"]["results"]
    assert len(results) > 0, "expected at least one fuzzy match"
    assert body["data"]["mode_used"] == "fuzzy"
    for item in results:
        assert item["score"] > 0
        assert item["source_type"] == "chunk"


def test_fuzzy_typo_tolerance(test_client):
    """A query with a typo (裂逢→裂缝) should still match the same chunks."""
    # Correct query
    r_correct = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝处理",
            "mode": "fuzzy",
        },
    )
    correct_ids = {item["chunk_id"] for item in r_correct.json()["data"]["results"]}

    # Typo query
    r_typo = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂逢处理",
            "mode": "fuzzy",
        },
    )
    typo_ids = {item["chunk_id"] for item in r_typo.json()["data"]["results"]}

    # The typo query should return some of the same chunks (fuzzy tolerance)
    assert len(typo_ids) > 0, "typo query should return some results"
    overlap = correct_ids & typo_ids
    assert len(overlap) > 0, (
        f"typo '{'裂逢处理'}' should overlap with correct '{'裂缝处理'}' results"
    )


def test_fuzzy_results_sorted_by_similarity(test_client):
    """Scores should be in descending order (highest similarity first)."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝处理",
            "mode": "fuzzy",
        },
    )
    results = r.json()["data"]["results"]
    assert len(results) > 0, "expected at least one result"
    scores = [item["score"] for item in results]
    assert scores == sorted(scores, reverse=True), f"scores not sorted: {scores}"


# ═══════════════════════════════════════════════════════════════
# Vector search (Ollama + Milvus + PG)
# ═══════════════════════════════════════════════════════════════


def test_vector_search_returns_semantically_relevant_chunks(test_client):
    """vector mode should return chunks semantically related to the query."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝宽度大于0.3mm时需要采取什么处理措施？",
            "mode": "vector",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    results = body["data"]["results"]
    assert len(results) > 0, "expected at least one vector result"
    assert body["data"]["mode_used"] == "vector"
    # The top result should be about crack processing
    top_text = results[0]["text"]
    assert "裂缝" in top_text or "灌浆" in top_text, (
        f"top result should be about crack, got: {top_text[:80]}"
    )
    for item in results:
        assert item["source_type"] == "chunk"
        assert item["score"] >= 0


def test_vector_results_have_metadata(test_client):
    """Vector results must include the same traceability metadata as keyword."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "渗漏检测方法",
            "mode": "vector",
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) > 0
    for item in results:
        meta = item["metadata"]
        missing = REQUIRED_CHUNK_METADATA - set(meta.keys())
        assert not missing, f"chunk {item['chunk_id']} missing metadata: {missing}"
        assert item["source_type"] == "chunk"
        assert meta["download_url"] == f"/api/v1/documents/{meta['doc_id']}/download"


def test_vector_top_k_limit(test_client):
    """Vector top_k should limit results."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "缺陷处理",
            "mode": "vector",
            "top_k": 3,
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) <= 3


def test_vector_score_in_cosine_range(test_client):
    """COSINE scores should be in [0, 2] range (cosine distance may exceed 1 in Milvus)."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "泄洪安全评价",
            "mode": "vector",
        },
    )
    results = r.json()["data"]["results"]
    assert len(results) > 0
    for item in results:
        assert 0 <= item["score"] <= 2.0, f"score {item['score']} out of COSINE range"


# ═══════════════════════════════════════════════════════════════
# Hybrid search (RRF)
# ═══════════════════════════════════════════════════════════════


def test_hybrid_returns_results(test_client):
    """Hybrid mode should return results with mode_used=hybrid."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝宽度处理措施",
            "mode": "hybrid",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    results = body["data"]["results"]
    assert len(results) > 0, "expected at least one hybrid result"
    assert body["data"]["mode_used"] == "hybrid"
    for item in results:
        assert item["source_type"] == "chunk"
        assert item["score"] >= 0
        # Verify metadata completeness
        meta = item["metadata"]
        missing = REQUIRED_CHUNK_METADATA - set(meta.keys())
        assert not missing, f"missing metadata: {missing}"


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/search/index  (HT callback → index build)
# ═══════════════════════════════════════════════════════════════

INDEX_TEST_COLLECTION = "search_index_test"


@pytest.fixture(scope="module")
def index_test_client():
    """TestClient with collection_name overridden for index tests."""
    from unittest.mock import patch

    with patch("src.main.settings.milvus_collection", INDEX_TEST_COLLECTION):
        from src.main import app
        from fastapi.testclient import TestClient

        yield TestClient(app)
    # Teardown: drop test collection
    from pymilvus import MilvusClient
    from src.settings import Settings

    s = Settings()
    mc = MilvusClient(
        uri=s.milvus_uri,
        user=s.milvus_user,
        password=s.milvus_password,
        db_name=s.milvus_db,
    )
    if mc.has_collection(INDEX_TEST_COLLECTION):
        mc.drop_collection(INDEX_TEST_COLLECTION)


def test_search_index_returns_202(index_test_client):
    """POST /api/v1/search/index with a valid doc_id should return 202."""
    r = index_test_client.post(
        "/api/v1/search/index",
        json={
            "doc_id": "seed-doc-001",
            "event_id": "evt-test-001",
            "trace_id": "ht-test-001",
            "title": "测试文档",
            "chunk_count": 3,
            "embedding_model": "bge-m3",
            "embedding_dimension": 1024,
            "status": "completed",
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["task_id"].startswith("idx-task-")
    assert body["data"]["status"] in ("processing", "completed")


def test_search_index_writes_to_milvus(index_test_client):
    """After index build, seed-doc-002 chunks should be in Milvus."""
    r = index_test_client.post(
        "/api/v1/search/index",
        json={
            "doc_id": "seed-doc-002",
            "event_id": "evt-test-002",
        },
    )
    assert r.status_code == 202, r.text

    # Verify data in Milvus
    from pymilvus import MilvusClient
    from src.settings import Settings

    s = Settings()
    mc = MilvusClient(
        uri=s.milvus_uri,
        user=s.milvus_user,
        password=s.milvus_password,
        db_name=s.milvus_db,
    )
    mc.load_collection(INDEX_TEST_COLLECTION)
    results = mc.query(
        INDEX_TEST_COLLECTION,
        filter='doc_id == "seed-doc-002"',
        output_fields=["chunk_id", "doc_id"],
        limit=10,
    )
    assert len(results) > 0, "expected chunks from seed-doc-002 in Milvus"
    for r_item in results:
        assert r_item["doc_id"] == "seed-doc-002"
        assert r_item["chunk_id"].startswith("seed-chunk-")


def test_search_index_idempotent(index_test_client):
    """Calling /search/index twice with same doc_id should not duplicate data."""
    # First call
    r1 = index_test_client.post(
        "/api/v1/search/index",
        json={
            "doc_id": "seed-doc-001",
            "event_id": "evt-idem-1",
        },
    )
    assert r1.status_code == 202

    from pymilvus import MilvusClient
    from src.settings import Settings

    s = Settings()
    mc = MilvusClient(
        uri=s.milvus_uri,
        user=s.milvus_user,
        password=s.milvus_password,
        db_name=s.milvus_db,
    )
    mc.load_collection(INDEX_TEST_COLLECTION)
    first = mc.query(
        INDEX_TEST_COLLECTION, filter='doc_id == "seed-doc-001"', output_fields=["id"]
    )

    # Second call
    r2 = index_test_client.post(
        "/api/v1/search/index",
        json={
            "doc_id": "seed-doc-001",
            "event_id": "evt-idem-2",
        },
    )
    assert r2.status_code == 202

    # Handler released the collection — reload before query
    mc.load_collection(INDEX_TEST_COLLECTION)
    second = mc.query(
        INDEX_TEST_COLLECTION, filter='doc_id == "seed-doc-001"', output_fields=["id"]
    )
    # Count should be the same — no duplicates
    assert len(second) == len(first), (
        f"idempotent check: first={len(first)}, second={len(second)}"
    )


def test_search_index_invalid_doc_id_returns_error(index_test_client):
    """A doc_id not in PG should return an error."""
    r = index_test_client.post(
        "/api/v1/search/index",
        json={
            "doc_id": "nonexistent-doc-999",
            "event_id": "evt-bad",
        },
    )
    body = r.json()
    # Should NOT be 202 — missing doc
    assert body["code"] != 0 or r.status_code != 202, (
        f"expected error for nonexistent doc_id, got {body}"
    )


# ═══════════════════════════════════════════════════════════════
# Rules source guard (include_sources validation)
# ═══════════════════════════════════════════════════════════════


def test_include_sources_rules_rejected(test_client):
    """include_sources containing 'rules' should return 400."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝",
            "mode": "vector",
            "include_sources": ["rules"],
        },
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] != 0
    assert "rule" in body["message"].lower()


def test_include_sources_rules_with_chunks_rejected(test_client):
    """include_sources ['chunks','rules'] should also return 400."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝",
            "mode": "vector",
            "include_sources": ["chunks", "rules"],
        },
    )
    assert r.status_code == 400, r.text


def test_include_sources_chunks_only_accepted(test_client):
    """include_sources with only 'chunks' should work normally."""
    r = test_client.post(
        "/api/v1/search",
        json={
            "query": "裂缝",
            "mode": "keyword",
            "include_sources": ["chunks"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["code"] == 0
