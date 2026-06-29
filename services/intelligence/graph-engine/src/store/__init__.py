"""存储层：Memgraph、Milvus、PostgreSQL 数据访问。

- memgraph.py:   MemgraphStore — 双标签节点 + 语义边类型的 Memgraph 存储
- milvus.py:     MilvusStore — 实体/关系向量存储与检索
- chunk_reader.py: PgChunkReader — 从 PG 读取文档 chunks
- task_store.py: TaskStore — 抽取任务状态管理
"""
