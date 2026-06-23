"""Configuration via environment variables with defaults."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SEARCH_"}

    # PostgreSQL
    pg_host: str = "localhost"
    pg_port: int = 5434
    pg_user: str = "daduhe"
    pg_password: str = "gis31415"
    pg_dbname: str = "mydatabase"

    # Milvus
    milvus_uri: str = "http://10.222.124.211:19530"
    milvus_user: str = "daduhe"
    milvus_password: str = "gis31415"
    milvus_db: str = "daduhe_milvus_database"
    milvus_collection: str = "seed_chunks"

    # Ollama
    ollama_url: str = "http://localhost:11435"

    # RRF
    rrf_k: int = 60

    # Vector search minimum cosine similarity threshold (0-1).
    # Hits below this are treated as noise and filtered out.
    vector_min_score: float = 0.45

    # LSL (not wired yet)
    lsl_base_url: str = "http://rule-extractor:3000"
