"""MilvusStore：实体/关系向量存储与检索。

Collection 设计：
- graph_entities:    entity_id 为 VARCHAR 主键，upsert 实现实体去重
- graph_relationships: auto_id 主键，允许重复（应用层去重已足够）

索引策略：使用 AUTOINDEX 自动选择最优索引类型（IVF_FLAT/HNSW 等），
插入新数据后立即可搜索，无需手动 flush/release/rebuild。
"""

from pymilvus import MilvusClient, DataType

from src.settings import Settings


class MilvusStore:
    """知识图谱实体与关系的向量存储与检索。

    实体使用 upsert（主键去重），关系使用 insert（允许重复）。
    搜索返回 COSINE 距离作为相似度分数。

    Attributes:
        _settings: 应用配置。
        _client: pymilvus MilvusClient 实例。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化 Milvus 客户端。

        Args:
            settings: 应用配置，提供 Milvus 连接参数。
        """
        self._settings = settings
        self._client = MilvusClient(
            uri=settings.milvus_uri,
            user=settings.milvus_user,
            password=settings.milvus_password,
            db_name=settings.milvus_db,
        )

    # ── 生命周期 ───────────────────────────────────────────────────

    def initialize(self) -> None:
        """确保两个 collection 存在（含 AUTOINDEX）且已加载。

        新建 collection 时自动创建 schema + AUTOINDEX（自动加载）。
        已存在的 collection 若未加载则执行 load。
        """
        self._ensure_entity_collection()
        self._ensure_relation_collection()

    def close(self) -> None:
        """关闭 Milvus 客户端连接。"""
        self._client.close()

    # ── upsert ──────────────────────────────────────────────────────

    def upsert_entities(
        self,
        entity_data: list[dict],
        vectors: list[list[float]],
    ) -> dict:
        """幂等 upsert 实体（以 entity_id 为主键）。

        Args:
            entity_data: 实体数据列表，每项含 entity_id, entity_name, entity_type,
                         entity_description。
            vectors: 1024 维浮点向量，与 entity_data 顺序一致。

        Returns:
            dict: {"upsert_count": N}
        """
        if not entity_data:
            return {"upsert_count": 0}
        data = [
            {
                "entity_id": e["entity_id"],
                "vector": v,
                "entity_name": e["entity_name"],
                "entity_type": e["entity_type"],
                "entity_description": e["entity_description"],
            }
            for e, v in zip(entity_data, vectors)
        ]
        return self._client.upsert(
            collection_name=self._settings.milvus_entity_collection,
            data=data,
        )

    def upsert_relationships(
        self,
        rel_data: list[dict],
        vectors: list[list[float]],
    ) -> dict:
        """插入关系向量（auto_id，允许重复）。

        Args:
            rel_data: 关系数据列表，每项含 src_entity_id, tgt_entity_id,
                      relation_type, keywords, description。
            vectors: 1024 维浮点向量，与 rel_data 顺序一致。

        Returns:
            dict: {"insert_count": N}
        """
        if not rel_data:
            return {"insert_count": 0}
        data = [
            {
                "vector": v,
                "src_entity_id": r["src_entity_id"],
                "tgt_entity_id": r["tgt_entity_id"],
                "relation_type": r["relation_type"],
                "keywords": r["keywords"],
                "description": r["description"],
            }
            for r, v in zip(rel_data, vectors)
        ]
        return self._client.insert(
            collection_name=self._settings.milvus_relation_collection,
            data=data,
        )

    # ── 搜索 ────────────────────────────────────────────────────────

    def search_entities(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        """向量搜索实体。

        Args:
            query_vector: 查询向量，1024 维。
            top_k: 返回 top-k 结果，默认 10。

        Returns:
            list[dict]: 每项含 entity_id, entity_name, entity_type,
                        entity_description, score 字段。
        """
        coll = self._settings.milvus_entity_collection
        hits = self._client.search(
            collection_name=coll,
            data=[query_vector],
            limit=top_k,
            output_fields=[
                "entity_id",
                "entity_name",
                "entity_type",
                "entity_description",
            ],
        )
        return [
            {
                "entity_id": h.get("entity_id", ""),
                "entity_name": h.get("entity_name", ""),
                "entity_type": h.get("entity_type", ""),
                "entity_description": h.get("entity_description", ""),
                "score": h.get("distance", 0),
            }
            for h in hits[0]
        ]

    def search_relationships(
        self, query_vector: list[float], top_k: int = 10
    ) -> list[dict]:
        """向量搜索关系。

        Args:
            query_vector: 查询向量，1024 维。
            top_k: 返回 top-k 结果，默认 10。

        Returns:
            list[dict]: 每项含 src_entity_id, tgt_entity_id, relation_type,
                        keywords, description, score 字段。
        """
        coll = self._settings.milvus_relation_collection
        hits = self._client.search(
            collection_name=coll,
            data=[query_vector],
            limit=top_k,
            output_fields=[
                "src_entity_id",
                "tgt_entity_id",
                "relation_type",
                "keywords",
                "description",
            ],
        )
        return [
            {
                "src_entity_id": h.get("src_entity_id", ""),
                "tgt_entity_id": h.get("tgt_entity_id", ""),
                "relation_type": h.get("relation_type", ""),
                "keywords": h.get("keywords", ""),
                "description": h.get("description", ""),
                "score": h.get("distance", 0),
            }
            for h in hits[0]
        ]

    # ── 内部方法 ────────────────────────────────────────────────────

    def _ensure_entity_collection(self) -> None:
        """创建实体 collection（如不存在）或确保已加载。

        Schema: entity_id (VARCHAR PK) + entity_name + entity_type +
                entity_description + vector (FLOAT_VECTOR, COSINE AUTOINDEX)。
        """
        coll = self._settings.milvus_entity_collection
        if self._client.has_collection(coll):
            self._ensure_loaded(coll)
            return
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(
            "entity_id",
            DataType.VARCHAR,
            is_primary=True,
            max_length=256,
        )
        schema.add_field("entity_name", DataType.VARCHAR, max_length=512)
        schema.add_field("entity_type", DataType.VARCHAR, max_length=128)
        schema.add_field("entity_description", DataType.VARCHAR, max_length=4096)
        schema.add_field(
            "vector",
            DataType.FLOAT_VECTOR,
            dim=self._settings.embedding_dim,
        )

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._client.create_collection(
            collection_name=coll,
            schema=schema,
            index_params=index_params,
        )
        # AUTOINDEX 自动加载 collection，立即可搜索

    def _ensure_relation_collection(self) -> None:
        """创建关系 collection（如不存在）或确保已加载。

        Schema: id (INT64 PK, auto_id) + src_entity_id + tgt_entity_id +
                relation_type + keywords + description +
                vector (FLOAT_VECTOR, COSINE AUTOINDEX)。
        使用 auto_id 主键，允许重复关系。
        """
        coll = self._settings.milvus_relation_collection
        if self._client.has_collection(coll):
            self._ensure_loaded(coll)
            return
        schema = self._client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("src_entity_id", DataType.VARCHAR, max_length=256)
        schema.add_field("tgt_entity_id", DataType.VARCHAR, max_length=256)
        schema.add_field("relation_type", DataType.VARCHAR, max_length=64)
        schema.add_field("keywords", DataType.VARCHAR, max_length=512)
        schema.add_field("description", DataType.VARCHAR, max_length=4096)
        schema.add_field(
            "vector",
            DataType.FLOAT_VECTOR,
            dim=self._settings.embedding_dim,
        )

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._client.create_collection(
            collection_name=coll,
            schema=schema,
            index_params=index_params,
        )

    def _ensure_loaded(self, coll: str) -> None:
        """检查 collection 加载状态，未加载时执行 load。

        Args:
            coll: Collection 名称。
        """
        try:
            state = self._client.get_load_state(coll, timeout=5)
            if str(state.get("state", "")) == "LoadState.NotLoad":
                self._client.load_collection(coll)
        except Exception:
            pass
