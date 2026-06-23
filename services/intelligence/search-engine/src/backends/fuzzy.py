from src.models import ChunkResult, ChunkMetadata, SearchFilters

# pg_trgm similarity threshold for Chinese text. Chinese trigrams differ from
# Latin-based languages; 0.01 is pragmatic for 2-4 character queries.
_SIM_THRESHOLD = 0.005


def search_fuzzy(conn, query: str, filters: SearchFilters, top_k: int) -> list[ChunkResult]:
    """pg_trgm similarity-based fuzzy search with PG JOIN for metadata."""
    where_clauses = ["similarity(c.chunk_text, %(query)s) > %(threshold)s"]
    params = {"query": query, "threshold": _SIM_THRESHOLD, "limit": top_k}

    if filters.doc_type:
        where_clauses.append("d.doc_type = ANY(%(doc_type)s)")
        params["doc_type"] = filters.doc_type
    if filters.doc_ids:
        where_clauses.append("c.doc_id = ANY(%(doc_ids)s)")
        params["doc_ids"] = filters.doc_ids

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT
            c.chunk_id,
            c.chunk_text,
            c.page_number,
            c.section_title,
            c.section_number,
            d.doc_id,
            d.doc_type,
            d.title,
            similarity(c.chunk_text, %(query)s) AS sim
        FROM metadata.chunks c
        JOIN metadata.documents d ON c.doc_id = d.doc_id
        WHERE {where_sql}
        ORDER BY sim DESC
        LIMIT %(limit)s
    """

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    results = []
    for row in rows:
        chunk_id, chunk_text, page_number, section_title, section_number, doc_id, doc_type, title, sim = row
        results.append(ChunkResult(
            chunk_id=chunk_id,
            text=chunk_text,
            score=round(float(sim), 4),
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

    return results
