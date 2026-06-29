"""模糊搜索后端：pg_trgm 相似度匹配。

使用 PostgreSQL pg_trgm 扩展的 similarity() 函数计算中文文本相似度。
中文 trigram 特征与拉丁语系不同，阈值 _SIM_THRESHOLD = 0.005 针对 2-4 字查询调优。
"""

from psycopg2.extensions import connection as PgConnection

from src.models import ChunkResult, ChunkMetadata, SearchFilters

# pg_trgm 中文相似度阈值。中文 trigram 与拉丁语系不同，
# 0.005 是针对 2-4 字短查询的实际调优值。
_SIM_THRESHOLD: float = 0.005


def search_fuzzy(
    conn: PgConnection,
    query: str,
    filters: SearchFilters,
    top_k: int,
) -> list[ChunkResult]:
    """pg_trgm 相似度模糊搜索，通过 PG JOIN 组装溯源元数据。

    依赖 PostgreSQL pg_trgm 扩展。similarity() 函数返回 0-1 之间的相似度分数。
    通过 JOIN metadata.documents 获取文档级元数据。

    Args:
        conn: PostgreSQL 连接。
        query: 搜索关键词（支持拼写错误容忍）。
        filters: 搜索过滤条件（doc_type, doc_ids, date 范围）。
        top_k: 返回结果数量上限。

    Returns:
        list[ChunkResult]: 按 similarity 降序排列的 chunk 结果列表。
    """
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
            sim,
        ) = row
        results.append(
            ChunkResult(
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
            )
        )

    return results
