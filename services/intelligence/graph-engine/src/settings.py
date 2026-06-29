"""graph-engine 配置 — YAML 文件提供默认值，环境变量 GRAPH_ 前缀覆盖。

基础设施配置（PG / Milvus / Ollama / Memgraph）→ config/infrastructure.yaml
服务间调用和业务配置 → config/services.yaml
环境变量 > YAML 配置 > Python default
"""

from pathlib import Path
import yaml
from pydantic_settings import BaseSettings

# ── YAML 配置加载 ────────────────────────────────────────────
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _yaml(name: str) -> dict:
    path = _CONFIG_DIR / name
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_infra = _yaml("infrastructure.yaml")
_services = _yaml("services.yaml")


def _get(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return default if d is None else d


class Settings(BaseSettings):
    """graph-engine 全局配置，环境变量前缀 GRAPH_。

    包含 Memgraph、PostgreSQL、Milvus、Ollama、LLM 网关等外部依赖的连接参数，
    以及抽取并发度、LLM token 限制、embedding 维度等运行时参数。
    """

    model_config = {"env_prefix": "GRAPH_"}

    # ── Memgraph 图数据库 ──
    memgraph_uri: str = _get(_infra, "memgraph", "uri", default="bolt://localhost:17687")
    memgraph_username: str = _get(_infra, "memgraph", "username", default="")
    memgraph_password: str = _get(_infra, "memgraph", "password", default="")
    memgraph_database: str = _get(_infra, "memgraph", "database", default="memgraph")

    # ── PostgreSQL ──
    pg_host: str = _get(_infra, "postgresql", "host", default="localhost")
    pg_port: int = _get(_infra, "postgresql", "port", default=5432)
    pg_user: str = _get(_infra, "postgresql", "user", default="")
    pg_password: str = _get(_infra, "postgresql", "password", default="")
    pg_database: str = _get(_infra, "postgresql", "database", default="")

    # ── LLM 网关 ──
    llm_gateway_url: str = _get(
        _services, "agent_reasoning", "llm_gateway_url",
        default="http://localhost:8004",
    )

    # ── Milvus 向量数据库 ──
    milvus_uri: str = _get(_infra, "milvus", "uri", default="http://localhost:19530")
    milvus_user: str = _get(_infra, "milvus", "user", default="")
    milvus_password: str = _get(_infra, "milvus", "password", default="")
    milvus_db: str = _get(_infra, "milvus", "database", default="")
    milvus_entity_collection: str = _get(
        _services, "graph_engine", "milvus_entity_collection",
        default="graph_entities",
    )
    milvus_relation_collection: str = _get(
        _services, "graph_engine", "milvus_relation_collection",
        default="graph_relationships",
    )

    # ── Ollama embedding ──
    ollama_url: str = _get(_infra, "ollama", "url", default="http://localhost:11434")
    embedding_model: str = _get(_infra, "ollama", "embedding_model", default="bge-m3")
    embedding_dim: int = _get(_infra, "ollama", "embedding_dim", default=1024)

    # ── Prompt 配置 ──
    prompt_profile_path: str = _get(
        _services, "graph_engine", "prompt_profile_path",
        default="entity_type/water_conservancy.yaml",
    )

    # ── 抽取参数（业务调优，不属于基础设施配置）──
    entity_extract_max_gleaning: int = 1
    max_source_ids_per_entity: int = 10
    extraction_llm_max_tokens: int = 4000
    extraction_max_async: int = 4
    merge_summary_context_size: int = 12000
    merge_summary_max_tokens: int = 500
    merge_summary_language: str = "Chinese"
    graph_search_top_k: int = 10
