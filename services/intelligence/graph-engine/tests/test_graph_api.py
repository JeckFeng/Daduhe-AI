"""Integration tests for POST /api/v1/graph/query endpoint."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.settings import Settings
from src.store.memgraph import MemgraphStore

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
def settings():
    return Settings()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def memgraph_store(settings):
    store = MemgraphStore(settings)
    await store.initialize()
    yield store
    await store.close()


async def _delete_all(store: MemgraphStore):
    from neo4j import AsyncGraphDatabase

    settings = store._settings
    driver = AsyncGraphDatabase.driver(
        settings.memgraph_uri,
        auth=(settings.memgraph_username, settings.memgraph_password),
    )
    async with driver.session(database=settings.memgraph_database) as session:
        await session.run("MATCH (n:`base`) DETACH DELETE n")
    await driver.close()


@pytest_asyncio.fixture
async def seed_defect_norms(memgraph_store):
    await memgraph_store.upsert_node(
        entity_id="api-裂缝",
        entity_type="DefectType",
        properties={"entity_name": "裂缝", "description": "开裂缺陷"},
    )
    await memgraph_store.upsert_node(
        entity_id="api-norm-dlt2628",
        entity_type="NormClause",
        properties={
            "entity_name": "DL/T 2628-2023 §5.2.3",
            "description": "裂缝宽度标准",
            "page_numbers": "23",
            "section_titles": "5.2 裂缝分类",
            "doc_titles": "DL/T 2628-2023",
        },
    )
    await memgraph_store.upsert_edge(
        source_entity_id="api-裂缝",
        target_entity_id="api-norm-dlt2628",
        relation_type="REGULATED_BY",
        properties={"keywords": "标准", "description": "判定标准"},
    )
    yield
    await _delete_all(memgraph_store)


# ── Validation ──────────────────────────────────────────────────────


class TestQueryAPIValidation:
    async def test_invalid_query_type_returns_400(self, client):
        """Invalid query_type → 400 with meaningful error."""
        r = await client.post(
            "/api/v1/graph/query", json={"query_type": "invalid_type", "params": {}}
        )
        assert r.status_code == 400
        data = r.json()
        assert data["code"] != 0

    async def test_missing_query_type_returns_400(self, client):
        """Missing query_type → 400."""
        r = await client.post("/api/v1/graph/query", json={"params": {}})
        assert r.status_code == 400

    async def test_missing_required_param_returns_400(self, client):
        """Missing query param for entity_search → 400."""
        r = await client.post(
            "/api/v1/graph/query", json={"query_type": "entity_search", "params": {}}
        )
        assert r.status_code == 400


# ── entity_search API ───────────────────────────────────────────────


class TestQueryAPIEntitySearch:
    async def test_empty_result_for_unknown_query(self, client, seed_defect_norms):
        """Query that doesn't match any entity → 200 with empty arrays."""
        r = await client.post(
            "/api/v1/graph/query",
            json={
                "query_type": "entity_search",
                "params": {"query": "XYZ不存在的实体"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["entities"] == []
        assert data["data"]["edges"] == []

    async def test_returns_entities(self, client, seed_defect_norms):
        """entity_search for '裂缝' returns entities + edges."""
        r = await client.post(
            "/api/v1/graph/query",
            json={"query_type": "entity_search", "params": {"query": "裂缝"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["query_type"] == "entity_search"


# ── Security ────────────────────────────────────────────────────────


class TestQueryAPISecurity:
    async def test_cypher_injection_safe(self, client, seed_defect_norms):
        """Cypher injection attempt via query text is safely handled."""
        malicious = "'; MATCH (n) DETACH DELETE n; //"
        r = await client.post(
            "/api/v1/graph/query",
            json={"query_type": "entity_search", "params": {"query": malicious}},
        )
        # Should return 200 with empty results, NOT crash or delete data
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0

        # Verify existing data is still intact
        r2 = await client.post(
            "/api/v1/graph/query",
            json={"query_type": "entity_search", "params": {"query": "裂缝"}},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2["data"]["entities"]) >= 1
