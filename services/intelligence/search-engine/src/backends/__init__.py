"""搜索引擎后端模块。

- keyword.py: search_keyword() — PG ILIKE 关键词匹配
- fuzzy.py:   search_fuzzy()   — pg_trgm 模糊匹配
- vector.py:  search_vector()  — Ollama embedding + Milvus COSINE 向量检索
- hybrid.py:  search_hybrid()  — RRF 多路融合检索
"""
