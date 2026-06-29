"""关键词搜索后端：PG ILIKE 精确匹配。

使用 SQL LIKE/ILIKE 进行大小写不敏感关键词匹配。
通过 JOIN metadata.documents 组装完整溯源元数据。
评分 = chunk 文本中关键词出现的次数。
"""

from psycopg2.extensions import connection as PgConnection

from src.models import ChunkResult, ChunkMetadata, SearchFilters


def search_keyword(
    conn: PgConnection,
    query: str,
    filters: SearchFilters,
    top_k: int,
) -> list[ChunkResult]:
    """ILIKE 关键词搜索，通过 PG JOIN 组装溯源元数据。

    评分策略：统计 chunk_text 中关键词的出现次数（hit_count），
    按 hit_count 降序排列。该评分对短查询效果较好，对长查询偏低。

    Args:
        conn: PostgreSQL 连接。
        query: 搜索关键词。
        filters: 搜索过滤条件（doc_type, doc_ids, date 范围）。
        top_k: 返回结果数量上限。

    Returns:
        list[ChunkResult]: 按 hit_count 降序排列的 chunk 结果列表。
    """
    where_clauses = ["LOWER(c.chunk_text) LIKE LOWER(%(pattern)s)"]
    params = {"pattern": f"%{query}%", "limit": top_k}

    if filters.doc_type:
        where_clauses.append("d.doc_type = ANY(%(doc_type)s)")
        params["doc_type"] = filters.doc_type
    if filters.doc_ids:
        where_clauses.append("c.doc_id = ANY(%(doc_ids)s)")
        params["doc_ids"] = filters.doc_ids

    where_sql = " AND ".join(where_clauses)

    # hit_count = chunk_text 中移除了关键词后减少的长度 ÷ 关键词长度
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

    results: list[ChunkResult] = []
    for row in rows:
        (
            chunk_id,
            chunk_text,
            page_number,
            section_title,
            section_number,
            doc_id,
            doc_type,
            title,
            hit_count,
        ) = row
        results.append(
            ChunkResult(
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
            )
        )

    return results
