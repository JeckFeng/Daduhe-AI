"""Hybrid search via Reciprocal Rank Fusion (RRF).

Currently = vector results only, with empty slots for keyword, fuzzy, and rules.
The function signature is designed so adding a new source is just passing an extra
rank list — no signature changes needed.
"""
from pymilvus import MilvusClient

from src.models import ChunkResult, SearchFilters, RuleResult
from src.backends.vector import search_vector


def search_hybrid(
    milvus_client: MilvusClient,
    ollama_url: str,
    pg_conn,
    query: str,
    filters: SearchFilters,
    top_k: int,
    collection_name: str,
    rrf_k: int = 60,
    keyword_ranks: list[ChunkResult] | None = None,
    fuzzy_ranks: list[ChunkResult] | None = None,
    rules_results: list[RuleResult] | None = None,
) -> list[ChunkResult]:
    """RRF fusion of multiple retrieval sources.

    Slots for keyword_ranks, fuzzy_ranks, and rules_results are accepted but
    currently unused. Adding a new source is just passing the list — no
    signature changes needed.
    """
    source_lists: list[list[ChunkResult]] = []

    # Vector (always active)
    vector_results = search_vector(
        milvus_client, ollama_url, pg_conn, query, filters, top_k,
        collection_name,
    )
    source_lists.append(vector_results)

    # Reserved slots — add here when sources are ready
    # if keyword_ranks:
    #     source_lists.append(keyword_ranks)
    # if fuzzy_ranks:
    #     source_lists.append(fuzzy_ranks)

    if len(source_lists) == 1:
        return source_lists[0][:top_k]

    # RRF scoring
    rrf_scores: dict[str, tuple[float, ChunkResult]] = {}
    for src_results in source_lists:
        for rank, item in enumerate(src_results, start=1):
            key = item.chunk_id
            rrf = 1.0 / (rrf_k + rank)
            if key in rrf_scores:
                old_score, old_item = rrf_scores[key]
                rrf_scores[key] = (old_score + rrf, old_item)
            else:
                rrf_scores[key] = (rrf, item)

    merged = sorted(rrf_scores.values(), key=lambda x: x[0], reverse=True)
    results = []
    for rrf_score, item in merged[:top_k]:
        item.score = round(rrf_score, 4)
        results.append(item)
    return results
