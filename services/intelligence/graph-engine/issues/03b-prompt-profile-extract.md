# Issue 3b: Prompt Profile 与单 Chunk 抽取

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询 — Issue 3: 实体关系抽取

## What to build

实现水工领域 YAML prompt profile 加载 + 单个 chunk 的实体关系抽取。

1. **YAML Prompt Profile**：创建 `graph-engine/prompts/entity_type/water_conservancy.yaml`，定义：
   - `entity_types_guidance`：12 类实体类型的详细描述和分类指引（Project, Region, Structure, DefectLocation, DefectType, DefectImpact, DefectAssessment, Treatment, Material, DetectionMethod, NormClause, Parameter）
   - `entity_extraction_json_examples`：基于种子数据 15 个 chunk 的实际内容，撰写 2-3 个真实 few-shot 示例

2. **Prompt 加载模块**：兼容 LightRAG 的 `resolve_entity_extraction_prompt_profile` 机制，从 YAML 文件加载 profile，支持通过 `GRAPH_PROMPT_PROFILE_PATH` 环境变量指定路径。若文件不存在，回退到代码内置的默认 water_conservancy profile

3. **单 Chunk 抽取函数**：输入一段 chunk 文本（约 200 token），使用 JSON 模式（`response_format={"type": "json_object"}`）调 LLM，返回 `EntityExtractionResult`（entities + relationships）。抽取函数的输入和输出需与后续的 Gleaning + 合并去重流程对接

4. JSON 解析失败时给出明确错误信息（含原始 LLM 返回片段），方便调试 prompt

## Acceptance criteria

- [ ] `water_conservancy.yaml` 包含完整的 12 类 entity_types_guidance
- [ ] `water_conservancy.yaml` 包含至少 2 个基于种子数据撰写的 few-shot 示例
- [ ] 加载 YAML profile：`entity_types_guidance` 非空字符串，`entity_extraction_json_examples` 非空列表
- [ ] 用种子数据 chunk（如 seed-chunk-002 裂缝处理标准）调抽取：
  - 返回 `EntityExtractionResult`，含 entities 列表和 relationships 列表
  - entities 中每个元素有 `entity_name`、`entity_type`、`entity_description`
  - relationships 中每个元素有 `source_entity`、`target_entity`、`relationship_keywords`、`relationship_description`
  - entity_type 属于 12 类之一或 "Other"
- [ ] entity_name 遵循 title case 规范，避免简称（如仅返回"裂缝"而非"3号坝段上游面横向裂缝"算不足）
- [ ] JSON 解析失败时有明确错误信息
- [ ] 同一 chunk 两次抽取 → 第二次走缓存（验证 Issue 3a 缓存集成）

## Blocked by

- Issue 3a（LLM Client 与缓存）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
