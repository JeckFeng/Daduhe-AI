"""Integration tests for graph query service — entity_search + relation_search."""

import pytest
import pytest_asyncio

from src.settings import Settings
from src.store.memgraph import MemgraphStore
from src.store.milvus import MilvusStore
from src.query.service import GraphQueryService

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


@pytest_asyncio.fixture
def milvus_store(settings):
    return MilvusStore(settings)


@pytest_asyncio.fixture
async def query_service(memgraph_store, milvus_store, settings):
    return GraphQueryService(memgraph_store, milvus_store, settings)


@pytest_asyncio.fixture
async def seed_defect_norms(memgraph_store):
    """Seed: DefectType '裂缝' REGULATED_BY NormClause 'DL/T 2628-2023 §5.2.3'."""
    await memgraph_store.upsert_node(
        entity_id="defect-裂缝",
        entity_type="DefectType",
        properties={
            "entity_name": "裂缝",
            "description": "水工建筑物混凝土结构表面的开裂缺陷",
        },
    )
    await memgraph_store.upsert_node(
        entity_id="norm-dlt2628-5.2.3",
        entity_type="NormClause",
        properties={
            "entity_name": "DL/T 2628-2023 §5.2.3",
            "description": "裂缝宽度大于0.3mm判定为较大缺陷",
            "page_numbers": "23",
            "section_titles": "5.2 裂缝分类标准",
            "doc_titles": "DL/T 2628-2023",
        },
    )
    await memgraph_store.upsert_edge(
        source_entity_id="defect-裂缝",
        target_entity_id="norm-dlt2628-5.2.3",
        relation_type="REGULATED_BY",
        properties={
            "keywords": "判定阈值,分级标准",
            "description": "裂缝宽度大于0.3mm判定为较大缺陷",
            "page_numbers": "23",
            "section_titles": "5.2 裂缝分类标准",
        },
    )
    yield
    await _delete_all(memgraph_store)


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


class TestEntitySearch:
    async def test_accepts_valid_params(self, query_service, seed_defect_norms):
        """entity_search should accept query param."""
        result = await query_service.query("entity_search", {"query": "裂缝"})
        assert "entities" in result
        assert "edges" in result
        assert result["query_type"] == "entity_search"

    async def test_missing_query_raises(self, query_service, seed_defect_norms):
        """entity_search without query raises ValueError."""
        with pytest.raises(ValueError):
            await query_service.query("entity_search", {})


class TestRelationSearch:
    async def test_accepts_valid_params(self, query_service, seed_defect_norms):
        """relation_search should accept query param."""
        result = await query_service.query("relation_search", {"query": "裂缝 灌浆"})
        assert "entities" in result
        assert "edges" in result
        assert result["query_type"] == "relation_search"

    async def test_missing_query_raises(self, query_service, seed_defect_norms):
        """relation_search without query raises ValueError."""
        with pytest.raises(ValueError):
            await query_service.query("relation_search", {})


class TestUnsupportedType:
    async def test_raises_for_unsupported_type(self, query_service):
        """Unsupported query_type raises ValueError."""
        with pytest.raises(ValueError):
            await query_service.query("related_norms", {"defect_type": "裂缝"})
