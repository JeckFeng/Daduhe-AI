"""混合检索后端：Reciprocal Rank Fusion (RRF) 多路结果融合。

当前实现 = 仅向量检索结果（keyword、fuzzy、rules 三个槽位已预留）。
函数签名设计支持增量添加新数据源 — 只需传入新的 rank 列表，无需修改签名。

RRF 公式: score(chunk) = Σ 1/(k + rank_i)，其中 k = rrf_k（默认 60）。
"""

from pymilvus import MilvusClient
from psycopg2.extensions import connection as PgConnection

from src.models import ChunkResult, SearchFilters, RuleResult
from src.backends.vector import search_vector


def search_hybrid(
    milvus_client: MilvusClient,
    ollama_url: str,
    pg_conn: PgConnection,
    query: str,
    filters: SearchFilters,
    top_k: int,
    collection_name: str,
    rrf_k: int = 60,
    keyword_ranks: list[ChunkResult] | None = None,
    fuzzy_ranks: list[ChunkResult] | None = None,
    rules_results: list[RuleResult] | None = None,
) -> list[ChunkResult]:
    """RRF 多路检索结果融合。

    多路召回后按 RRF 公式加权合并：
        RRF_score(chunk) = Σ 1/(k + rank_position)
    其中 k = rrf_k，rank_position 从 1 开始。最终按 RRF 总分降序排列。

    keyword_ranks / fuzzy_ranks / rules_results 当前为预留槽位，
    传入 None 或空列表时自动跳过。添加新数据源只需传入对应列表，
    无需修改函数签名。

    Args:
        milvus_client: pymilvus MilvusClient 实例。
        ollama_url: Ollama 服务地址。
        pg_conn: PostgreSQL 连接。
        query: 搜索文本。
        filters: 搜索过滤条件。
        top_k: 最终返回结果数量上限。
        collection_name: Milvus collection 名称。
        rrf_k: RRF 融合常数（默认 60），值越大排名差异影响越小。
        keyword_ranks: 关键词搜索结果（预留槽位）。
        fuzzy_ranks: 模糊搜索结果（预留槽位）。
        rules_results: LSL 规则搜索结果（预留槽位）。

    Returns:
        list[ChunkResult]: 按 RRF 分数降序排列的 top_k 条结果。
    """
    source_lists: list[list[ChunkResult]] = []

    # 向量检索（始终启用）
    vector_results = search_vector(
        milvus_client,
        ollama_url,
        pg_conn,
        query,
        filters,
        top_k,
        collection_name,
    )
    source_lists.append(vector_results)

    # 预留槽位 — 后续服务就绪后取消注释即可启用
    # if keyword_ranks:
    #     source_lists.append(keyword_ranks)
    # if fuzzy_ranks:
    #     source_lists.append(fuzzy_ranks)

    # 单路检索时直接截断返回，无需 RRF 计算
    if len(source_lists) == 1:
        return source_lists[0][:top_k]

    # RRF 多路融合：按 chunk_id 聚合各路的 RRF 分数
    rrf_scores: dict[str, tuple[float, ChunkResult]] = {}
    for src_results in source_lists:
        for rank, item in enumerate(src_results, start=1):
            key = item.chunk_id
            rrf = 1.0 / (rrf_k + rank)
            if key in rrf_scores:
                # 同一 chunk 在多路中出现 → 累加 RRF 分数
                old_score, old_item = rrf_scores[key]
                rrf_scores[key] = (old_score + rrf, old_item)
            else:
                rrf_scores[key] = (rrf, item)

    # 按 RRF 总分降序排列，截取 top_k
    merged = sorted(rrf_scores.values(), key=lambda x: x[0], reverse=True)
    results: list[ChunkResult] = []
    for rrf_score, item in merged[:top_k]:
        item.score = round(rrf_score, 4)
        results.append(item)
    return results
