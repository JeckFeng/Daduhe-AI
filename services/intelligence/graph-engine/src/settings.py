"""配置管理：通过环境变量加载，前缀为 GRAPH_。

所有配置项均有合理默认值，开发环境可直接使用，生产环境通过环境变量覆盖。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """graph-engine 全局配置，环境变量前缀 GRAPH_。

    包含 Memgraph、PostgreSQL、Milvus、Ollama、LLM 网关等外部依赖的连接参数，
    以及抽取并发度、LLM token 限制、embedding 维度等运行时参数。
    """

    model_config = {"env_prefix": "GRAPH_"}

    # ── Memgraph 图数据库 ──────────────────────────────────────────
    memgraph_uri: str = "bolt://localhost:17687"
    memgraph_username: str = ""
    memgraph_password: str = ""
    memgraph_database: str = "memgraph"

    # ── PostgreSQL（通过 SSH 隧道连接远程） ─────────────────────────
    pg_host: str = "localhost"
    pg_port: int = 5434
    pg_user: str = "daduhe"
    pg_password: str = "gis31415"
    pg_database: str = "mydatabase"

    # ── LLM 网关（agent-reasoning 的 /api/v1/llm/completion） ──────
    llm_gateway_url: str = "http://localhost:8004"

    # ── 抽取参数 ───────────────────────────────────────────────────
    entity_extract_max_gleaning: int = 1
    max_source_ids_per_entity: int = 10
    prompt_profile_path: str = "entity_type/water_conservancy.yaml"

    # LLM 抽取输出上限（JSON 格式的 entities + relationships）
    extraction_llm_max_tokens: int = 4000

    # 并行抽取最大并发数
    extraction_max_async: int = 4

    # LLM map-reduce 合并参数
    merge_summary_context_size: int = 12000
    merge_summary_max_tokens: int = 500
    merge_summary_language: str = "Chinese"

    # ── Milvus 向量数据库 ──────────────────────────────────────────
    milvus_uri: str = "http://10.222.124.211:19530"
    milvus_user: str = "daduhe"
    milvus_password: str = "gis31415"
    milvus_db: str = "daduhe_milvus_database"
    milvus_entity_collection: str = "graph_entities"
    milvus_relation_collection: str = "graph_relationships"

    # ── Embedding（Ollama bge-m3） ─────────────────────────────────
    ollama_url: str = "http://localhost:11435"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # ── 图查询参数 ─────────────────────────────────────────────────
    graph_search_top_k: int = 10
