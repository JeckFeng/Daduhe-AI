"""llm-gateway 配置 — YAML 文件提供默认值，环境变量 LLM_GATEWAY_ 前缀覆盖。

基础设施配置（PG）→ config/infrastructure.yaml
LLM 后端和调用策略 → config/services.yaml
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
    """llm-gateway 服务配置，环境变量前缀 LLM_GATEWAY_。

    所有字段支持通过 LLM_GATEWAY_{FIELD_NAME} 环境变量覆盖。
    """

    model_config = {"env_prefix": "LLM_GATEWAY_"}

    # ── DeepSeek API ──
    deepseek_api_key: str = _get(
        _services, "llm_gateway", "deepseek_api_key", default=""
    )
    deepseek_api_url: str = _get(
        _services, "llm_gateway", "deepseek_api_url",
        default="https://api.deepseek.com/v1",
    )

    # ── 本地 vLLM ──
    vllm_url: str = _get(
        _services, "llm_gateway", "vllm_url",
        default="http://localhost:8000/v1",
    )
    vllm_model: str = _get(_services, "llm_gateway", "vllm_model", default="")

    # ── 调用策略 ──
    default_model: str = _get(
        _services, "llm_gateway", "default_model", default="vllm-local"
    )
    realtime_timeout: int = 30
    batch_timeout: int = 120

    # ── LLM 缓存 ──
    cache_ttl_seconds: int = 604800

    # ── PostgreSQL ──
    pg_host: str = _get(_infra, "postgresql", "host", default="localhost")
    pg_port: int = _get(_infra, "postgresql", "port", default=5432)
    pg_user: str = _get(_infra, "postgresql", "user", default="")
    pg_password: str = _get(_infra, "postgresql", "password", default="")
    pg_database: str = _get(_infra, "postgresql", "database", default="")
