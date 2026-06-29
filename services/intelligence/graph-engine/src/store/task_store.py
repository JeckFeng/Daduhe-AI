"""PG 任务存储：抽取任务的 CRUD 操作。

管理 graph_engine.extraction_tasks 表，支持任务创建、状态更新、进度记录和结果写入。
"""

from datetime import datetime, timezone
from uuid import uuid4

import psycopg2
import psycopg2.extras

from src.settings import Settings


class TaskStore:
    """graph_engine.extraction_tasks 表的 CRUD 操作。

    提供任务创建、状态查询/更新、进度记录和结果持久化功能。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化任务存储。

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

    def find_by_doc_id(self, doc_id: str) -> dict | None:
        """按 doc_id 查找最近的任务。

        Args:
            doc_id: 文档 ID。

        Returns:
            最近创建的任务 dict，若无则返回 None。包含 task_id, doc_id, status,
            progress, result, error_message 字段。
        """
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                "SELECT task_id, doc_id, status, progress, result, error_message "
                "FROM graph_engine.extraction_tasks "
                "WHERE doc_id = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (doc_id,),
            )
            row = cur.fetchone()
            cur.close()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    def create_task(self, doc_id: str, status: str = "pending") -> dict:
        """创建新任务。

        Args:
            doc_id: 文档 ID。
            status: 初始状态，默认 "pending"。

        Returns:
            创建的任务 dict，包含 task_id, doc_id, status, created_at。
        """
        task_id = f"g-task-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.autocommit = True
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                "INSERT INTO graph_engine.extraction_tasks "
                "(task_id, doc_id, status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (task_id, doc_id, status, now, now),
            )
            cur.close()
            return {
                "task_id": task_id,
                "doc_id": doc_id,
                "status": status,
                "created_at": now.isoformat(),
            }
        finally:
            conn.close()

    def update_status(
        self, task_id: str, status: str, error_message: str | None = None
    ) -> None:
        """更新任务状态。

        Args:
            task_id: 任务 ID。
            status: 新状态（pending/processing/completed/failed）。
            error_message: 失败时的错误描述，可选。
        """
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                "UPDATE graph_engine.extraction_tasks "
                "SET status = %s, updated_at = %s, error_message = %s "
                "WHERE task_id = %s",
                (status, now, error_message, task_id),
            )
            cur.close()
        finally:
            conn.close()

    def update_progress(self, task_id: str, progress: dict) -> None:
        """更新任务进度（JSONB 字段）。

        Args:
            task_id: 任务 ID。
            progress: 进度信息 dict，如 {"phase": "extraction", "completed": 5, "total": 10}。
        """
        now = datetime.now(timezone.utc)
        import json

        conn = self._connect()
        try:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                "UPDATE graph_engine.extraction_tasks "
                "SET progress = %s, updated_at = %s "
                "WHERE task_id = %s",
                (json.dumps(progress), now, task_id),
            )
            cur.close()
        finally:
            conn.close()

    def update_result(self, task_id: str, result: dict) -> None:
        """写入任务结果并将状态置为 completed。

        Args:
            task_id: 任务 ID。
            result: 结果 dict，如 {"entity_count": 15, "relationship_count": 22, ...}。
        """
        now = datetime.now(timezone.utc)
        import json

        conn = self._connect()
        try:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                "UPDATE graph_engine.extraction_tasks "
                "SET result = %s, status = 'completed', updated_at = %s, completed_at = %s "
                "WHERE task_id = %s",
                (json.dumps(result), now, now, task_id),
            )
            cur.close()
        finally:
            conn.close()
