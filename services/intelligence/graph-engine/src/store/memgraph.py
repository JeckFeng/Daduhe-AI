"""MemgraphStore：双标签节点 + 语义边类型的 Memgraph 图数据库存储。

封装 neo4j AsyncGraphDatabase，提供节点/边的幂等 upsert 和 BFS 子图检索。
瞬态错误重试策略参考 LightRAG 的 MemgraphStorage 实现。
"""

import asyncio
import random
from datetime import datetime, timezone

from neo4j import AsyncGraphDatabase, AsyncManagedTransaction
from neo4j.exceptions import TransientError

from src.settings import Settings


class MemgraphStore:
    """异步 Memgraph 图存储，支持双标签节点和语义关系类型。

    节点使用双标签：workspace（如 "base"）+ entity_type（如 "DefectType"）。
    边使用语义类型（如 REGULATED_BY、TREATED_BY），而非通用 DIRECTED。

    Attributes:
        _settings: 应用配置。
        _driver: neo4j AsyncDriver 实例。
        _workspace: 工作空间标签，默认 "base"。
        _database: Memgraph 数据库名称。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 Memgraph 存储。

        Args:
            settings: 应用配置，提供 Memgraph 连接参数。
        """
        self._settings = settings
        self._driver = None
        self._workspace = "base"
        self._database = settings.memgraph_database

    async def initialize(self) -> None:
        """建立 Memgraph 连接并验证连通性。"""
        self._driver = AsyncGraphDatabase.driver(
            self._settings.memgraph_uri,
            auth=(self._settings.memgraph_username, self._settings.memgraph_password),
        )
        self._database = self._settings.memgraph_database
        async with self._driver.session(database=self._database) as session:
            await session.run("RETURN 1")

    async def close(self) -> None:
        """关闭 Memgraph 连接。"""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    # ── 节点 upsert ────────────────────────────────────────────────

    async def upsert_node(
        self, entity_id: str, entity_type: str, properties: dict
    ) -> None:
        """幂等 upsert 节点，使用双标签：workspace + entity_type。

        通过 MERGE 匹配 entity_id，SET += 更新属性。自动添加 created_at 时间戳。

        Args:
            entity_id: 实体唯一标识，格式 "{entity_type}-{entity_name}"。
            entity_type: 实体类型，作为节点第二标签。
            properties: 节点属性 dict。

        Raises:
            RuntimeError: 未调用 initialize() 时抛出。
        """
        if self._driver is None:
            raise RuntimeError("MemgraphStore not initialized")

        node_props = dict(properties)
        node_props["entity_id"] = entity_id
        node_props["entity_type"] = entity_type
        if "created_at" not in node_props:
            node_props["created_at"] = datetime.now(timezone.utc).isoformat()

        # 转义反引号以防标签名包含特殊字符
        workspace_label = self._workspace.replace("`", "``")
        entity_label = entity_type.replace("`", "``")
        query = f"""
            MERGE (n:`{workspace_label}`:`{entity_label}` {{entity_id: $entity_id}})
            SET n += $properties
        """

        await self._retry_write(
            query, {"entity_id": entity_id, "properties": node_props}
        )

    # ── 边 upsert ──────────────────────────────────────────────────

    async def upsert_edge(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        properties: dict | None = None,
    ) -> None:
        """幂等 upsert 边，使用语义关系类型。

        通过 MATCH 两端节点 + MERGE 边实现。边属性通过 SET += 更新。

        Args:
            source_entity_id: 源实体 ID。
            target_entity_id: 目标实体 ID。
            relation_type: 语义关系类型，如 REGULATED_BY、TREATED_BY。
            properties: 边属性 dict，包含 keywords、description、weight 等。

        Raises:
            RuntimeError: 未调用 initialize() 时抛出。
        """
        if self._driver is None:
            raise RuntimeError("MemgraphStore not initialized")

        edge_props = dict(properties) if properties else {}
        workspace_label = self._workspace.replace("`", "``")
        rel_type = relation_type.replace("`", "``")

        query = f"""
            MATCH (source:`{workspace_label}` {{entity_id: $source_entity_id}})
            MATCH (target:`{workspace_label}` {{entity_id: $target_entity_id}})
            MERGE (source)-[r:`{rel_type}`]-(target)
            SET r += $properties
        """

        await self._retry_write(
            query,
            {
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "properties": edge_props,
            },
        )

    # ── 知识图谱检索 ───────────────────────────────────────────────

    async def get_knowledge_graph(
        self, node_label: str, max_depth: int = 3, max_nodes: int = 1000
    ) -> dict:
        """从起始实体出发的 BFS 子图检索。

        使用 Memgraph 的 BFS 语法进行广度优先遍历，返回指定深度内的子图。

        Args:
            node_label: 起始实体的 entity_id。
            max_depth: BFS 最大深度，默认 3。
            max_nodes: 最大返回节点数，默认 1000。

        Returns:
            dict: {"nodes": list[dict], "edges": list[dict], "is_truncated": bool}
            节点格式: {"id": str, "labels": list[str], "properties": dict}
            边格式: {"id": str, "type": str, "source": str, "target": str, "properties": dict}

        Raises:
            RuntimeError: 未调用 initialize() 时抛出。
        """
        if self._driver is None:
            raise RuntimeError("MemgraphStore not initialized")

        workspace_label = self._workspace.replace("`", "``")
        nodes = []
        edges = []
        seen_nodes = set()
        seen_edges = set()
        is_truncated = False

        async with self._driver.session(
            database=self._database, default_access_mode="READ"
        ) as session:
            query = f"""
                MATCH (start:`{workspace_label}`)
                WHERE start.entity_id = $entity_id

                OPTIONAL MATCH path = (start)-[*BFS 0..{max_depth}]-(end:`{workspace_label}`)
                WHERE path IS NULL OR ALL(n IN nodes(path) WHERE '{workspace_label}' IN labels(n))
                WITH start, collect(DISTINCT end) AS discovered_nodes
                WITH start, [node IN discovered_nodes WHERE node IS NOT NULL AND node <> start] AS other_nodes
                WITH
                CASE
                    WHEN 1 + size(other_nodes) <= $max_nodes THEN [start] + other_nodes
                    ELSE [start] + other_nodes[0..$max_other_nodes]
                END AS limited_nodes,
                1 + size(other_nodes) > $max_nodes AS truncated

                UNWIND limited_nodes AS n
                OPTIONAL MATCH (n)-[r]-(m)
                WHERE m IN limited_nodes
                RETURN
                    collect(DISTINCT n) AS nodes,
                    collect(DISTINCT r) AS relationships,
                    truncated
            """

            result = await session.run(
                query,
                {
                    "entity_id": node_label,
                    "max_nodes": max_nodes,
                    "max_other_nodes": max(max_nodes - 1, 0),
                },
            )
            record = await result.single()
            await result.consume()

            if not record:
                return {"nodes": [], "edges": [], "is_truncated": False}

            is_truncated = record.get("truncated", False)

            for node in record.get("nodes", []) or []:
                nid = node.element_id
                if nid not in seen_nodes:
                    nodes.append(
                        {
                            "id": str(nid),
                            "labels": list(node.labels),
                            "properties": dict(node),
                        }
                    )
                    seen_nodes.add(nid)

            for rel in record.get("relationships", []) or []:
                eid = rel.element_id
                if eid not in seen_edges:
                    edges.append(
                        {
                            "id": str(eid),
                            "type": rel.type,
                            "source": str(rel.start_node.element_id),
                            "target": str(rel.end_node.element_id),
                            "properties": dict(rel),
                        }
                    )
                    seen_edges.add(eid)

        return {"nodes": nodes, "edges": edges, "is_truncated": is_truncated}

    # ── 内部辅助方法 ───────────────────────────────────────────────

    async def _retry_write(
        self, query: str, params: dict, max_retries: int = 100
    ) -> None:
        """执行写查询，带瞬态错误指数退避重试（参考 LightRAG 模式）。

        Args:
            query: Cypher 查询语句。
            params: 查询参数。
            max_retries: 最大重试次数，默认 100。

        Raises:
            TransientError: 重试耗尽后仍失败时抛出。
        """
        initial_wait = 0.2
        backoff = 1.1
        jitter = 0.1

        for attempt in range(max_retries):
            try:
                async with self._driver.session(database=self._database) as session:

                    async def _tx(tx: AsyncManagedTransaction):
                        result = await tx.run(query, params)
                        await result.consume()

                    await session.execute_write(_tx)
                    return
            except TransientError:
                if attempt < max_retries - 1:
                    wait = initial_wait * (backoff**attempt) + random.uniform(0, jitter)
                    await asyncio.sleep(wait)
                else:
                    raise
