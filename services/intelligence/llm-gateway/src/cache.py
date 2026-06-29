"""LLM 响应缓存：PG 持久化 + TTL 过期 + 缓存键身份感知。

缓存键 = MD5(system_prompt + user_prompt + model + host)，确保切换
后端（vLLM vs DeepSeek）时自动 bust 缓存，因为 host 参与哈希。

TTL：超过 cache_ttl_seconds 的条目在 get() 时自动驱逐。
频繁使用的条目因 set() 刷新 created_at 而保持存活性。
"""

import hashlib
import json

import psycopg2

from src.settings import Settings


def compute_args_hash(*args: str) -> str:
    """对参数列表计算 MD5 哈希，生成缓存键。

    与 LightRAG 的 compute_args_hash 行为一致：将所有参数拼接后 MD5。

    Args:
        *args: 参与哈希的字符串参数。

    Returns:
        str: 32 位十六进制 MD5 哈希值。
    """
    return hashlib.md5("".join(args).encode("utf-8")).hexdigest()


class LLMCache:
    """基于 PostgreSQL 的 LLM 响应缓存。

    特性：
        - 缓存键包含 host（base_url），切换后端自动 bust 缓存
        - TTL 过期：get() 时自动过滤过期条目
        - ON CONFLICT upsert：重复 set() 会刷新 created_at（热条目保持存活）
        - 通过 cache_ttl_seconds=0 可全局禁用缓存
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 LLM 缓存。

        Args:
            settings: 应用配置，提供 PG 连接参数和 cache_ttl_seconds。
        """
        self._settings = settings

    @property
    def _enabled(self) -> bool:
        """缓存是否启用（cache_ttl_seconds > 0）。"""
        return self._settings.cache_ttl_seconds > 0

    def _get_conn(self):
        """创建新的 PostgreSQL 连接。"""
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
        """生成缓存键。

        缓存键 = MD5(system + user + model + host + response_format)。
        host 的不同值（vllm_url vs deepseek_url）确保不同后端的相同
        prompt 不会共享缓存。

        Args:
            model: 模型名称。
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            host: LLM 后端 base_url（用于区分后端）。
            response_format: 可选的响应格式约束。

        Returns:
            str: 32 位 MD5 缓存键。
        """
        return compute_args_hash(
            system_prompt,
            user_prompt,
            model,
            host,
            response_format,
        )

    def get(self, cache_key: str) -> dict | None:
        """查询缓存。

        仅返回未过期的条目（created_at > now() - TTL）。

        Args:
            cache_key: 缓存键。

        Returns:
            dict | None: 缓存的响应数据，miss 或过期时返回 None。
        """
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
        """写入或更新缓存。

        使用 ON CONFLICT upsert，重复 set() 会刷新 created_at 时间戳，
        使得频繁使用的条目持续保持存活性。

        Args:
            cache_key: 缓存键。
            model: 模型名称。
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            response: LLM 响应 dict，包含 content/model/prompt_tokens/completion_tokens/latency_ms。
        """
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
