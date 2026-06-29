"""End-to-end extraction pipeline tests — requires LLM + Memgraph + PG."""

import pytest
import pytest_asyncio

from src.settings import Settings
from src.store.memgraph import MemgraphStore
from src.store.task_store import TaskStore
from src.extraction.worker import process_extraction_task

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
def settings():
    return Settings()


@pytest_asyncio.fixture
async def memgraph_store(settings):
    store = MemgraphStore(settings)
    await store.initialize()
    yield store
    await store.close()


async def _delete_all(store: MemgraphStore):
    from neo4j import AsyncGraphDatabase

    s = store._settings
    driver = AsyncGraphDatabase.driver(
        s.memgraph_uri,
        auth=(s.memgraph_username, s.memgraph_password),
    )
    async with driver.session(database=s.memgraph_database) as session:
        await session.run("MATCH (n:`base`) DETACH DELETE n")
    await driver.close()


class TestE2EExtraction:
    async def test_process_seed_doc_002_writes_to_memgraph(
        self, settings, memgraph_store
    ):
        """Extract seed-doc-002 (5 chunks) → Memgraph has nodes and edges."""
        await _delete_all(memgraph_store)

        doc_id = "seed-doc-002"
        task_id = "g-task-e2e-test-002"

        # Clean up pre-existing rows and create fresh task
        import psycopg2

        conn = psycopg2.connect(
            host=settings.pg_host,
            port=settings.pg_port,
            user=settings.pg_user,
            password=settings.pg_password,
            dbname=settings.pg_database,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM graph_engine.extraction_tasks WHERE task_id = %s", (task_id,)
        )
        cur.execute(
            "INSERT INTO graph_engine.extraction_tasks (task_id, doc_id, status) "
            "VALUES (%s, %s, 'processing')",
            (task_id, doc_id),
        )
        cur.close()
        conn.close()

        # Run extraction
        await process_extraction_task(task_id, doc_id, settings)

        # Verify task status
        task_store = TaskStore(settings)
        task_after = task_store.find_by_doc_id(doc_id)
        assert task_after is not None
        assert task_after["status"] == "completed", (
            f"Task failed: {task_after.get('error_message')}"
        )
        result = task_after["result"]
        assert result["entity_count"] > 0, f"No entities extracted: {result}"
        assert result["relationship_count"] >= 0

        # Verify Memgraph has nodes
        from neo4j import AsyncGraphDatabase as ADG

        s = settings
        driver = ADG.driver(
            s.memgraph_uri, auth=(s.memgraph_username, s.memgraph_password)
        )
        async with driver.session(database=s.memgraph_database) as session:
            r = await session.run("MATCH (n:`base`) RETURN count(n) AS cnt")
            rec = await r.single()
            await r.consume()
        await driver.close()

        node_count = rec["cnt"]
        assert node_count > 0, "Memgraph should have nodes after extraction"

        # Cleanup
        await _delete_all(memgraph_store)
