# Issue 2: Memgraph 存储层集成

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询

## What to build

从 LightRAG 导入 `MemgraphStorage`，封装为 graph-engine 可用的 Memgraph 存储层。核心改造：将 LightRAG 默认的单 label + `DIRECTED` 边模式改为**双 label + 语义化 edge type**模式。

具体改造点：
1. **节点 — 双 label**：在 `upsert_node` 中，除 workspace label 外，将 `entity_type` 作为第二个 label 写入 Cypher（如 `MERGE (n:\`base\`:\`DefectType\` {entity_id: $entity_id})`）
2. **关系 — 语义化 edge type**：将 edge_data 中的 `relation_type` 作为 edge type（如 `REGULATED_BY`、`TREATED_BY`），替代默认的 `DIRECTED`
3. **溯源属性扩展**：节点写入时，自动补全 `page_numbers`、`section_titles`、`doc_titles` 属性（从 chunk 数据中提取）
4. 封装初始化逻辑：从 `GRAPH_MEMGRAPH_URI` 等配置读取连接信息，调用 `MemgraphStorage.initialize()`
5. 对外暴露 `get_knowledge_graph`（BFS 子图）、`search_labels`（标签搜索）等方法
6. 在 `/ready` 端点中集成 Memgraph 连接检测

不改动 LightRAG 源代码，通过包装/继承方式扩展 `MemgraphStorage`。

## Acceptance criteria

- [ ] `uv sync` 后能成功 `from lightrag.kg.memgraph_impl import MemgraphStorage`
- [ ] 创建带双 label 的节点：`MATCH (n:DefectType) RETURN n` 能查到
- [ ] 创建语义化 edge type 的关系：`MATCH ()-[r:REGULATED_BY]->() RETURN r` 能查到
- [ ] 节点属性包含 `entity_id`、`entity_type`、`description`、`source_id`、`page_numbers`、`section_titles`、`doc_titles`、`created_at`
- [ ] 关系属性包含 `keywords`、`description`、`source_id`、`page_numbers`、`section_titles`、`weight`
- [ ] 对同一 `entity_id` 重复 upsert 为更新而非重复创建
- [ ] 集成测试：写入 2 个节点 + 1 条边 → 通过 Cypher 查询验证结构正确

## Blocked by

- Issue 1（项目脚手架与配置基础设施）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
