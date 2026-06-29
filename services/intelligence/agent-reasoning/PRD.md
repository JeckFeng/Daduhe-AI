# PRD: agent-reasoning 智能问答 Agent

## Problem Statement

agent-reasoning（fxl-agent-reasoning, port 8003）是 Daduhe-AI 面向用户的智能问答服务。用户通过自然语言提问水工建筑物缺陷相关问题，系统需要自动分析问题意图、拆解复合问题、从多个检索源获取知识、组装 LLM 生成带溯源的答案。

当前服务仅有返回 `[TODO]` 的 stub 端点。Phase A 需要搭建完整的 LangGraph RAG 编排流水线，走通"用户提问 → 意图分析 → 问题分解 → 指代消解 → 多源检索 → 知识融合 → LLM 生成 → 引文组装"全链路，并为后续接入规则库、参数库、知识图谱等多源检索做好框架扩展准备。

## Solution

在 search-engine（多模式检索）和 daduhe_common（链路追踪/日志/健康检查）之上，基于 LangGraph StateGraph 实现 Supervisor+Worker+Fusion 编排架构：

- **Supervisor**：LLM 驱动的查询分析器，判断问题类型（规范查询/知识问答/对比分析/闲聊），将复合问题拆解为独立子问题
- **Context Resolution**：LLM 驱动的指代消解节点，结合多轮对话历史对每个子问题做上下文补全
- **call_tools**：并行调用 search-engine 对每个子问题执行检索，结果挂在对应 SubQuestion 上
- **Fusion**：跨子问题结果去重（按 chunk_id）、按 score 降序排序、取 TOP-K 输出扁平上下文
- **Generator**：LLM 驱动，基于融合上下文生成带 `[N]` 引用标记的自然语言答案
- **Citation**：抽取答案中的 `[N]` 标记，映射到 chunk 元数据，组装可核查的引文数组

同时保留 `POST /api/v1/llm/completion` 作为兼容透传端点，内部转发到 llm-gateway（port 8004）。

## User Stories

### 核心问答

1. 作为最终用户，我想要用自然语言提问水工建筑物缺陷问题，并获得带引用来源的专业答案，以便追溯信息源头
2. 作为最终用户，我想要问"混凝土坝裂缝宽度超过多少需要处理"这样的单一问题时，系统自动检索规范条文并给出带规范引用的精确答案
3. 作为最终用户，我想要问"坝体裂缝的成因有哪些？对应的处理措施是什么？"这样的复合问题时，系统自动分解为多个子问题分别检索再综合回答
4. 作为最终用户，我想要问"DL/T 2628 和 SL 230 对裂缝分类有什么不同"这样的对比问题时，系统分别检索两本规范并对比分析
5. 作为最终用户，我想要在问答中看到答案里用 `[1]` `[2]` 标记引用，并能点击 citation 下载原文，以便核查答案准确性

### 多轮对话

6. 作为最终用户，我想要在提问"之前问的那条规范里对贯穿性裂缝怎么规定的"时，系统能理解我指的是之前对话中讨论过的规范，而无需我重复规范名称
7. 作为最终用户，我想要和系统进行多轮交互逐步深入探讨一个技术问题，系统能记住对话上下文

### 闲聊处理

8. 作为最终用户，当我说"你好"或"你是谁"时，系统应友好回应而不做无意义的检索

### LLM 调用工厂

9. 作为 graph-engine 服务，我想要通过 llm-gateway 的 `POST /api/v1/completion` 统一调用 LLM，自动享受 PG 缓存（相同 prompt + 相同后端命中缓存，14x+ 加速）
10. 作为运维人员，我想要通过 priority 参数（`realtime` / `batch`）控制 LLM 调用的超时策略，以便平衡延迟和吞吐

### 可观测性与配置

11. 作为运维人员，我想要通过环境变量（前缀 `AGENT_`）配置 LLM 参数、超时、TOP-K 等所有可调参数，以便不同环境灵活部署
12. 作为运维人员，我想要每次请求有 trace_id 贯穿所有节点，结构化日志记录每个节点的输入/输出/耗时，以便排查问题

### 框架扩展性

13. 作为开发者，我想要通过 ToolRegistry 一行注册新数据源工具，以便后续接入规则库、参数库、知识图谱时无需改动图拓扑
14. 作为开发者，我想要 ConversationStore 采用接口抽象，Phase B 从内存切换到 PostgreSQL 时不需改动 Agent 逻辑

## Implementation Decisions

### 架构：LangGraph StateGraph + Tool Registry + State Enrichment

采用 LangGraph StateGraph 编排多节点流水线，而非单体 Agent。核心设计模式：

- **State Enrichment**：SubQuestion 作为贯穿对象，各节点逐步补充字段（Supervisor 创建 → Context Resolution 补充 resolved_query → call_tools 补充 results），不创建平行中间对象，便于 trace 和调试
- **先分解后消解**：Supervisor 先拆分子问题，Context Resolution 再对每个子问题分别做指代消解
- **全局统一检索模式**：Phase A 不做按子问题的检索模式差异化，用户指定或 `auto` → `hybrid`
- **LLM 统一走 llm-gateway**：所有 LLM 调用通过 llm-gateway（port 8004）的 `POST /api/v1/completion`，享受 PG 缓存（cache key = `md5(system+user+model+host)`，TTL 7 天）。Graph 节点直接调用 `LLMClient.completion()`（内部 HTTP 客户端调用 llm-gateway），`/api/v1/llm/completion` 保留为兼容透传端点

### Graph 拓扑

```
supervisor ──┬── query_type=chitchat ────→ generator → END
             │
             └── query_type≠chitchat ──→ context_resolution → call_tools → fusion → generator ──┬── chitchat → END
                                                                                                   │
                                                                                                   └── 非chitchat → citation → END
```

6 个节点（supervisor / context_resolution / call_tools / fusion / generator / citation），2 处条件路由（Supervisor → Generator 的 chitchat 快捷路径，Generator → END 的 chitchat 跳过 citation 路径）。

### 节点职责

- **supervisor**：LLM 分析 query + 近期对话历史 → 输出 `query_type`（chitchat | spec_lookup | knowledge_qa | comparison）和 `sub_questions` 列表。使用历史做语义判断（判断 query_type 和分解维度），不做指代消解。LLM 参数：temperature=0.0, max_tokens=500, priority=realtime。失败不可降级，整个请求返回错误。
- **context_resolution**：LLM 消费 ConvesationStore.get_recent(turns=5) + 每个 sub_question → 补充 resolved_query 和 resolved_context 实体。使用历史做指代消解（如"之前那本规范"→"DL/T 2628-2023"）。LLM 参数：temperature=0.0, max_tokens=500, priority=realtime。失败降级：resolved_query 回退为原始 question，记录 warn。
- **call_tools**：对每个 sub_question，用 resolved_query 作为检索输入，通过 ToolRegistry 并行调用 search-engine。ToolRegistry 按 source_type 匹配工具（Phase A 仅 vector_search），结果挂在对应 sub_question.results。部分子问题检索失败不中断流水线，有结果就继续。ToolRegistry.execute 内部捕获异常，失败返回 error 字段。
- **fusion**：收集所有 sub_question.results 去重（按 chunk_id，保留高分）、按 score 降序排序、取 TOP-K（默认 10，通过 Settings 配置）、输出扁平 `fused_context` 字符串（`[1] chunk_text\n[2] chunk_text...`）。
- **generator**：LLM 消费 fused_context + sub_questions，生成带 `[N]` 引用标记的自然语言答案。所有 query_type 统一一个 system prompt，靠上下文让 LLM 自适应。检索结果为空时生成"未找到"风格回复。LLM 参数：temperature=0.1, max_tokens=2000, priority=realtime。失败返回错误但附带已有 citations。
- **citation**：正则提取 answer 中的 `[N]` 标记，从 Fusion 结果列表中按序号取出 chunk metadata，组装 citations 数组。excerpt 取 chunk 原文前 150 字。download_url 用 search_engine_url 的 base 拼接完整 URL。

### 数据模型

AgentState 核心字段：

```
query: str                 # 原始用户输入
conversation_id: str       # 会话ID
trace_id: str              # 链路追踪ID
retrieval_mode: str        # 检索模式（auto=自动判断）
query_type: str            # Supervisor 输出的问题类型
sub_questions: list[SubQuestion]  # 贯穿对象，逐节点 enrich
fused_context: str         # Fusion 输出的扁平TOP-K上下文
answer: str                # Generator 输出，带[N]标记
citations: list[Citation]  # Citation 输出
messages: Annotated[list[BaseMessage], add_messages]  # LangGraph 消息累积
```

SubQuestion（贯穿对象，State Enrichment 模式）：

```
id: str                         # "q1", "q2"
question: str                   # 原始子问题文本
topic: str                      # 问题主题描述
requires_history: bool          # 是否需要历史指代消解
history_reference: str | None   # 对历史的引用描述
resolved_query: str | None      # Context Resolution 补充
resolved_context: dict | None   # Context Resolution 补充
results: list[dict]             # call_tools 补充
```

Message：

```
role: str        # "user" | "assistant" | "system"
content: str
timestamp: float # time.time()
```

### ConversationStore 接口抽象

内存实现，三个接口：

- `get_history(conversation_id) → list[Message]` — 获取完整历史
- `append_messages(conversation_id, messages) → None` — 追加消息
- `get_recent(conversation_id, turns=5) → list[Message]` — 获取最近 N 轮

存储完整会话，上下文窗口由消费者决定。Phase B 迁移到 PostgreSQL 只需替换实现。

### LLM 调用策略

所有 LLM 调用通过 llm-gateway（port 8004）统一入口，享受 PG 缓存（TTL 7 天）。LLM 后端选择（vllm-local / deepseek-chat）和 API 密钥由 llm-gateway 管理，agent-reasoning 仅指定 model 名。

| 节点 | temperature | max_tokens | priority | 失败策略 |
|------|-------------|------------|----------|----------|
| supervisor | 0.0 | 500 | realtime | 不可降级，返回错误 |
| context_resolution | 0.0 | 500 | realtime | 降级为原始 question |
| generator | 0.1 | 2000 | realtime | 返回错误，附带已有 citations |

所有参数通过 Settings（环境变量前缀 `AGENT_`）全局可配置。llm-gateway 连接配置：
- `AGENT_LLM_GATEWAY_URL`：llm-gateway 地址，默认 `http://localhost:8004`

### 错误码体系

遵循 ICD 约定：段号 × 1000 + 序号。

- 0 = 成功
- 1xxx = 参数错误（ChatRequest 校验失败）
- 4xxx = 上游服务调用失败（search-engine 不可达）
- 9xxx = 内部错误（LLM 调用失败、Graph 执行异常等）

### 元数据装配

agent-reasoning 不做元数据装配。search-engine 已返回完整 metadata，只需在 citation 节点中映射为 ICD-03 §6.1 定义的 citation 结构，并对 download_url 使用 search_engine_url 的 base 拼接完整 URL。

## Testing Decisions

### 测试策略

参照 `search-engine/tests/test_search.py` 风格，使用集成测试：

- FastAPI `TestClient` 通过 HTTP 端点测试
- 检索部分调真实 search-engine（同进程 TestClient）
- LLM 调用部分使用 mock（避免消耗 API 配额）
- 验证端到端答案质量（answer 非空、citations 结构完整、trace_id 贯穿）

### 测试模块

- **ConversationStore 单元测试**：内存实现的 CRUD 和窗口截断行为
- **ToolRegistry 单元测试**：注册/解析/执行/并行执行的正确性（已有 smoke test）
- **Graph 节点单元测试**：每个节点的纯逻辑（mock LLM、mock search-engine）
- **Chat 端点集成测试**：完整流水线（真实 search-engine + mock LLM）
- **LLM Completion 端点集成测试**：LLM 工厂的模型路由和超时

### TDD 流程

单个测试 → 单个实现，不批量写测试再批量写实现。每个节点先写测试验证外部行为，再实现内部逻辑。

## Out of Scope

- **多源检索**（规则库、参数库、知识图谱）：Phase B+，ToolRegistry 框架已预留扩展点
- **LLM Supervisor 多源选择**：Phase A 仅 vector_search，Phase B 升级为自主选择检索源
- **任务规划**：当前不做 DAG 任务规划，不做子问题间检索结果依赖
- **自动报告生成、图像识别、趋势预测**：后续独立功能，不在 Phase A 范围
- **PostgreSQL 持久化 ConversationStore**：Phase A 使用内存实现
- **流式响应**（`stream=True`）：Phase A 仅支持非流式，ChatRequest.stream 字段预留
- **按子问题差异化检索模式**：Phase A 全局统一检索模式
- **LSL rules 检索源**：search-engine 当前 `include_sources` 仅支持 `["chunks"]`

## Further Notes

- Supervisor 和 Context Resolution 都访问对话历史，但职责不同：Supervisor 用历史做语义判断（query_type、分解维度），Context Resolution 用历史做指代消解（"那本规范"→具体规范名）
- 完整设计讨论记录在项目记忆中
- 领域术语定义在 `CONTEXT.md`
