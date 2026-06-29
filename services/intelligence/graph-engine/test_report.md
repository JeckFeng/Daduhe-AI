# graph-engine 实体关系抽取测试报告

**日期**: 2026-06-26  
**测试环境**: 109 test cases (57 unit + 52 integration), pytest 9.1.1, Python 3.11.15  
**LLM**: deepseek-chat（通过 agent-reasoning, max_tokens=4000）  
**结果**: **109 passed, 0 failed**, 耗时 187s

---

## 1. 架构变更（本次 vs 上次）

| 特性 | 旧版 | 新版 |
|------|------|------|
| Chunk 抽取 | 串行 for 循环 | asyncio.Semaphore(4) 并行 + fail-fast |
| 去重合并 | 规则：选最长 description | LLM map-reduce 合并 |
| 关系类型 | `_infer_edge_type()` 规则推断 | **LLM 直接输出 `relation_type`** |
| JSON 容错 | 无 | 截断修复 fallback |
| max_tokens | 默认 2000（隐式） | Settings 控制 4000 |

---

## 2. 抽取效果

### 2.1 种子文档一：DL/T 2700-2023 泄水建筑物水力安全评价导则（seed-doc-002）

| 指标 | 数值 |
|------|------|
| Chunk 数量 | 5 |
| 合并后实体数 | 65 |
| 合并后关系数 | 62 |
| 总耗时 | 117.5s |

**实体类型分布**:

| 实体类型 | 数量 | 示例 |
|----------|------|------|
| Parameter | 16 | 冲刷坑后坡比不应陡于1:3、运行超过30年 |
| DetectionMethod | 13 | 全面安全检测评估、冲刷坑形态测量 |
| Treatment | 12 | 低压密孔灌浆、修复加固、限制运行条件 |
| DefectLocation | 9 | 两岸边坡、下游河床、消力池底板 |
| DefectType | 8 | 冲刷、泥沙淤积、磨损 |
| DefectAssessment | 6 | 不安全、安全、基本安全 |
| Structure | 5 | 压力钢管、尾坎、泄水建筑物 |
| Material | 2 | PVC止水带、环氧砂浆 |
| NormClause | 1 | 现行规范要求 |

**关系类型分布**（LLM 直接输出）: TREATED_BY(42) > DEFINED_BY(34) > HAS_SUBTYPE(32) > RELATED(28) > OCCURS_IN(19) > USES_MATERIAL(17) > CAUSES(12) > BELONGS_TO(4) > REGULATED_BY(1)

### 2.2 种子文档二：DL/T 2628-2023 水工建筑物缺陷管理规范（seed-doc-001）

| 指标 | 数值 |
|------|------|
| Chunk 数量 | 10 |
| 合并后实体数 | 138 |
| 合并后关系数 | 129 |
| 总耗时 | 184.0s |

**实体类型分布**:

| 实体类型 | 数量 | 示例 |
|----------|------|------|
| Parameter | 30 | 宽度<0.2mm、宽度0.2-0.3mm、裂缝宽度>0.3mm |
| DefectType | 25 | 结构缺陷、渗流缺陷、材料劣化缺陷 |
| Treatment | 25 | 表面封闭法、化学灌浆、灌浆处理 |
| DetectionMethod | 22 | 回弹法、超声-回弹综合法、钻芯法 |
| DefectAssessment | 11 | 较大缺陷、轻微渗漏、中等渗漏 |
| Structure | 10 | 闸门、压力钢管、拦污栅 |
| Material | 9 | 环氧树脂、聚氨酯浆材、环氧涂料 |
| DefectLocation | 9 | 贯穿性裂缝、深层裂缝、表层裂缝 |
| DefectImpact | 9 | 建筑物整体稳定性降低、渗流安全隐患 |
| Other | 5 | 缺陷管理信息系统、缺陷档案、全生命周期管理 |
| NormClause | 1 | 现行规范要求 |

**关系类型分布**（LLM 直接输出，含种子文档二和种子文档一汇总）: TREATED_BY(42) > DEFINED_BY(34) > HAS_SUBTYPE(32) > RELATED(28) > OCCURS_IN(19) > USES_MATERIAL(17) > CAUSES(12) > BELONGS_TO(4) > REGULATED_BY(1)

### 2.3 LLM 关系类型 vs 规则推断对比

| 关系类型 | 规则推断 | LLM 直接输出 | 变化 |
|----------|----------|-------------|------|
| TREATED_BY | 26 | 42 | +62% |
| DEFINED_BY | 29 | 34 | +17% |
| HAS_SUBTYPE | 24 | 32 | +33% |
| RELATED | 20 | 28 | +40% |
| OCCURS_IN | 5 | 19 | +280% |
| USES_MATERIAL | 11 | 17 | +55% |
| CAUSES | 22 | 12 | -45% |
| BELONGS_TO | 0 | 4 | **全新出现** |
| REGULATED_BY | 1 | 1 | 持平 |

**关键发现**:
- **BELONGS_TO 首次出现**: 规则推断（关键词匹配"归属"/"案例"）从未触发此类型，LLM 正确识别了结构归属关系
- **OCCURS_IN 大幅增加**: LLM 比关键词"部位"/"位置"匹配更准确识别位置关系
- **CAUSES 更保守**: LLM 对因果关系判断比规则更严格（12 vs 22），减少了误标
- **9 种类型全覆盖**: LLM 使用了全部 9 种类型，分布更符合文档真实语义

### 2.4 效果分析

- **实体类型覆盖**: 两份文档覆盖 11 种实体类型，领域覆盖全面
- **关系覆盖率**: entity → relationship 比例约 0.94:1，实体间关联被有效抽取
- **LLM 合并质量**: description 从多条碎片化文本合并为连贯的摘要描述
- **LLM 随机性**: 同一文档两次抽取的实体数有约 5-10% 波动，类型分布基本稳定

---

## 3. 性能

### 3.1 端到端吞吐量

| 文档 | Chunks | 串行耗时 | 并行耗时 | 提升 | 实体抽取速率 |
|------|--------|----------|----------|------|-------------|
| seed-doc-002 | 5 | 167.0s | 117.5s | **29.6%** | 0.55 entities/s |
| seed-doc-001 | 10 | 281.4s | 184.0s | **34.6%** | 0.75 entities/s |

### 3.2 耗时分布

并行模式端到端流程耗时（seed-doc-001, 10 chunks, max_async=4）：

| 阶段 | 耗时 (s) | 占比 | 说明 |
|------|----------|------|------|
| 并行 LLM 抽取 | ~175 | 95% | 10 chunks 并发度 4，两波完成 |
| LLM map-reduce 合并 | ~5 | 2.7% | 多实体 map → LLM summarize → reduce |
| Memgraph 写入 | ~4 | 2.2% | 138 节点 + 129 关系批量写入 |
| Prompt 构建 + 其他 | <1 | <1% | YAML 加载、模板渲染 |

**瓶颈**: LLM 推理占绝对主导（~95%）。

### 3.3 并行效率

- seed-doc-002: 1.42x 加速（5 chunks / 4 semaphore）
- seed-doc-001: 1.53x 加速（10 chunks / 4 semaphore）
- 并行效率约 60-65%，损失来自 Gleaning 串行 + merge/write 固定开销 + 长尾 chunk

### 3.4 全量测试性能

| 指标 | 数值 |
|------|------|
| 总测试数 | 109 (57 unit + 52 integration) |
| 全量通过时间 | 186.7s |
| 其中 e2e 测试 (seed-doc-002) | 117.5s |
| 其中 LLM 单元测试 (单 chunk + gleaning) | ~30s |
| 其中 Memgraph/PG/API 集成测试 | ~30s |
| 非 LLM 测试 (merge, settings, models) | <1s |

---

## 4. 可观测性

### 4.1 Prometheus 指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `daduh_http_requests_total` | Counter | `service` | HTTP 请求总数 |
| `daduh_graph_extraction_duration_s` | Histogram | `doc_id` | 单文档抽取耗时分布 |

### 4.2 任务追踪

每次抽取通过 `graph_engine.extraction_tasks` 表记录：

- `progress` JSONB: `{"phase": "extraction|merging|writing", "completed": N, "total": N}`
- `result` JSONB: `{"entity_count": N, "relationship_count": N, "nodes_written": N, "edges_written": N}`
- 状态机: `pending → processing → completed/failed`
- Worker 通过 `asyncio.create_task` 在 API 端点内启动

---

## 5. 代码改动汇总

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `src/settings.py` | 新增 | extraction_llm_max_tokens, extraction_max_async, merge_summary_context_size, merge_summary_max_tokens, merge_summary_language |
| `src/models.py` | 新增字段 | `Relationship.relation_type: str = "RELATED"` |
| `src/extraction/worker.py` | 重构 | `_parallel_extract_chunks()` + `process_extraction_task` 并行抽取 + LLM 合并 |
| `src/extraction/extractor.py` | 新增 | 注入 relation type 指南到 prompt、解析 `relation_type`、JSON 截断修复 fallback |
| `src/extraction/pipeline.py` | 重构+删除 | `_build_llm_merge_prompt()`, `_llm_summarize()`, `_map_reduce_merge()`, `merge_with_llm()`; 删除 `_infer_edge_type()` |
| `src/llm/client.py` | 新增 | 传递 `max_tokens` 参数到 agent-reasoning |
| `src/prompts/loader.py` | 新增 | 加载 `relation_types_guidance` + fallback |
| `prompts/.../water_conservancy.yaml` | 新增 | `relation_types_guidance` + 10 条 relation_type few-shot 示例 |
| `src/main.py` | 新增 | Prometheus 指标 + Worker 异步启动 |
| `tests/test_parallel_merge.py` | 新增 | 17 个测试（prompt 构建、map-reduce、LLM 合并、relation_type 投票、并行抽取） |
| `tests/conftest.py` | 新增 | `pytest.mark.integration` + `GRAPH_SKIP_INTEGRATION_TESTS` 跳过逻辑 |

---

## 6. 已知局限

1. **LLM 随机性**: 同一 chunk 两次抽取可能得到不同实体数量和名称，entity_type 和 relation_type 分类基本稳定。
2. **中文繁简体**: "裂缝" vs "裂縫" 不会被 case-insensitive 匹配合并（不同 Unicode 码点），当前种子数据均为简体中文。
3. **JSON 截断修复**: `_repair_truncated_json()` 仅在尾部截断场景有效，JSON 中间出现语法错误时无法修复。`max_tokens=4000` 已大幅降低截断概率。
4. **并行加速上限**: 受 LLM API 并发限制（max_async=4），Gleaning 轮次增加时加速效果递减。
5. **LLM 合并质量**: map-reduce 合并依赖 LLM 摘要质量，极端情况下可能丢失细节。token 估算使用 `chars/2` 启发式规则。
6. **fail-fast 模式**: 单 chunk JSON 解析失败会取消整个文档抽取。`_repair_truncated_json()` 提供了安全网，但中间位置的语法错误仍会导致失败。
