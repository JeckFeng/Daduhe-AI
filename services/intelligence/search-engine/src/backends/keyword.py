from src.models import ChunkResult, ChunkMetadata, SearchFilters


def search_keyword(conn, query: str, filters: SearchFilters, top_k: int) -> list[ChunkResult]:
    """ILIKE keyword search with PG JOIN for metadata assembly."""
    where_clauses = ["LOWER(c.chunk_text) LIKE LOWER(%(pattern)s)"]
    params = {"pattern": f"%{query}%", "limit": top_k}

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
            (LENGTH(c.chunk_text) - LENGTH(REPLACE(LOWER(c.chunk_text), LOWER(%(query)s), ''))) / NULLIF(LENGTH(%(query)s), 0) AS hit_count
        FROM metadata.chunks c
        JOIN metadata.documents d ON c.doc_id = d.doc_id
        WHERE {where_sql}
        ORDER BY hit_count DESC
        LIMIT %(limit)s
    """
    params["query"] = query

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    results = []
    for row in rows:
        chunk_id, chunk_text, page_number, section_title, section_number, doc_id, doc_type, title, hit_count = row
        results.append(ChunkResult(
            chunk_id=chunk_id,
            text=chunk_text,
            score=float(hit_count or 0),
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
