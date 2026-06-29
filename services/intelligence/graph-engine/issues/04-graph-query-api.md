# Issue 4: 知识图谱查询 API

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询 — Issue 2: 知识图谱查询

## What to build

实现 `POST /api/v1/graph/query` 端点，支持 4 种 query_type 的纯 Cypher 模板化查询，返回结构化 nodes + edges + 溯源信息。

1. **4 种 query_type Cypher 映射**：

| query_type | 输入 params | Cypher 逻辑 |
|------------|------------|------------|
| `related_norms` | `defect_type`（必填），`structure_type`（可选） | 匹配 `(n:DefectType)-[:REGULATED_BY]->(m:NormClause)`，可选按 structure_type 过滤 |
| `related_treatments` | `defect_type`（必填） | 匹配 `(n:DefectType)-[:TREATED_BY]->(m:Treatment)` |
| `related_cases` | `defect_type`（必填），`structure_type`（可选） | 匹配 `(n:DefectType)-[:BELONGS_TO]->(p:Project)` 或 BFS 扩展到工程节点 |
| `entity_detail` | `entity_name`（必填），`depth`（可选，默认 3） | 以 entity_name 为起点 BFS `[0..depth]` 跳子图，复用 MemgraphStorage 的 `get_knowledge_graph` |

2. **返回格式**（ICD-03 §4.2）：
   ```
   {
     "nodes": [{ "id": "n1", "type": "DefectType", "name": "裂缝",
                 "description": "...", "page_numbers": "23", "section_titles": "...",
                 "doc_titles": "DL/T 2628-2023" }, ...],
     "edges": [{ "from": "n1", "to": "n2", "relation": "REGULATED_BY",
                 "keywords": "...", "description": "...",
                 "page_numbers": "23", "section_titles": "..." }, ...],
     "query_type": "related_norms"
   }
   ```

3. **错误处理**：
   - 不支持的 query_type → 400 `{"code": 1002, "message": "invalid value for query_type: ..."}`
   - 必填 params 缺失 → 400
   - Memgraph 查询失败 → 500
   - 查询无结果 → 200 返回空 nodes/edges 数组（非错误）

4. **安全**：使用参数化 Cypher 查询，entity_name、defect_type 等用户输入通过 `$params` 传参，禁止字符串拼接

## Acceptance criteria

- [ ] `related_norms`：传入 `{"defect_type": "裂缝"}` → 返回 DefectType 节点 + 关联的 NormClause 节点 + REGULATED_BY 边
- [ ] `related_treatments`：传入 `{"defect_type": "渗漏"}` → 返回 DefectType 节点 + 关联的 Treatment 节点 + TREATED_BY 边
- [ ] `related_cases`：传入 `{"defect_type": "裂缝"}` → 返回 DefectType 节点 + 关联的 Project 节点 + BELONGS_TO 边
- [ ] `entity_detail`：传入 `{"entity_name": "裂缝", "depth": 2}` → 返回以"裂缝"为中心 2 跳 BFS 子图
- [ ] 所有查询结果中 node 含 `description`、`page_numbers`、`section_titles`、`doc_titles` 字段
- [ ] 所有查询结果中 edge 含 `keywords`、`description`、`page_numbers`、`section_titles` 字段
- [ ] 传无效 query_type → 400 错误
- [ ] 传不存在的 entity_name → 200 空 nodes/edges
- [ ] Cypher 注入测试：entity_name 含特殊字符（如 `'; DROP ...`）→ 参数化查询安全处理

## Blocked by

- Issue 1（项目脚手架与配置基础设施）
- Issue 2（Memgraph 存储层集成）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
