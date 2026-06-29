"""PG chunk 读取器：从 metadata.chunks 表读取文档的 chunk 数据。

用于抽取管线第一阶段——获取待抽取的 chunk 文本列表。
"""

import psycopg2
import psycopg2.extras

from src.settings import Settings


class PgChunkReader:
    """从 PostgreSQL metadata.chunks 表读取 chunk 数据。

    按 chunk_index 排序，返回包含文档元数据（标题、页码、章节）的 chunk 列表。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 chunk 读取器。

        Args:
            settings: 应用配置，提供 PG 连接参数。
        """
        self._settings = settings

    def _connect(self):
        """创建新的 PostgreSQL 连接。"""
        return psycopg2.connect(
            host=self._settings.pg_host,
            port=self._settings.pg_port,
            user=self._settings.pg_user,
            password=self._settings.pg_password,
            dbname=self._settings.pg_database,
        )

    def read_chunks_by_doc_id(self, doc_id: str) -> list[dict]:
        """按 doc_id 读取所有 chunk，按 chunk_index 排序。

        Args:
            doc_id: 文档 ID。

        Returns:
            list[dict]: chunk 列表，每个元素包含 chunk_id, doc_id, content,
                        page_number, section_title, doc_title 字段。
        """
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                "SELECT c.chunk_id, c.doc_id, c.chunk_text AS content, "
                "c.page_number, c.section_title, d.title AS doc_title "
                "FROM metadata.chunks c "
                "LEFT JOIN metadata.documents d ON c.doc_id = d.doc_id "
                "WHERE c.doc_id = %s "
                "ORDER BY COALESCE(c.chunk_index, 0)",
                (doc_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
        finally:
            conn.close()
