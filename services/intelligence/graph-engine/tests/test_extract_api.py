"""Integration tests for POST /api/v1/graph/extract — idempotency + task management."""

import pytest
import pytest_asyncio
import psycopg2
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.settings import Settings

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
def settings():
    return Settings()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _pg_conn(settings):
    return psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        user=settings.pg_user,
        password=settings.pg_password,
        dbname=settings.pg_database,
    )


@pytest_asyncio.fixture
async def clean_tasks(settings):
    conn = _pg_conn(settings)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DELETE FROM graph_engine.extraction_tasks")
    cur.close()
    conn.close()
    yield
    conn = _pg_conn(settings)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DELETE FROM graph_engine.extraction_tasks")
    cur.close()
    conn.close()


class TestExtractIdempotency:
    async def test_first_request_returns_202(self, client, clean_tasks):
        """First POST /extract → 202 + task_id."""
        r = await client.post("/api/v1/graph/extract", json={"doc_id": "seed-doc-001"})
        assert r.status_code == 202
        data = r.json()
        assert data["code"] == 0
        assert "task_id" in data["data"]
        assert data["data"]["status"] in ("processing", "pending")

    async def test_duplicate_request_while_processing_returns_409(
        self, client, clean_tasks
    ):
        """Second POST /extract for same doc_id while pending → 409."""
        r1 = await client.post("/api/v1/graph/extract", json={"doc_id": "test-doc-409"})
        assert r1.status_code == 202

        # Immediate retry — task is pending/processing
        r2 = await client.post("/api/v1/graph/extract", json={"doc_id": "test-doc-409"})
        assert r2.status_code == 409
        assert r2.json()["code"] == 5003

    async def test_completed_task_returns_200_already_done(
        self, client, clean_tasks, settings
    ):
        """Re-request a completed task → 200 'already done'."""
        # Insert a completed task directly via PG
        conn = _pg_conn(settings)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO graph_engine.extraction_tasks (task_id, doc_id, status) "
            "VALUES (%s, %s, %s)",
            ("g-task-completed-001", "test-doc-completed", "completed"),
        )
        cur.close()
        conn.close()

        r = await client.post(
            "/api/v1/graph/extract", json={"doc_id": "test-doc-completed"}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "completed"

    async def test_missing_doc_id_returns_400(self, client):
        """POST /extract without doc_id → 400."""
        r = await client.post("/api/v1/graph/extract", json={})
        assert r.status_code == 400

    async def test_task_persisted_to_pg(self, client, clean_tasks, settings):
        """After POST /extract → task row exists in PG."""
        r = await client.post(
            "/api/v1/graph/extract", json={"doc_id": "test-doc-persist"}
        )
        assert r.status_code == 202

        conn = _pg_conn(settings)
        cur = conn.cursor()
        cur.execute(
            "SELECT task_id, doc_id, status FROM graph_engine.extraction_tasks "
            "WHERE doc_id = %s",
            ("test-doc-persist",),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        assert row is not None
        assert row[1] == "test-doc-persist"
        assert row[2] in ("pending", "processing")
