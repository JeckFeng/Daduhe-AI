"""向量搜索后端：Ollama embedding → Milvus COSINE 检索 → PG 元数据补全。

三步流程：
1. Ollama bge-m3 将 query 转为 1024 维向量
2. Milvus COSINE 相似度搜索 top_k 个候选
3. 按 min_score 阈值过滤后，从 PG 批量补全溯源元数据
"""

import httpx
from pymilvus import MilvusClient
from psycopg2.extensions import connection as PgConnection

from src.models import ChunkResult, ChunkMetadata, SearchFilters
from src.settings import Settings


def search_vector(
    milvus_client: MilvusClient,
    ollama_url: str,
    pg_conn: PgConnection,
    query: str,
    filters: SearchFilters,
    top_k: int,
    collection_name: str,
    min_score: float | None = None,
) -> list[ChunkResult]:
    """Ollama embedding → Milvus COSINE 检索 → PG 元数据补全。

    检索流程：
        1. Ollama bge-m3 生成 query embedding（1024 维）
        2. Milvus COSINE 搜索 top_k 候选 chunk
        3. 按 min_score（默认 vector_min_score=0.45）过滤低分命中
        4. 从 PG metadata.chunks JOIN metadata.documents 批量补全元数据
        5. 按 COSINE 分数降序排列返回

    Args:
        milvus_client: pymilvus MilvusClient 实例。
        ollama_url: Ollama 服务地址。
        pg_conn: PostgreSQL 连接。
        query: 搜索文本。
        filters: 搜索过滤条件。
        top_k: Milvus 搜索候选数（元数据补全后可能因 PG JOIN 进一步减少）。
        collection_name: Milvus collection 名称。
        min_score: 最小 COSINE 阈值，None 时使用 Settings().vector_min_score。

    Returns:
        list[ChunkResult]: 按 COSINE 分数降序排列的 chunk 结果列表。
    """
    # 确定过滤阈值
    threshold = min_score if min_score is not None else Settings().vector_min_score

    # 1. Ollama embedding
    resp = httpx.post(
        f"{ollama_url}/api/embeddings",
        json={"model": "bge-m3", "prompt": query},
        timeout=30,
    )
    resp.raise_for_status()
    query_vector = resp.json()["embedding"]

    # 2. Milvus COSINE 向量检索
    milvus_client.load_collection(collection_name)
    search_results = milvus_client.search(
        collection_name=collection_name,
        data=[query_vector],
        limit=top_k,
        output_fields=["chunk_id", "doc_id"],
    )

    if not search_results or not search_results[0]:
        return []

    # 3. 阈值过滤：仅保留 COSINE >= threshold 的命中
    hits: dict[str, float] = {}
    for hit in search_results[0]:
        entity = hit.get("entity", {})
        chunk_id = entity.get("chunk_id", "")
        score = hit["distance"]
        if chunk_id and score >= threshold:
            hits[chunk_id] = score

    if not hits:
        return []

    # 4. PG 批量元数据补全 — JOIN metadata.documents 获取所有溯源字段
    where_clauses = ["c.chunk_id = ANY(%(chunk_ids)s)"]
    params = {"chunk_ids": list(hits.keys())}

    if filters.doc_ids:
        where_clauses.append("c.doc_id = ANY(%(doc_ids)s)")
        params["doc_ids"] = filters.doc_ids

    where_sql = " AND ".join(where_clauses)

    cur = pg_conn.cursor()
    cur.execute(
        f"""
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
    """,
        params,
    )
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
        ) = row
        results.append(
            ChunkResult(
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
            )
        )

    # 按 COSINE 分数降序排列
    results.sort(key=lambda x: x.score, reverse=True)
    return results
