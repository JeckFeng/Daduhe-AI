"""实体关系抽取管线：单块抽取 → 合并 → 写入图数据库。

- extractor.py: 单 chunk LLM 抽取实体与关系
- gleaning.py:  第二轮 gleaning 补充抽取遗漏实体
- pipeline.py:  多 chunk 结果合并（含 LLM map-reduce）+ Memgraph 写入
- worker.py:    异步抽取任务编排器
"""
