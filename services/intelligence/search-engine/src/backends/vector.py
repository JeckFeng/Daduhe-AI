import httpx
from pymilvus import MilvusClient

from src.models import ChunkResult, ChunkMetadata, SearchFilters
from src.settings import Settings


def search_vector(
    milvus_client: MilvusClient,
    ollama_url: str,
    pg_conn,
    query: str,
    filters: SearchFilters,
    top_k: int,
    collection_name: str,
    min_score: float | None = None,
) -> list[ChunkResult]:
    """Ollama embed → Milvus COSINE search → PG metadata enrichment."""
    threshold = min_score if min_score is not None else Settings().vector_min_score
    # 1. Embed query with Ollama bge-m3
    resp = httpx.post(
        f"{ollama_url}/api/embeddings",
        json={"model": "bge-m3", "prompt": query},
        timeout=30,
    )
    resp.raise_for_status()
    query_vector = resp.json()["embedding"]

    # 2. Search Milvus
    milvus_client.load_collection(collection_name)
    search_results = milvus_client.search(
        collection_name=collection_name,
        data=[query_vector],
        limit=top_k,
        output_fields=["chunk_id", "doc_id"],
    )

    if not search_results or not search_results[0]:
        return []

    # Collect chunk_ids and scores; drop hits below min threshold
    hits = {}
    for hit in search_results[0]:
        entity = hit.get("entity", {})
        chunk_id = entity.get("chunk_id", "")
        score = hit["distance"]
        if chunk_id and score >= threshold:
            hits[chunk_id] = score

    if not hits:
        return []

    # 3. Enrich metadata from PostgreSQL
    where_clauses = ["c.chunk_id = ANY(%(chunk_ids)s)"]
    params = {"chunk_ids": list(hits.keys())}

    if filters.doc_ids:
        where_clauses.append("c.doc_id = ANY(%(doc_ids)s)")
        params["doc_ids"] = filters.doc_ids

    where_sql = " AND ".join(where_clauses)

    cur = pg_conn.cursor()
    cur.execute(f"""
        SELECT
            c.chunk_id,
            c.chunk_text,
            c.page_number,
            c.section_title,
            c.section_number,
            d.doc_id,
            d.doc_type,
            d.title
        FROM metadata.chunks c
        JOIN metadata.documents d ON c.doc_id = d.doc_id
        WHERE {where_sql}
    """, params)
    rows = cur.fetchall()
    cur.close()

    results = []
    for row in rows:
        chunk_id, chunk_text, page_number, section_title, section_number, doc_id, doc_type, title = row
        results.append(ChunkResult(
            chunk_id=chunk_id,
            text=chunk_text,
            score=round(hits[chunk_id], 4),
            metadata=ChunkMetadata(
                doc_id=doc_id,
                doc_type=doc_type,
                title=title,
                section_number=section_number,
                section_title=section_title,
                page_number=page_number,
                download_url=f"/api/v1/documents/{doc_id}/download",
            ),
        ))

    # Sort by score descending
    results.sort(key=lambda x: x.score, reverse=True)
    return results
