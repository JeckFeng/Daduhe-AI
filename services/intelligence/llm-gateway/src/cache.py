"""LLM response cache with LightRAG-style cache identity.

Cache key = hash(system_prompt + user_prompt + model + host + response_format).
Switching model backends automatically busts the cache because host is in the hash.

TTL: entries older than cache_ttl_seconds are evicted on get().
Frequently-used entries stay alive because set() refreshes created_at.
"""

import hashlib
import json

import psycopg2

from src.settings import Settings


def compute_args_hash(*args: str) -> str:
    """Hash arguments for cache key, mirroring LightRAG's compute_args_hash."""
    return hashlib.md5("".join(args).encode("utf-8")).hexdigest()


class LLMCache:
    """PG-based LLM response cache with TTL and cache-identity-aware keys."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def _enabled(self) -> bool:
        return self._settings.cache_ttl_seconds > 0

    def _get_conn(self):
        return psycopg2.connect(
            host=self._settings.pg_host,
            port=self._settings.pg_port,
            user=self._settings.pg_user,
            password=self._settings.pg_password,
            dbname=self._settings.pg_database,
        )

    def cache_key(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        host: str = "",
        response_format: str = "",
    ) -> str:
        """Build a cache key that includes host (base_url) so switching
        backends (vllm vs deepseek) automatically busts the cache."""
        return compute_args_hash(
            system_prompt,
            user_prompt,
            model,
            host,
            response_format,
        )

    def get(self, cache_key: str) -> dict | None:
        """Retrieve cached response, or None if miss or expired."""
        if not self._enabled:
            return None
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT response
                FROM llm_gateway.llm_cache
                WHERE cache_key = %s
                  AND created_at > now() - make_interval(secs => %s)
                """,
                (cache_key, self._settings.cache_ttl_seconds),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            conn.close()

    def set(
        self,
        cache_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response: dict,
    ) -> None:
        """Insert or update cached response."""
        if not self._enabled:
            return
        response_json = json.dumps(response, ensure_ascii=False)
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO llm_gateway.llm_cache
                    (cache_key, model, system_prompt, user_prompt, response)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    response = EXCLUDED.response,
                    created_at = now()
                """,
                (cache_key, model, system_prompt, user_prompt, response_json),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
