"""图查询服务：向量搜索 + Memgraph 图扩展。

两种查询模式：
- entity_search:   向量搜索实体 → Memgraph 批量获取节点 + 图扩展边
- relation_search: 向量搜索关系 → Memgraph 获取端点实体 + 格式化边

参考 LightRAG 的 _get_node_data / _get_edge_data 模式实现。
"""

import httpx

from src.settings import Settings
from src.store.memgraph import MemgraphStore
from src.store.milvus import MilvusStore


class GraphQueryService:
    """执行 Milvus 向量搜索 + Memgraph 图扩展的混合查询。

    将向量搜索的 top-k 结果作为种子，通过 Memgraph 进行图扩展，
    返回实体节点和相关边。

    Attributes:
        _store: Memgraph 图存储。
        _milvus: Milvus 向量存储。
        _settings: 应用配置。
    """

    def __init__(self, store: MemgraphStore, milvus: MilvusStore, settings: Settings) -> None:
        """初始化查询服务。

        Args:
            store: Memgraph 图存储实例。
            milvus: Milvus 向量存储实例。
            settings: 应用配置。
        """
        self._store = store
        self._milvus = milvus
        self._settings = settings

    async def query(self, query_type: str, params: dict) -> dict:
        """根据 query_type 分发到对应的查询方法。

        Args:
            query_type: "entity_search" 或 "relation_search"。
            params: 查询参数，必须包含 query 文本，可选 top_k。

        Returns:
            dict: 包含 entities、edges、query_type 字段的结果。

        Raises:
            ValueError: query_type 不支持时抛出。
        """
        if query_type == "entity_search":
            return await self._entity_search(params)
        if query_type == "relation_search":
            return await self._relation_search(params)
        raise ValueError(f"Unsupported query_type: {query_type}")

    # ── entity_search ──────────────────────────────────────────────

    async def _entity_search(self, params: dict) -> dict:
        """实体搜索：向量搜索实体 → 图扩展（LightRAG _get_node_data 模式）。

        流程：
        1. Embed 查询文本
        2. Milvus 向量搜索实体
        3. Memgraph 批量获取实体节点
        4. Memgraph 查询实体间的边

        Args:
            params: 查询参数，query 必填，top_k 可选。

        Returns:
            dict: {"entities": list[dict], "edges": list[dict], "query_type": "entity_search"}

        Raises:
            ValueError: query 为空时抛出。
        """
        query_text = params.get("query", "")
        top_k = params.get("top_k", self._settings.graph_search_top_k)

        if not query_text:
            raise ValueError("query is required for entity_search")

        # 1. Embed 查询文本
        query_vector = await _embed(query_text, self._settings)

        # 2. Milvus 向量搜索实体
        entity_hits = self._milvus.search_entities(query_vector, top_k)
        hit_ids = [h["entity_id"] for h in entity_hits]
        if not hit_ids:
            return {"entities": [], "edges": [], "query_type": "entity_search"}

        # 3. Memgraph 批量获取实体节点
        entity_nodes = await self._batch_get_nodes(hit_ids)

        # 4. 图扩展：查找命中实体之间的边
        edges = await self._get_edges_between(hit_ids)

        return {
            "entities": entity_nodes,
            "edges": edges,
            "query_type": "entity_search",
        }

    # ── relation_search ────────────────────────────────────────────

    async def _relation_search(self, params: dict) -> dict:
        """关系搜索：向量搜索关系 → 获取端点实体（LightRAG _get_edge_data 模式）。

        流程：
        1. Embed 查询文本
        2. Milvus 向量搜索关系
        3. 收集端点 entity_id 集合
        4. Memgraph 批量获取端点实体
        5. 格式化关系边

        Args:
            params: 查询参数，query 必填，top_k 可选。

        Returns:
            dict: {"entities": list[dict], "edges": list[dict], "query_type": "relation_search"}

        Raises:
            ValueError: query 为空时抛出。
        """
        query_text = params.get("query", "")
        top_k = params.get("top_k", self._settings.graph_search_top_k)

        if not query_text:
            raise ValueError("query is required for relation_search")

        # 1. Embed 查询文本
        query_vector = await _embed(query_text, self._settings)

        # 2. Milvus 向量搜索关系
        edge_hits = self._milvus.search_relationships(query_vector, top_k)
        if not edge_hits:
            return {"entities": [], "edges": [], "query_type": "relation_search"}

        # 3. 收集所有端点 entity_id
        endpoint_ids: set[str] = set()
        for h in edge_hits:
            if h["src_entity_id"]:
                endpoint_ids.add(h["src_entity_id"])
            if h["tgt_entity_id"]:
                endpoint_ids.add(h["tgt_entity_id"])

        # 4. Memgraph 批量获取端点实体
        entity_nodes = await self._batch_get_nodes(list(endpoint_ids))

        # 5. 格式化边（带 score）
        edges = [
            {
                "from": h["src_entity_id"],
                "to": h["tgt_entity_id"],
                "relation": h["relation_type"],
                "keywords": h["keywords"],
                "description": h["description"],
                "score": h["score"],
            }
            for h in edge_hits
        ]

        return {
            "entities": entity_nodes,
            "edges": edges,
            "query_type": "relation_search",
        }

    # ── Memgraph 辅助方法 ──────────────────────────────────────────

    async def _batch_get_nodes(self, entity_ids: list[str]) -> list[dict]:
        """批量按 entity_id 从 Memgraph 获取实体节点。

        Args:
            entity_ids: entity_id 列表。

        Returns:
            list[dict]: 节点列表，每项含 id, type, name, description。
        """
        if not entity_ids or self._store._driver is None:
            return []

        query = """
            MATCH (n:`base`)
            WHERE n.entity_id IN $ids
            RETURN n
        """
        records = await self._run_read(query, {"ids": entity_ids})
        return self._format_nodes(records, "n")

    async def _get_edges_between(self, entity_ids: list[str]) -> list[dict]:
        """查找给定实体节点之间的所有边。

        使用 UNION 双向查询确保无向边不被遗漏。
        按 edge element_id 去重。

        Args:
            entity_ids: entity_id 列表（至少 2 个）。

        Returns:
            list[dict]: 边列表，每项含 from, to, relation, keywords, description。
        """
        if len(entity_ids) < 2 or self._store._driver is None:
            return []

        query = """
            MATCH (src:`base`)-[r]->(tgt:`base`)
            WHERE src.entity_id IN $ids AND tgt.entity_id IN $ids
            RETURN src, r, tgt
        UNION
            MATCH (src:`base`)-[r]->(tgt:`base`)
            WHERE src.entity_id IN $ids AND tgt.entity_id IN $ids
            RETURN tgt, r, src
        """
        records = await self._run_read(query, {"ids": entity_ids})

        edges: list[dict] = []
        seen: set[str] = set()
        for record in records:
            rel = record.get("r")
            if rel is None:
                continue
            eid = rel.element_id
            if eid in seen:
                continue
            seen.add(eid)
            eprops = dict(rel)
            edges.append(
                {
                    "from": str(rel.start_node.element_id),
                    "to": str(rel.end_node.element_id),
                    "relation": rel.type,
                    "keywords": eprops.get("keywords", ""),
                    "description": eprops.get("description", ""),
                }
            )
        return edges

    async def _run_read(self, query: str, params: dict) -> list:
        """执行只读 Cypher 查询。

        每次调用创建独立的 neo4j driver 和 session（避免跨请求 driver 生命周期问题）。

        Args:
            query: Cypher 查询语句。
            params: 查询参数字典。

        Returns:
            list: neo4j Record 列表。
        """
        from neo4j import AsyncGraphDatabase

        s = self._settings
        driver = AsyncGraphDatabase.driver(
            s.memgraph_uri,
            auth=(s.memgraph_username, s.memgraph_password),
        )
        async with driver.session(
            database=s.memgraph_database, default_access_mode="READ"
        ) as session:
            result = await session.run(query, params)
            records = [r async for r in result]
        await driver.close()
        return records

    def _format_nodes(self, records: list, key: str) -> list[dict]:
        """将 neo4j Record 格式化为标准节点 dict。

        去重 + 提取核心字段（id, type, name, description）。
        entity_type 取 base 以外的第一个标签。

        Args:
            records: neo4j Record 列表。
            key: 记录中节点字段的键名。

        Returns:
            list[dict]: 格式化后的节点列表。
        """
        nodes: list[dict] = []
        seen: set[str] = set()
        for record in records:
            node = record.get(key)
            if node is None:
                continue
            nid = node.element_id
            if nid in seen:
                continue
            seen.add(nid)
            props = dict(node)
            labels = list(node.labels)
            entity_type = next((label for label in labels if label != "base"), "Other")
            nodes.append(
                {
                    "id": str(nid),
                    "type": entity_type,
                    "name": props.get("entity_name", props.get("name", "")),
                    "description": props.get(
                        "entity_description", props.get("description", "")
                    ),
                }
            )
        return nodes


# ── embedding 辅助函数 ───────────────────────────────────────────────


async def _embed(text: str, settings: Settings) -> list[float]:
    """调用 Ollama API 生成文本的 embedding 向量。

    Args:
        text: 待向量化的文本。
        settings: 应用配置。

    Returns:
        list[float]: 1024 维浮点向量。
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": settings.embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
