"""Integration tests for MemgraphStore.

Requires Memgraph accessible at GRAPH_MEMGRAPH_URI (default bolt://localhost:17687).
"""

import pytest
from neo4j import GraphDatabase

from src.settings import Settings
from src.store.memgraph import MemgraphStore

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def sync_driver(settings):
    """Sync neo4j driver for direct Cypher verification."""
    driver = GraphDatabase.driver(
        settings.memgraph_uri,
        auth=(settings.memgraph_username, settings.memgraph_password),
    )
    yield driver
    driver.close()


@pytest.fixture
async def store(settings):
    """Initialized MemgraphStore. Cleans up test data after each test."""
    s = MemgraphStore(settings)
    await s.initialize()
    yield s
    # Clean up test data
    try:
        async with s._driver.session(database=s._database) as session:
            await session.run("MATCH (n) DETACH DELETE n")
    except Exception:
        pass
    await s.close()


# ── Node Upsert Tests ────────────────────────────────────────────


async def test_upsert_node_dual_label(store, sync_driver):
    """Tracer bullet: node created with workspace + entity_type labels."""
    await store.upsert_node(
        entity_id="test-node-001",
        entity_type="DefectType",
        properties={
            "description": "混凝土裂缝",
            "source_id": ["seed-chunk-001"],
            "page_numbers": "23",
            "section_titles": "§5.2.3 裂缝处理标准",
            "doc_titles": "DL/T 2628-2023",
        },
    )

    with sync_driver.session() as session:
        result = session.run(
            "MATCH (n:DefectType {entity_id: 'test-node-001'}) RETURN n"
        )
        record = result.single()
        assert record is not None, "Node not found with dual label"
        node = record["n"]
        assert "base" in node.labels
        assert "DefectType" in node.labels
        assert node["entity_id"] == "test-node-001"
        assert node["entity_type"] == "DefectType"
        assert node["description"] == "混凝土裂缝"
        assert node["page_numbers"] == "23"
        assert node["doc_titles"] == "DL/T 2628-2023"


async def test_upsert_node_all_required_properties(store, sync_driver):
    """Node contains all 8 required property fields."""
    await store.upsert_node(
        entity_id="test-node-002",
        entity_type="NormClause",
        properties={
            "description": "DL/T 2628-2023 §5.2.3",
            "source_id": ["seed-chunk-003"],
            "page_numbers": "23",
            "section_titles": "§5.2.3",
            "doc_titles": "DL/T 2628-2023",
        },
    )

    with sync_driver.session() as session:
        result = session.run(
            "MATCH (n:NormClause {entity_id: 'test-node-002'}) RETURN n"
        )
        node = result.single()["n"]
        assert node["entity_id"] is not None
        assert node["entity_type"] is not None
        assert node["description"] is not None
        assert node["source_id"] is not None
        assert node["page_numbers"] is not None
        assert node["section_titles"] is not None
        assert node["doc_titles"] is not None
        assert node["created_at"] is not None


async def test_upsert_node_idempotent(store, sync_driver):
    """Repeated upsert of same entity_id updates, not duplicates."""
    await store.upsert_node(
        entity_id="test-node-idem",
        entity_type="DefectType",
        properties={"description": "version 1", "source_id": []},
    )
    await store.upsert_node(
        entity_id="test-node-idem",
        entity_type="DefectType",
        properties={"description": "version 2", "source_id": []},
    )

    with sync_driver.session() as session:
        result = session.run(
            "MATCH (n {entity_id: 'test-node-idem'}) RETURN count(n) AS cnt"
        )
        cnt = result.single()["cnt"]
        assert cnt == 1, f"Expected 1 node, got {cnt} (duplicate created)"

        result2 = session.run("MATCH (n {entity_id: 'test-node-idem'}) RETURN n")
        node = result2.single()["n"]
        assert node["description"] == "version 2"


# ── Edge Upsert Tests ────────────────────────────────────────────


async def test_upsert_edge_semantic_type(store, sync_driver):
    """Edge uses semantic relation type REGULATED_BY instead of DIRECTED."""
    await store.upsert_node(
        entity_id="edge-src-001",
        entity_type="DefectType",
        properties={"description": "裂缝", "source_id": []},
    )
    await store.upsert_node(
        entity_id="edge-tgt-001",
        entity_type="NormClause",
        properties={"description": "DL/T 2628-2023", "source_id": []},
    )

    await store.upsert_edge(
        source_entity_id="edge-src-001",
        target_entity_id="edge-tgt-001",
        relation_type="REGULATED_BY",
        properties={
            "keywords": "裂缝处理标准",
            "description": "裂缝宽度超过0.3mm需灌浆处理",
            "source_id": ["seed-chunk-002"],
            "page_numbers": "23",
            "section_titles": "§5.2.3",
            "weight": 1.0,
        },
    )

    with sync_driver.session() as session:
        result = session.run("MATCH ()-[r:REGULATED_BY]->() RETURN r")
        records = list(result)
        assert len(records) > 0, "No REGULATED_BY edge found"
        edge = records[0]["r"]
        assert edge["keywords"] == "裂缝处理标准"
        assert edge["description"] == "裂缝宽度超过0.3mm需灌浆处理"
        assert edge["weight"] == 1.0


async def test_upsert_edge_required_properties(store, sync_driver):
    """Edge contains all required provenance + weight properties."""
    await store.upsert_node(
        entity_id="edge-src-002",
        entity_type="DefectType",
        properties={"description": "渗漏", "source_id": []},
    )
    await store.upsert_node(
        entity_id="edge-tgt-002",
        entity_type="Treatment",
        properties={"description": "帷幕灌浆", "source_id": []},
    )

    await store.upsert_edge(
        source_entity_id="edge-src-002",
        target_entity_id="edge-tgt-002",
        relation_type="TREATED_BY",
        properties={
            "keywords": "灌浆处理",
            "description": "采用帷幕灌浆处理渗漏",
            "source_id": ["seed-chunk-005"],
            "page_numbers": "45",
            "section_titles": "§6.2.1",
            "weight": 0.9,
        },
    )

    with sync_driver.session() as session:
        result = session.run("MATCH ()-[r:TREATED_BY]->() RETURN r")
        edge = result.single()["r"]
        assert "keywords" in edge
        assert "description" in edge
        assert "source_id" in edge
        assert "page_numbers" in edge
        assert "section_titles" in edge
        assert "weight" in edge


# ── Knowledge Graph Retrieval ────────────────────────────────────


async def test_get_knowledge_graph_bfs(store, sync_driver):
    """BFS subgraph returns correct node/edge structure."""
    await store.upsert_node(
        entity_id="kg-A",
        entity_type="DefectType",
        properties={"description": "裂缝", "source_id": []},
    )
    await store.upsert_node(
        entity_id="kg-B",
        entity_type="NormClause",
        properties={"description": "DL/T 2628-2023", "source_id": []},
    )
    await store.upsert_node(
        entity_id="kg-C",
        entity_type="Treatment",
        properties={"description": "灌浆", "source_id": []},
    )

    await store.upsert_edge("kg-A", "kg-B", "REGULATED_BY", {"weight": 1.0})
    await store.upsert_edge("kg-B", "kg-C", "TREATED_BY", {"weight": 1.0})

    kg = await store.get_knowledge_graph("kg-A", max_depth=2)

    assert len(kg["nodes"]) >= 2  # at least A and B
    assert len(kg["edges"]) >= 1  # at least A->B
    for node in kg["nodes"]:
        assert "id" in node
        assert "labels" in node
        assert "properties" in node
    for edge in kg["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "type" in edge
