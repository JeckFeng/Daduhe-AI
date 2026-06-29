# Issue 3c: Gleaning + 合并去重 + Memgraph 写入

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询 — Issue 3: 实体关系抽取

## What to build

实现多 chunk 抽取结果的 Gleaning 增强、三层合并去重、以及最终写入 Memgraph。

1. **Gleaning 增强抽取**：在第一轮抽取后，将第一轮的 user/assistant 对作为 `history_messages` 传入第二轮"继续抽取"（prompt 模板复用 LightRAG 的 `entity_continue_extraction_json_user_prompt`）。合并两轮结果时，同名实体取描述更长的版本，新实体追加。Gleaning 轮数由 `GRAPH_ENTITY_EXTRACT_MAX_GLEANING` 控制（默认 1）。Gleaning 前检查输入 token 数是否超出上限（`MAX_EXTRACT_INPUT_TOKENS`，默认 20480），超出则跳过 gleaning 并记录 WARN 日志

2. **三层合并去重**（复用 LightRAG 逻辑）：
   - 第一层：同名实体 → MERGE（利用 `entity_name` 作为 MERGE 键）
   - 第二层：同一实体的多条 description → 字符串精确匹配去重
   - 第三层：当 description 数量超过阈值 → 调 LLM 摘要压缩为一个综合描述

3. **Memgraph 写入**：
   - 实体 → 调用 MemgraphStorage.upsert_node，节点带双 label（workspace label + entity_type label）。属性需包含 entity_id、entity_type、description、source_id、page_numbers、section_titles、doc_titles、created_at
   - 关系 → 调用 MemgraphStorage.upsert_edge，边类型使用语义化的 relation_type（如 `REGULATED_BY`，非 `DIRECTED`）。属性需包含 keywords、description、source_id、page_numbers、section_titles、weight
   - 溯源字段（page_numbers、section_titles、doc_titles）从 chunk 元数据中提取，去重后拼接写入
   - `source_id` 截断：`max_source_ids_per_entity` 上限（默认 10），超出按 KEEP 策略裁剪

4. 进度追踪：处理过程中更新 PG 任务表的 `progress` JSONB 字段（如 `{"phase": "gleaning", "extracted": 3, "total": 15}`）

## Acceptance criteria

- [ ] 给定 3 个 chunk 的抽取结果（2 个含同名实体），合并后同名实体只有 1 个节点，description 为合并后的版本
- [ ] 同描述的实体在去重后被移除
- [ ] Gleaning 开启（default 1 轮）：第二轮 LLM 调用后能补充第一轮漏掉的实体
- [ ] Gleaning 设为 0：跳过 gleaning，只跑一轮抽取
- [ ] 写入 Memgraph 后：`MATCH (n:DefectType) RETURN n` 能查到对应类型节点
- [ ] 写入 Memgraph 后：`MATCH ()-[r:REGULATED_BY]->() RETURN r` 能查到对应类型关系
- [ ] 节点属性含 page_numbers、section_titles、doc_titles 非空值
- [ ] 关系属性含 keywords、weight 非默认值
- [ ] source_id 数量不超过 max_source_ids_per_entity 上限

## Blocked by

- Issue 2（Memgraph 存储层集成）
- Issue 3b（Prompt Profile 与单 Chunk 抽取）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
