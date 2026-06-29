"""Configuration via environment variables with LLM_GATEWAY_ prefix."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "LLM_GATEWAY_"}

    # LLM backends
    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com/v1"
    vllm_url: str = "http://10.222.124.211:8000/v1"
    vllm_model: str = (
        "/home/gyyknowledge/modelscope/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf"
    )

    default_model: str = "vllm-local"
    realtime_timeout: int = 30
    batch_timeout: int = 120

    # LLM cache TTL (seconds). 0 = cache disabled.
    cache_ttl_seconds: int = 604800  # 7 days

    # PostgreSQL (for LLM cache)
    pg_host: str = "localhost"
    pg_port: int = 5434
    pg_user: str = "daduhe"
    pg_password: str = "gis31415"
    pg_database: str = "mydatabase"
