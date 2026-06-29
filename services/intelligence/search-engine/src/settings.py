"""search-engine 配置 — YAML 文件提供默认值，环境变量 SEARCH_ 前缀覆盖。

基础设施配置（PG / Milvus / Ollama）→ config/infrastructure.yaml
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
    """search-engine 服务配置，环境变量前缀 SEARCH_。

    所有字段支持通过 SEARCH_{FIELD_NAME} 环境变量覆盖。
    """

    model_config = {"env_prefix": "SEARCH_"}

    # ── PostgreSQL ──
    pg_host: str = _get(_infra, "postgresql", "host", default="localhost")
    pg_port: int = _get(_infra, "postgresql", "port", default=5432)
    pg_user: str = _get(_infra, "postgresql", "user", default="")
    pg_password: str = _get(_infra, "postgresql", "password", default="")
    pg_dbname: str = _get(_infra, "postgresql", "database", default="")

    # ── Milvus 向量数据库 ──
    milvus_uri: str = _get(_infra, "milvus", "uri", default="http://localhost:19530")
    milvus_user: str = _get(_infra, "milvus", "user", default="")
    milvus_password: str = _get(_infra, "milvus", "password", default="")
    milvus_db: str = _get(_infra, "milvus", "database", default="")
    milvus_collection: str = _get(
        _services, "search_engine", "milvus_collection", default="seed_chunks"
    )

    # ── Ollama embedding ──
    ollama_url: str = _get(_infra, "ollama", "url", default="http://localhost:11434")

    # ── LSL rule-extractor ──
    lsl_base_url: str = _get(
        _services, "search_engine", "lsl_base_url",
        default="http://rule-extractor:3000",
    )

    # ── 检索参数（业务调优）──
    rrf_k: int = 60
    vector_min_score: float = 0.45
