"""LLM 响应缓存：基于 PostgreSQL graph_engine.llm_cache 表。

缓存键 = MD5(system_prompt + user_prompt + model)，对相同 prompt 避免重复 LLM 调用。
用于抽取管线中大量相同类型 prompt 的去重优化。
"""

import hashlib
import json

import psycopg2

from src.settings import Settings


class LLMCache:
    """基于 PostgreSQL 的 LLM 响应缓存。

    缓存键由 system_prompt + user_prompt + model 的 MD5 哈希生成。
    对相同输入返回缓存结果，避免重复调用 LLM。

    Attributes:
        _settings: 应用配置，提供 PG 连接参数。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化缓存。

        Args:
            settings: 应用配置。
        """
        self._settings = settings

    def _get_conn(self):
        """创建新的 PostgreSQL 连接。"""
        return psycopg2.connect(
            host=self._settings.pg_host,
            port=self._settings.pg_port,
            user=self._settings.pg_user,
            password=self._settings.pg_password,
            dbname=self._settings.pg_database,
        )

    @staticmethod
    def _cache_key(model: str, system_prompt: str, user_prompt: str) -> str:
        """计算缓存键：system + user + model 的 MD5 哈希。

        Args:
            model: LLM 模型名称。
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。

        Returns:
            32 位十六进制 MD5 字符串。
        """
        raw = system_prompt + user_prompt + model
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def get(self, model: str, system_prompt: str, user_prompt: str) -> dict | None:
        """查询缓存。

        Args:
            model: 模型名称。
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。

        Returns:
            缓存命中时返回 response dict，未命中返回 None。
        """
        key = self._cache_key(model, system_prompt, user_prompt)
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT response FROM graph_engine.llm_cache WHERE cache_key = %s",
                (key,),
            )
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            conn.close()

    def set(
        self, model: str, system_prompt: str, user_prompt: str, response: dict
    ) -> None:
        """写入缓存（INSERT ON CONFLICT 实现幂等更新）。

        Args:
            model: 模型名称。
            system_prompt: 系统提示词。
            user_prompt: 用户提示词。
            response: LLM 返回的完整 response dict。
        """
        key = self._cache_key(model, system_prompt, user_prompt)
        response_json = json.dumps(response)
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO graph_engine.llm_cache (cache_key, model, system_prompt, user_prompt, response)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    response = EXCLUDED.response,
                    created_at = now()
                """,
                (key, model, system_prompt, user_prompt, response_json),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def delete(self, cache_key: str) -> None:
        """删除指定缓存条目。

        Args:
            cache_key: 要删除的缓存键（MD5 哈希）。
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM graph_engine.llm_cache WHERE cache_key = %s",
                (cache_key,),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
