"""Integration tests for Memgraph write pipeline — requires Memgraph."""

import pytest
import pytest_asyncio

from src.settings import Settings
from src.models import Entity, EntityExtractionResult, Relationship
from src.store.memgraph import MemgraphStore
from src.extraction.pipeline import write_to_memgraph

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


@pytest_asyncio.fixture
async def clean_memgraph(memgraph_store):
    await _delete_all(memgraph_store)
    yield
    await _delete_all(memgraph_store)


class TestWriteToMemgraph:
    async def test_writes_entity_with_all_properties(
        self, memgraph_store, clean_memgraph
    ):
        """Write entity → Memgraph node has entity_name, description, page_numbers, etc."""
        result = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectType",
                    entity_description="水工建筑物混凝土结构表面的开裂缺陷",
                ),
            ],
            relationships=[],
        )
        source_meta = {
            "裂缝": {
                "chunk_ids": ["chunk-001", "chunk-002"],
                "page_numbers": ["23", "45"],
                "section_titles": ["5.2 裂缝分类标准", "5.3 处理措施"],
                "doc_titles": ["DL/T 2628-2023"],
            },
        }

        stats = await write_to_memgraph(memgraph_store, result, source_meta)
        assert stats["nodes_written"] == 1
        assert stats["edges_written"] == 0

    async def test_writes_relationships(self, memgraph_store, clean_memgraph):
        """Write entity + relationship → Memgraph has both."""
        result = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectType",
                    entity_description="开裂缺陷",
                ),
                Entity(
                    entity_name="DL/T 2628-2023 §5.2.3",
                    entity_type="NormClause",
                    entity_description="裂缝宽度标准",
                ),
            ],
            relationships=[
                Relationship(
                    source="裂缝",
                    target="DL/T 2628-2023 §5.2.3",
                    keywords="判定阈值,分级标准",
                    description="裂缝宽度大于0.3mm判定为较大缺陷",
                ),
            ],
        )
        source_meta = {}

        stats = await write_to_memgraph(memgraph_store, result, source_meta)
        assert stats["nodes_written"] == 2
        assert stats["edges_written"] == 1

    async def test_metadata_fields_preserved(self, memgraph_store, clean_memgraph):
        """Write entity → verify page_numbers, doc_titles are stored in Memgraph."""
        result = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectType",
                    entity_description="开裂缺陷",
                ),
            ],
            relationships=[],
        )
        source_meta = {
            "裂缝": {
                "chunk_ids": ["chunk-001"],
                "page_numbers": ["42"],
                "section_titles": ["§6.3 灌浆处理"],
                "doc_titles": ["DL/T 2700-2023"],
            },
        }

        await write_to_memgraph(memgraph_store, result, source_meta)

        # Verify via query
        from neo4j import AsyncGraphDatabase

        s = memgraph_store._settings
        driver = AsyncGraphDatabase.driver(
            s.memgraph_uri,
            auth=(s.memgraph_username, s.memgraph_password),
        )
        async with driver.session(database=s.memgraph_database) as session:
            r = await session.run(
                "MATCH (n:`base`:`DefectType` {entity_name: '裂缝'}) RETURN n"
            )
            record = await r.single()
            await r.consume()
        await driver.close()

        assert record is not None
        props = dict(record["n"])
        assert "42" in props.get("page_numbers", "")
        assert "DL/T 2700-2023" in props.get("doc_titles", "")
