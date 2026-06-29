# Process Status

Last Updated: 2026-06-25

---

# Current Objective

agent-reasoning Phase A 开发完成并通过全链路集成测试。下一步进入 graph-engine 开发。

---

# Current Status

## Phase

- [ ] Planning
- [ ] Design
- [x] Implementation
- [x] Testing
- [x] Evaluation
- [ ] Refactoring
- [ ] Completed

Current Phase:

```text
agent-reasoning Phase A 完成，graph-engine 待开发
```

---

# Completed Tasks

## 2026-06-25 — agent-reasoning Phase A 全部完成

### Issue #1: 项目脚手架 + 基础设施

- FastAPI app + TraceMiddleware + health/ready/metrics 端点
- `settings.py` — pydantic-settings，前缀 `AGENT_`
- `models.py` — ChatRequest/ChatResponse/LLMCompletionRequest/LLMCompletionResponse
- 错误码遵循 ICD-03 (0=成功, 1002=参数错误, 4001=上游失败, 9001=内部错误)

### Issue #2: Tool Registry + vector_search 工具

- `tools/registry.py` — ToolRegistry 可扩展框架（register/resolve/execute/execute_parallel）
- `tools/vector_search.py` — 封装 search-engine POST /api/v1/search
- 支持 DI 注入 httpx.AsyncClient（便于测试生命周期管理）

### Issue #3: AgentState + Graph 骨架

- `graph/state.py` — AgentState TypedDict + SubQuestion pydantic model
- `graph/builder.py` — StateGraph 编译框架
- `graph/router.py` — 条件路由（chitchat → generator, 其他 → context_resolution）
- State Enrichment 模式：SubQuestion 作为贯穿对象逐节点 enrich

### Issue #4: Supervisor — 查询分析与问题拆解

- `graph/supervisor.py` — LLM 驱动的 4 类意图分类（chitchat/spec_lookup/knowledge_qa/comparison）
- `llm/prompts.py` — SUPERVISOR_SYSTEM prompt，含分类标准 + 分解原则 + JSON 输出格式
- comparison 类型强制拆解为 2+ 子问题
- LLM 失败不可降级，返回 _error

### Issue #5: Context Resolution + 多轮对话

- `graph/context_resolution.py` — LLM 驱动的指代消解节点
- `store/conversation.py` — InMemoryConversationStore（接口抽象，Phase B 可换 PostgreSQL）
- `llm/prompts.py` — CONTEXT_RESOLUTION_SYSTEM prompt，4 条消解规则
- 无指代需要时智能跳过 LLM 调用（pass-through）
- LLM 失败降级：resolved_query 回退为原始 question

### Issue #6: LLM Completion Factory

- `POST /api/v1/llm/completion` — 供 graph-engine 等外部消费者使用
- `llm/client.py` — LLMClient 封装 OpenAI-compatible API
- 支持 deepseek-chat / vllm-local，priority 控制超时（realtime 30s / batch 120s）
- 返回 latency_ms + token usage

### Issue #7: 全链路集成 + Chat 端点

- `POST /api/v1/chat` — 完整 6 节点 StateGraph 编排
- 拓扑：supervisor → [chitchat→generator | else→context_resolution→call_tools→fusion→generator→citation]
- 多轮对话记忆：请求完成后自动将 user/assistant 消息追加到 ConversationStore
- 44 项集成测试 100% 通过（9 大类场景，真实 search-engine + 真实 vLLM）

### 2026-06-25 — Chitchat Prompt 优化

- `GENERATOR_SYSTEM` 拆为专业问答模式 + 闲聊互动模式
- `generator_node` 对 chitchat 类型构建独立 user_message，不再触发"未找到"逻辑
- 能力询问类闲聊（"你能帮我做什么"）从"抱歉未找到"优化为 4 点能力介绍

### 2026-06-23 — search-engine 全部 Issues (#1-#6 + 评测)

详见下方 "search-engine 开发记录" 折叠区。

---

<details>
<summary>search-engine 开发记录 (2026-06-23 ~ 2026-06-25)</summary>

### Issue #1: 项目脚手架 + keyword 检索

- `models.py` — SearchRequest/SearchResponse/ChunkResult/RuleResult 联合类型 + discriminator
- `settings.py` — pydantic-settings，前缀 `SEARCH_`
- `backends/keyword.py` — ILIKE 精确子串匹配，按命中次数排序
- 7 个 keyword 测试通过

### Issue #2: fuzzy 检索（pg_trgm）

- `backends/fuzzy.py` — pg_trgm similarity() 模糊匹配，阈值 0.005
- pg_trgm 对 2 字中文查询几乎不可用（"裂缝"仅 2 字符），短查询走 keyword ILIKE

### Issue #3: vector 语义向量检索

- `backends/vector.py` — Ollama bge-m3 embed → Milvus COSINE search → PG 元数据补全
- Milvus COSINE metric 返回的 distance 字段实际为 cosine similarity

### Issue #4: hybrid 混合检索（RRF）

- `backends/hybrid.py` — RRF 融合框架，当前 = vector only，预留 keyword/fuzzy/rules 槽位

### Issue #5: search/index 异步索引构建

- `POST /api/v1/search/index` — HT 回调 → PG 读 chunks → Ollama embed → Milvus upsert
- 幂等实现 + IVF_FLAT 索引自动创建

### Issue #6: 外部接口模型 + rules 守卫

- `clients/lsl.py` — LSL RuleSearchParams/RuleSearchResponse（ICD-02 §4.2）
- `clients/ht.py` — HT SearchIndexRequest（ICD-03 §5.1）

### 检索效果评测 (2026-06-25)

- vector 添加 score >= 0.45 阈值过滤
- 评测结论：READY FOR PRODUCTION PILOT

</details>

---

# agent-reasoning 尚未实现的功能（按 PRD Out of Scope）

以下功能在 PRD 中明确标记为 Phase A Out of Scope，当前未实现，需后续迭代完成。

## P0 — 依赖其他服务就绪后可立即接入

### 1. 多源检索（规则库 / 知识图谱 / 参数库）

| 项目 | 说明 |
|------|------|
| 当前状态 | ToolRegistry 仅注册了 `vector_search`（chunk 检索） |
| 缺失内容 | `rule_search`（LSL 规则库）、`graph_query`（Memgraph 知识图谱）、`param_lookup`（参数库） |
| 阻塞条件 | LSL rule-extractor 服务就绪；graph-engine 完成实体关系抽取并写入 Memgraph |
| 实现方式 | 各新增一个 ToolDef + handler，通过 `registry.register()` 一行注册即可加入 call_tools 并行执行，无需改动 Graph 拓扑 |
| PRD 引用 | User Story 13: "通过 ToolRegistry 一行注册新数据源工具" |

### 2. Supervisor 自动选择检索源

| 项目 | 说明 |
|------|------|
| 当前状态 | Phase A 仅 vector_search 可用，Supervisor 固定返回 `"sources": ["vector"]`，不做检索源选择 |
| 缺失内容 | LLM 驱动的多源选择：根据 query 语义自动判断需要哪些检索源（vector/rule/graph/param），输出到 retrieved_sources 字段 |
| 阻塞条件 | 多源检索工具就绪（见上一条） |
| 影响 | 当前 query_type 为 spec_lookup 时本应同时检索 chunk + rule，但因 rule 不可用只能走 vector |
| PRD 引用 | Implementation Decisions: "LLM Supervisor 多源选择：Phase A 仅 vector_search" |

## P1 — 独立可开发但非阻塞

### 3. 流式响应（stream=True）

| 项目 | 说明 |
|------|------|
| 当前状态 | `ChatRequest.stream` 字段已预留（默认 false），Chat 端点仅支持非流式返回完整 answer |
| 缺失内容 | SSE 流式输出：Generator 节点逐步产出 token → 通过 SSE 推送给客户端；Citation 节点需适配流式场景（answer 不完整时无法提取 [N] 标记） |
| 实现难点 | LangGraph 的 ainvoke 不支持 streaming；需改为 astream_events 或 astream 模式；Citation 需等流式结束后后处理或改为增量模式 |
| PRD 引用 | Out of Scope: "Phase A 仅支持非流式，ChatRequest.stream 字段预留" |

### 4. PostgreSQL 持久化 ConversationStore

| 项目 | 说明 |
|------|------|
| 当前状态 | `InMemoryConversationStore`：数据存于 dict，服务重启后全部丢失 |
| 缺失内容 | PostgreSQL 后端实现：实现 `ConversationStore` 接口的三个方法（get_history/append_messages/get_recent），通过 `AGENT_CONVERSATION_STORE_BACKEND` 环境变量切换 |
| PRD 引用 | User Story 14: "ConversationStore 采用接口抽象，Phase B 从内存切换到 PostgreSQL 时不需改动 Agent 逻辑" |

### 5. /metrics 端点完整实现

| 项目 | 说明 |
|------|------|
| 当前状态 | `GET /metrics` 返回 `# TODO: daduh_* metrics`（PlainTextResponse placeholder） |
| 缺失内容 | Prometheus 格式指标：`daduh_chat_requests_total`、`daduh_chat_latency_seconds`（histogram）、`daduh_llm_requests_total`（按 model 分 label）、`daduh_node_latency_seconds`（按 node_name 分 label） |
| PRD 引用 | User Story 12: "结构化日志记录每个节点的输入/输出/耗时" — metrics 是日志的聚合补充 |

### 6. 按子问题差异化检索模式

| 项目 | 说明 |
|------|------|
| 当前状态 | Phase A 全局统一检索模式（用户指定或 auto → hybrid），所有子问题使用同一 retrieval_mode |
| 缺失内容 | Supervisor 为每个子问题推荐最优检索模式（如 spec lookup → keyword 优先，knowledge_qa → hybrid） |
| PRD 引用 | Implementation Decisions: "Phase A 不做按子问题的检索模式差异化" |

## P2 — 需要上游改造或数据积累

### 7. LSL rules 检索源接入

| 项目 | 说明 |
|------|------|
| 当前状态 | search-engine 的 `include_sources` 当前仅支持 `["chunks"]`，传 `"rules"` 会返回 400 |
| 缺失内容 | search-engine 接入 rule-extractor 的规则库检索 API；agent-reasoning 新增 `rule_search` 工具 |
| 阻塞条件 | LSL rule-extractor 服务完成规则抽取并通过 ICD-02 §4.2 API 暴露 |
| PRD 引用 | Out of Scope: "search-engine 当前 include_sources 仅支持 ['chunks']" |

### 8. 自动报告生成 / 图像识别 / 趋势预测

| 项目 | 说明 |
|------|------|
| 当前状态 | 未开始 |
| 缺失内容 | 独立功能模块，不在当前问答链路范围内 |
| PRD 引用 | Out of Scope: "自动报告生成、图像识别、趋势预测：后续独立功能" |

---

# In Progress

无。agent-reasoning Phase A 开发已完成。

---

# Next Actions

## P0

- **graph-engine 开发** — 实体关系抽取 → Memgraph 写入 → Cypher 推理查询
  - 依赖 agent-reasoning 的 `POST /api/v1/llm/completion` 做 LLM 调用
  - 需要 Memgraph 数据库（已部署于 10.222.124.211:7687）
  - ICD 接口定义: ICD-04（待确认）

## P1

- agent-reasoning: `/metrics` 端点 Prometheus 指标实现
- agent-reasoning: ConversationStore PostgreSQL 后端
- LSL rule-extractor 就绪后，search-engine 接入 rules 检索

## P2

- agent-reasoning: 多源检索接入（rule/graph/param）
- agent-reasoning: 流式响应
- DM8 数据库迁移（正式上线前）

---

# Open Questions

## Question 1

DM8 数据库何时就绪？search-engine 的 fuzzy 检索依赖 pg_trgm，DM8 替代方案（CONTEXT INDEX + UTL_MATCH）需要单独适配。

Current Thinking:

技术路线已验证可行，DM8 适配可延后到上线前。

---

## Question 2

vector_min_score 阈值 0.45 是否需要调整？

Current Thinking:

基于当前 15 个 chunk 的小数据集确定。数据量增大后需要重新评估，可能需要在更大规模数据集上校准。

---

## Question 3

graph-engine 的 ICD-04 接口定义是否已最终确定？agent-reasoning 的 `/llm/completion` 是否能完全满足 graph-engine 的 LLM 调用需求（超时策略、token 限制、temperature 控制等）？

Current Thinking:

Issue #6 已实现的 `/llm/completion` 支持 model/messages/temperature/max_tokens/priority 全参数化，应能满足 graph-engine 需求。具体接口对齐在 graph-engine PRD 阶段确认。

---

# Recent Decisions

## 2026-06-25

### Decision

Chitchat 路径 Generator prompt 拆为双模式（专业问答 + 闲聊互动）

### Reason

原 GENERATOR_SYSTEM 统一使用"未检索到相关知识请诚实告知"逻辑，对 chitchat 场景（能力询问、问候等）生成生硬的"抱歉未找到"回复。拆分后 chitchat 路径构建独立 user_message，引导 LLM 进行友好闲聊。

### Alternatives Rejected

- 在 prompt 中增加复杂条件分支 — 增加 prompt 复杂度，不如代码层分支清晰
- 新建独立的 chitchat_generator_node — 代码逻辑 90% 相同，仅 user_message 构建不同

---

## 2026-06-25

### Decision

agent-reasoning 全链路集成测试使用真实 LLM + 真实 search-engine，不使用 mock

### Reason

TDD skill 要求测试验证外部可观测行为，不耦合实现细节。真实 LLM 的随机性通过断言关键词集合（而非精确匹配）来吸收。

---

## 2026-06-25

### Decision

vector 检索加 score >= 0.45 最小阈值

### Reason

无意义查询（"XYZZY"）返回了 score 0.34-0.40 的结果，无法区分真匹配和勉强凑数。阈值 0.45 能有效过滤噪声，同时不影响真实查询。

---

## 2026-06-23

### Decision

元数据装配在 backend 内部完成（不在 handler 层）

### Reason

遵循 GRASP Information Expert 原则。keyword/fuzzy 一次 SQL JOIN 即可完成，vector 在 Milvus 返回后批量查 PG。handler 只做 dispatch，不接触 PG schema。

---

## 2026-06-23

### Decision

hybrid 当前 = vector only，预留 keyword/fuzzy/rules 槽位

### Reason

先交付可用的混合检索，后期加入更多信源时不需要改接口签名——只需往 source_lists 里追加 rank 列表。

---

# Context For Next Session

Current Location:

```text
services/intelligence/search-engine/    (已完成)
services/intelligence/agent-reasoning/  (Phase A 完成)
services/intelligence/graph-engine/     (待开发)
```

Next Step:

```text
graph-engine: 实体关系抽取 → Memgraph 写入 → Cypher 推理查询
依赖 agent-reasoning POST /api/v1/llm/completion 做 LLM 调用
```

Important Notes:

- 不要修改 search-engine 的 API 契约（ICD-03 §5.2 已锁定）
- agent-reasoning 的 /chat 和 /llm/completion 接口已稳定，44 项集成测试通过
- 跨服务调用必须透传 X-Trace-Id header
- agent-reasoning 的 ToolRegistry 框架已为多源检索预留扩展点
- graph-engine 开发可使用 uv venv（Python 3.11），工作区根目录 services/intelligence/
