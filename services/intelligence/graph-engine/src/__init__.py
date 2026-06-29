"""graph-engine 服务：知识图谱实体关系抽取与查询。

提供两个核心API：
- POST /api/v1/graph/extract — 触发文档的实体关系抽取任务
- POST /api/v1/graph/query   — 向量+图混合查询（entity_search / relation_search）
"""
