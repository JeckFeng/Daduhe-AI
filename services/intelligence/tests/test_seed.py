"""Integration tests for seed data creation.
Requires remote infrastructure (PostgreSQL, Milvus, Ollama).
Set SKIP_SEED_TESTS=1 to skip.
"""

import os

import pytest

# Skip in CI or when explicitly set
_skip_reason = os.environ.get("SKIP_SEED_TESTS")
pytestmark = pytest.mark.skipif(
    bool(_skip_reason),
    reason=f"SKIP_SEED_TESTS={_skip_reason}",
)


@pytest.fixture(scope="module")
def db_conn():
    """PSQL connection to the project database via SSH tunnel."""
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


# ============================================================
# Slice 1: Schema
# ============================================================

REQUIRED_DOCUMENTS_COLUMNS = {
    "doc_id",
    "doc_type",
    "title",
    "authors",
    "source_org",
    "publish_date",
    "version",
    "language",
    "file_format",
    "file_path",
    "file_size_bytes",
    "permission_level",
    "tags",
    "abstract",
    "uploaded_at",
    "updated_at",
}

REQUIRED_CHUNKS_COLUMNS = {
    "chunk_id",
    "doc_id",
    "chunk_index",
    "chunk_text",
    "page_number",
    "section_title",
    "section_number",
    "char_start",
    "char_end",
    "token_count",
    "parent_chunk_id",
    "created_at",
}

REQUIRED_EMBEDDINGS_COLUMNS = {
    "embedding_id",
    "chunk_id",
    "embedding_model",
    "vector_dimension",
    "milvus_id",
    "created_at",
}


def test_schema_metadata_exists(db_conn):
    """metadata schema must exist after seed schema creation."""
    from scripts.seed_data import create_schema

    create_schema(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'metadata'"
    )
    assert cur.fetchone() is not None, "metadata schema was not created"


def test_documents_table_columns_match_icd(db_conn):
    """metadata.documents must have exactly the columns specified in ICD-01 §4.1."""
    from scripts.seed_data import create_schema

    create_schema(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'metadata' AND table_name = 'documents'"
    )
    actual = {row[0] for row in cur.fetchall()}
    assert actual == REQUIRED_DOCUMENTS_COLUMNS, (
        f"Column mismatch: {actual ^ REQUIRED_DOCUMENTS_COLUMNS}"
    )


def test_chunks_table_columns_match_icd(db_conn):
    """metadata.chunks must have exactly the columns specified in ICD-01 §4.3."""
    from scripts.seed_data import create_schema

    create_schema(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'metadata' AND table_name = 'chunks'"
    )
    actual = {row[0] for row in cur.fetchall()}
    assert actual == REQUIRED_CHUNKS_COLUMNS, (
        f"Column mismatch: {actual ^ REQUIRED_CHUNKS_COLUMNS}"
    )


def test_embeddings_table_columns_match_icd(db_conn):
    """metadata.embeddings must have exactly the columns specified in ICD-01 §4.4."""
    from scripts.seed_data import create_schema

    create_schema(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'metadata' AND table_name = 'embeddings'"
    )
    actual = {row[0] for row in cur.fetchall()}
    assert actual == REQUIRED_EMBEDDINGS_COLUMNS, (
        f"Column mismatch: {actual ^ REQUIRED_EMBEDDINGS_COLUMNS}"
    )


def test_chunks_foreign_key_to_documents(db_conn):
    """chunks.doc_id must reference documents.doc_id."""
    from scripts.seed_data import create_schema

    create_schema(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'metadata.chunks'::regclass AND contype = 'f'"
    )
    fks = [row[0] for row in cur.fetchall()]
    assert len(fks) >= 1, "chunks table missing foreign key to documents"


def test_chunk_id_unique_in_embeddings(db_conn):
    """embeddings must have a unique constraint on chunk_id."""
    from scripts.seed_data import create_schema

    create_schema(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'metadata' AND tablename = 'embeddings' AND indexname LIKE '%chunk_id%'"
    )
    indexes = cur.fetchall()
    assert len(indexes) >= 1, "embeddings missing unique index on chunk_id"


# ============================================================
# Slice 2: Seed data insertion
# ============================================================


def test_seed_documents_inserted(db_conn):
    """After seeding, metadata.documents contains exactly 2 seed documents."""
    from scripts.seed_data import create_schema, insert_documents

    create_schema(db_conn)
    insert_documents(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT count(*) FROM metadata.documents WHERE doc_id LIKE 'seed-%'")
    count = cur.fetchone()[0]
    assert count == 2, f"Expected 2 seed documents, got {count}"


def test_seed_documents_have_required_fields(db_conn):
    """Seed documents must have non-null title, doc_type, source_org, file_format."""
    from scripts.seed_data import create_schema, insert_documents

    create_schema(db_conn)
    insert_documents(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT doc_id, title, doc_type, source_org, file_format "
        "FROM metadata.documents WHERE doc_id LIKE 'seed-%' ORDER BY doc_id"
    )
    rows = cur.fetchall()
    for row in rows:
        doc_id, title, doc_type, source_org, file_format = row
        assert title, f"{doc_id}: title is empty"
        assert doc_type, f"{doc_id}: doc_type is empty"
        assert source_org, f"{doc_id}: source_org is empty"
        assert file_format == "pdf", (
            f"{doc_id}: file_format should be pdf, got {file_format}"
        )


def test_seed_chunks_inserted(db_conn):
    """After seeding, metadata.chunks contains exactly 15 seed chunks."""
    from scripts.seed_data import create_schema, insert_documents, insert_chunks

    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT count(*) FROM metadata.chunks WHERE chunk_id LIKE 'seed-%'")
    count = cur.fetchone()[0]
    assert count == 15, f"Expected 15 seed chunks, got {count}"


def test_seed_chunks_reference_valid_documents(db_conn):
    """Every seed chunk.doc_id must exist in metadata.documents."""
    from scripts.seed_data import create_schema, insert_documents, insert_chunks

    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT c.chunk_id, c.doc_id FROM metadata.chunks c "
        "LEFT JOIN metadata.documents d ON c.doc_id = d.doc_id "
        "WHERE c.chunk_id LIKE 'seed-%' AND d.doc_id IS NULL"
    )
    orphans = cur.fetchall()
    assert not orphans, f"Orphan chunks (doc_id not found): {orphans}"


def test_chunk_text_is_meaningful(db_conn):
    """Each seed chunk must have substantive text content (≥50 chars)."""
    from scripts.seed_data import create_schema, insert_documents, insert_chunks

    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT chunk_id, char_length(chunk_text) FROM metadata.chunks "
        "WHERE chunk_id LIKE 'seed-%'"
    )
    for chunk_id, length in cur.fetchall():
        assert length >= 50, f"{chunk_id}: chunk_text too short ({length} chars)"


# ============================================================
# Slice 3: Ollama embedding generation
# ============================================================


@pytest.fixture(scope="module")
def ollama_url():
    return "http://localhost:11435"


@pytest.fixture(scope="module")
def seed_chunk_texts():
    """All 15 chunk texts for embedding."""
    from scripts.seed_data import SEED_CHUNKS

    return [c["chunk_text"] for c in SEED_CHUNKS]


def test_ollama_embedding_returns_1024_dim(ollama_url, seed_chunk_texts):
    """bge-m3 must return 1024-dimensional vectors."""
    import httpx

    resp = httpx.post(
        f"{ollama_url}/api/embeddings",
        json={"model": "bge-m3", "prompt": seed_chunk_texts[0]},
        timeout=30,
    )
    assert resp.status_code == 200, f"Ollama API error: {resp.text}"
    data = resp.json()
    embedding = data["embedding"]
    assert len(embedding) == 1024, f"Expected 1024 dims, got {len(embedding)}"
    assert all(isinstance(v, float) for v in embedding), "Not all values are floats"


def test_ollama_embeddings_all_15_chunks(ollama_url, seed_chunk_texts):
    """All 15 seed chunks must be embeddable."""
    import httpx

    vectors = []
    for i, text in enumerate(seed_chunk_texts):
        resp = httpx.post(
            f"{ollama_url}/api/embeddings",
            json={"model": "bge-m3", "prompt": text},
            timeout=30,
        )
        assert resp.status_code == 200, f"Chunk {i} failed: {resp.text}"
        data = resp.json()
        embedding = data["embedding"]
        assert len(embedding) == 1024, f"Chunk {i}: expected 1024, got {len(embedding)}"
        vectors.append(embedding)
    assert len(vectors) == 15, f"Expected 15 vectors, got {len(vectors)}"


def test_similar_queries_yield_similar_vectors(ollama_url):
    """Semantically similar texts should produce vectors with high cosine similarity."""
    import httpx

    text_a = "裂缝宽度大于0.3mm时需要采取灌浆处理措施"
    text_b = "当裂缝超过0.3毫米时应进行灌浆加固"
    text_c = "泄洪能力不足时可采取加大泄洪断面措施"  # unrelated

    def embed(text):
        return httpx.post(
            f"{ollama_url}/api/embeddings",
            json={"model": "bge-m3", "prompt": text},
            timeout=30,
        ).json()["embedding"]

    va, vb, vc = embed(text_a), embed(text_b), embed(text_c)

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb)

    sim_ab = cosine(va, vb)
    sim_ac = cosine(va, vc)
    assert sim_ab > 0.85, f"Similar texts should have high similarity, got {sim_ab:.3f}"
    assert sim_ac < sim_ab, (
        f"Unrelated text should have lower similarity ({sim_ac:.3f} > {sim_ab:.3f})"
    )


# ============================================================
# Slice 4: Milvus collection + vector insertion
# ============================================================

TEST_COLLECTION = "seed_chunks_test"


@pytest.fixture(scope="module")
def milvus_client():
    """MilvusClient connected to the remote Milvus server.

    Uses a separate test collection (seed_chunks_test) to avoid
    conflicting with persisted seed data (seed_chunks).
    """
    from pymilvus import MilvusClient

    client = MilvusClient(
        uri="http://10.222.124.211:19530",
        user="daduhe",
        password="gis31415",
        db_name="daduhe_milvus_database",
    )
    yield client
    # Cleanup: drop the test collection after tests
    if client.has_collection(TEST_COLLECTION):
        client.drop_collection(TEST_COLLECTION)


def test_milvus_collection_created(milvus_client):
    """create_milvus_collection must create a test collection."""
    from scripts.seed_data import create_milvus_collection

    create_milvus_collection(milvus_client, TEST_COLLECTION)

    assert milvus_client.has_collection(TEST_COLLECTION), (
        "seed_chunks collection was not created"
    )


def test_milvus_collection_schema_matches_icd(milvus_client):
    """Test collection must have explicit chunk_id/doc_id fields per ICD-01 §6.1."""
    from scripts.seed_data import create_milvus_collection

    create_milvus_collection(milvus_client, TEST_COLLECTION)

    info = milvus_client.describe_collection(TEST_COLLECTION)

    field_names = {f["name"] for f in info["fields"]}
    assert field_names == {"id", "chunk_id", "doc_id", "vector"}, (
        f"Unexpected fields: {field_names}"
    )

    vector_field = next(f for f in info["fields"] if f["name"] == "vector")
    assert vector_field["params"]["dim"] == 1024

    chunk_id_field = next(f for f in info["fields"] if f["name"] == "chunk_id")
    assert chunk_id_field["params"]["max_length"] == 64

    doc_id_field = next(f for f in info["fields"] if f["name"] == "doc_id")
    assert doc_id_field["params"]["max_length"] == 64


def test_vectors_inserted_into_milvus(milvus_client):
    """insert_embeddings_to_milvus must insert 15 vectors and return their Milvus IDs."""
    from scripts.seed_data import (
        create_milvus_collection,
        insert_embeddings_to_milvus,
        SEED_CHUNKS,
    )

    create_milvus_collection(milvus_client, TEST_COLLECTION)

    # Generate embeddings first (via Ollama)
    from scripts.seed_data import generate_embeddings

    vectors = generate_embeddings(SEED_CHUNKS)

    result = insert_embeddings_to_milvus(
        milvus_client, SEED_CHUNKS, vectors, TEST_COLLECTION
    )
    assert result["insert_count"] == 15, (
        f"Expected 15 inserts, got {result['insert_count']}"
    )
    assert len(result["ids"]) == 15, f"Expected 15 IDs, got {len(result['ids'])}"
    # All IDs should be integers
    assert all(isinstance(id_, int) for id_ in result["ids"])

    # Verify IVF_FLAT index was built after insertion (ICD-01 §6.2)
    idx = milvus_client.describe_index(TEST_COLLECTION, "vector")
    assert idx["index_type"] == "IVF_FLAT", (
        f"Expected IVF_FLAT, got {idx['index_type']}"
    )
    assert idx["metric_type"] == "COSINE", f"Expected COSINE, got {idx['metric_type']}"


def test_milvus_search_returns_similar_chunks(milvus_client):
    """Searching with a query text must return top-k similar chunks with scores."""
    from scripts.seed_data import (
        create_milvus_collection,
        insert_embeddings_to_milvus,
        generate_embeddings,
        SEED_CHUNKS,
    )
    import httpx

    create_milvus_collection(milvus_client, TEST_COLLECTION)

    vectors = generate_embeddings(SEED_CHUNKS)
    insert_embeddings_to_milvus(milvus_client, SEED_CHUNKS, vectors, TEST_COLLECTION)

    # Wait for Milvus to make data queryable
    milvus_client.load_collection(TEST_COLLECTION)

    # Generate query embedding
    query = "裂缝宽度大于0.3mm时需要采取什么处理措施？"
    resp = httpx.post(
        "http://localhost:11435/api/embeddings",
        json={"model": "bge-m3", "prompt": query},
        timeout=30,
    )
    query_vector = resp.json()["embedding"]

    results = milvus_client.search(
        collection_name=TEST_COLLECTION,
        data=[query_vector],
        limit=3,
        output_fields=["chunk_id", "doc_id"],
    )
    assert len(results) == 1
    hits = results[0]
    assert len(hits) >= 1, "Should return at least 1 similar chunk"
    # Top hit should have distance > 0.5 for COSINE (1.0 = identical)
    assert hits[0]["distance"] > 0.5, (
        f"Top hit similarity too low: {hits[0]['distance']}"
    )
    # Top hit must have chunk_id and doc_id in entity (ICD-01 §6.3)
    entity = hits[0].get("entity", {})
    assert entity.get("chunk_id", "").startswith("seed-chunk-"), (
        f"Missing chunk_id: {entity}"
    )
    assert entity.get("doc_id", "").startswith("seed-doc-"), f"Missing doc_id: {entity}"


# ============================================================
# Slice 5: Embedding metadata write-back to PostgreSQL
# ============================================================


def test_embeddings_metadata_inserted(db_conn, milvus_client):
    """insert_embeddings_metadata writes 15 records to metadata.embeddings."""
    from scripts.seed_data import (
        create_schema,
        insert_documents,
        insert_chunks,
        create_milvus_collection,
        insert_embeddings_to_milvus,
        generate_embeddings,
        insert_embeddings_metadata,
        SEED_CHUNKS,
    )

    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)
    create_milvus_collection(milvus_client, TEST_COLLECTION)

    vectors = generate_embeddings(SEED_CHUNKS)
    result = insert_embeddings_to_milvus(
        milvus_client, SEED_CHUNKS, vectors, TEST_COLLECTION
    )
    insert_embeddings_metadata(db_conn, SEED_CHUNKS, result["ids"])

    cur = db_conn.cursor()
    cur.execute(
        "SELECT count(*) FROM metadata.embeddings WHERE embedding_id LIKE 'seed-%'"
    )
    count = cur.fetchone()[0]
    assert count == 15, f"Expected 15 embedding records, got {count}"


def test_embeddings_have_valid_chunk_refs(db_conn):
    """Every seed embedding must reference a valid chunk in metadata.chunks."""
    cur = db_conn.cursor()
    cur.execute(
        "SELECT e.embedding_id, e.chunk_id FROM metadata.embeddings e "
        "LEFT JOIN metadata.chunks c ON e.chunk_id = c.chunk_id "
        "WHERE e.embedding_id LIKE 'seed-%' AND c.chunk_id IS NULL"
    )
    orphans = cur.fetchall()
    assert not orphans, f"Orphan embeddings (chunk_id not found): {orphans}"


def test_embeddings_have_correct_model_and_dim(db_conn):
    """All seed embeddings must use bge-m3 model and 1024 vector_dimension."""
    cur = db_conn.cursor()
    cur.execute(
        "SELECT embedding_id, embedding_model, vector_dimension, milvus_id "
        "FROM metadata.embeddings WHERE embedding_id LIKE 'seed-%' ORDER BY embedding_id"
    )
    rows = cur.fetchall()
    assert len(rows) == 15
    for emb_id, model, dim, milvus_id in rows:
        assert model == "bge-m3", f"{emb_id}: expected bge-m3, got {model}"
        assert dim == 1024, f"{emb_id}: expected 1024 dims, got {dim}"
        assert milvus_id > 0, f"{emb_id}: milvus_id should be positive, got {milvus_id}"


# ============================================================
# Slice 6: End-to-end retrieval verification
# ============================================================


def test_end_to_end_retrieval_by_crack_query(db_conn, milvus_client):
    """Query about crack repair must retrieve the crack treatment chunk as top hit."""
    from scripts.seed_data import (
        create_schema,
        insert_documents,
        insert_chunks,
        create_milvus_collection,
        insert_embeddings_to_milvus,
        generate_embeddings,
        insert_embeddings_metadata,
        retrieve_similar_chunks,
        SEED_CHUNKS,
    )

    # Full pipeline setup
    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)
    create_milvus_collection(milvus_client, TEST_COLLECTION)

    vectors = generate_embeddings(SEED_CHUNKS)
    result = insert_embeddings_to_milvus(
        milvus_client, SEED_CHUNKS, vectors, TEST_COLLECTION
    )
    insert_embeddings_metadata(db_conn, SEED_CHUNKS, result["ids"])

    milvus_client.load_collection(TEST_COLLECTION)

    # Query about crack repair
    results = retrieve_similar_chunks(
        query_text="裂缝宽度大于0.3mm时应该怎么处理？",
        ollama_url="http://localhost:11435",
        milvus_client=milvus_client,
        db_conn=db_conn,
        top_k=3,
        collection_name=TEST_COLLECTION,
    )

    assert len(results) >= 1, "Should return at least 1 result"
    # Each result must have the required fields
    for r in results:
        assert "chunk_id" in r
        assert "chunk_text" in r
        assert "doc_id" in r
        assert "title" in r
        assert "score" in r
        assert r["score"] > 0.5, f"Score too low for {r['chunk_id']}: {r['score']}"
        assert len(r["chunk_text"]) >= 50, f"Chunk text too short for {r['chunk_id']}"

    # Top result should be about crack treatment (chunk-002 is the crack treatment chunk)
    top = results[0]
    assert "裂缝" in top["chunk_text"], (
        f"Top result not about cracks: {top['chunk_text'][:80]}"
    )


def test_end_to_end_retrieval_by_seepage_query(db_conn, milvus_client):
    """Query about seepage must retrieve seepage-related chunks."""
    from scripts.seed_data import (
        create_schema,
        insert_documents,
        insert_chunks,
        create_milvus_collection,
        insert_embeddings_to_milvus,
        generate_embeddings,
        insert_embeddings_metadata,
        retrieve_similar_chunks,
        SEED_CHUNKS,
    )

    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)
    create_milvus_collection(milvus_client, TEST_COLLECTION)

    vectors = generate_embeddings(SEED_CHUNKS)
    result = insert_embeddings_to_milvus(
        milvus_client, SEED_CHUNKS, vectors, TEST_COLLECTION
    )
    insert_embeddings_metadata(db_conn, SEED_CHUNKS, result["ids"])

    milvus_client.load_collection(TEST_COLLECTION)

    results = retrieve_similar_chunks(
        query_text="坝基渗漏应该采用什么灌浆技术？",
        ollama_url="http://localhost:11435",
        milvus_client=milvus_client,
        db_conn=db_conn,
        top_k=3,
        collection_name=TEST_COLLECTION,
    )

    assert len(results) >= 1
    # At least one result should mention seepage/grouting
    texts = " ".join(r["chunk_text"] for r in results)
    assert "灌浆" in texts or "渗漏" in texts, "No seepage-related content in results"


def test_retrieval_results_are_deduplicated(db_conn, milvus_client):
    """Retrieved chunk_ids must be unique (no duplicates)."""
    from scripts.seed_data import (
        create_schema,
        insert_documents,
        insert_chunks,
        create_milvus_collection,
        insert_embeddings_to_milvus,
        generate_embeddings,
        insert_embeddings_metadata,
        retrieve_similar_chunks,
        SEED_CHUNKS,
    )

    create_schema(db_conn)
    insert_documents(db_conn)
    insert_chunks(db_conn)
    create_milvus_collection(milvus_client, TEST_COLLECTION)

    vectors = generate_embeddings(SEED_CHUNKS)
    result = insert_embeddings_to_milvus(
        milvus_client, SEED_CHUNKS, vectors, TEST_COLLECTION
    )
    insert_embeddings_metadata(db_conn, SEED_CHUNKS, result["ids"])

    milvus_client.load_collection(TEST_COLLECTION)

    results = retrieve_similar_chunks(
        query_text="混凝土碳化深度如何评定？",
        ollama_url="http://localhost:11435",
        milvus_client=milvus_client,
        db_conn=db_conn,
        top_k=5,
        collection_name=TEST_COLLECTION,
    )

    chunk_ids = [r["chunk_id"] for r in results]
    assert len(chunk_ids) == len(set(chunk_ids)), (
        f"Duplicate chunk_ids found: {chunk_ids}"
    )
