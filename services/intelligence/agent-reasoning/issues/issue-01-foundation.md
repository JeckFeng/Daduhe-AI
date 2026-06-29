# Issue 1: Foundation — 数据模型 + Settings + ConversationStore

## Type

AFK

## Blocked by

None — can start immediately.

## What to build

搭建 agent-reasoning Phase A 的数据层基础。三个模块：

**1. AgentState 与 SubQuestion Pydantic 模型**（`src/graph/state.py` 重写）

AgentState 核心字段（TypedDict）：

```
query: str                 # 原始用户输入
conversation_id: str       # 会话ID
trace_id: str              # 链路追踪ID
retrieval_mode: str        # 检索模式（auto/手动指定）
query_type: str            # Supervisor 输出的问题类型
sub_questions: list[SubQuestion]  # 贯穿对象，逐节点 enrich
fused_context: str         # Fusion 输出
answer: str                # Generator 输出，带[N]标记
citations: list[Citation]  # Citation 输出
messages: Annotated[list[BaseMessage], add_messages]
```

SubQuestion（BaseModel，State Enrichment 贯穿对象）：

```
id: str                         # "q1", "q2"
question: str                   # 原始子问题文本
topic: str                      # 问题主题描述
requires_history: bool = False  # 是否需要历史指代消解
history_reference: str | None   # 对历史的引用描述
resolved_query: str | None      # Context Resolution 补充
resolved_context: dict | None   # Context Resolution 补充
results: list[dict]             # call_tools 补充
```

Message（BaseModel）：

```
role: str        # "user" | "assistant" | "system"
content: str
timestamp: float
```

**2. Settings 扩展**（`src/settings.py` 更新）

新增可配置项（环境变量前缀 `AGENT_`）：
- LLM 参数：`supervisor_temperature` (0.0), `supervisor_max_tokens` (500), `context_resolution_temperature` (0.0), `context_resolution_max_tokens` (500), `generator_temperature` (0.1), `generator_max_tokens` (2000)
- Fusion: `fusion_top_k` (10)
- 超时：`realtime_timeout` (30), `batch_timeout` (120)
- 保留现有配置：`search_engine_url`, `deepseek_api_key`, `deepseek_api_url`, `vllm_url`, `default_model`

**3. ConversationStore 内存实现**（`src/store/conversation.py` 新建）

三个接口的 InMemoryConversationStore：

- `get_history(conversation_id) → list[Message]` — 返回完整历史
- `append_messages(conversation_id, messages: list[Message]) → None` — 追加消息
- `get_recent(conversation_id, turns: int = 5) → list[Message]` — 返回最近 N 轮（按 timestamp 排序截断）

服务实例化时创建单例，放在模块级供 graph 节点引用。后续迁移到 PG 只需替换实现类。

## Acceptance criteria

- [ ] AgentState TypedDict 定义正确，字段类型与 PRD 一致
- [ ] SubQuestion BaseModel 可通过 `.model_validate()` 从 dict 构造，可选字段有合理默认值
- [ ] Message BaseModel 包含 role、content、timestamp 三字段
- [ ] Settings 新增 LLM 参数和融合参数，环境变量 `AGENT_*` 可覆盖默认值
- [ ] InMemoryConversationStore CRUD 单元测试：get_history 空 → append → get_history 有数据 → get_recent 截断正确
- [ ] 现有 9 个 smoke test 不受影响
