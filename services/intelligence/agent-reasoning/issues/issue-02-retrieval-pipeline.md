# Issue 2: Retrieval Pipeline — call_tools + fusion + citation

## Type

AFK

## Blocked by

- Issue #1 (Foundation) — 依赖 AgentState、SubQuestion、Settings、ConversationStore

## What to build

实现三条不需要 LLM 的 graph 节点，串联验证"检索 → 融合 → 引文"链路完整性。

**1. call_tools 节点**（`src/graph/call_tools.py` 重写）

- 对每个 sub_question，使用 `resolved_query or question` 作为检索文本
- 通过 ToolRegistry 调用 search-engine（Phase A 仅 vector_search 工具）
- 并行执行所有子问题的检索（`asyncio.gather`）
- 结果写入对应 `sub_question.results`
- 部分失败不中断：ToolRegistry 内部已捕获异常返回 error 字段，call_tools 记录 warn 后继续
- 检索参数：mode 使用 state.retrieval_mode（auto → hybrid），top_k 使用 Settings 默认值

**2. fusion 节点**（`src/graph/fusion.py` 重写）

- 收集所有 sub_question.results 中的 chunk 结果
- 去重：按 chunk_id，保留 score 高的
- 排序：按 score 降序
- 截断：取 TOP-K（Settings.fusion_top_k，默认 10）
- 输出扁平 `fused_context` 字符串：
  ```
  [1] chunk_text_1
  [2] chunk_text_2
  ...
  ```
- 保存排序后的结果列表到 state 供 citation 节点使用（fusion 需要额外输出一个有序结果列表）

**3. citation 节点**（`src/graph/citation.py` 重写）

- 正则提取 answer 中所有 `[N]` 标记
- 从 Fusion 排序后的结果列表中按序号 N-1 取 chunk
- 组装 citations 数组，每条包含：
  - `index`: N（数字）
  - `chunk_id`, `doc_title`, `doc_type`, `section`, `page`: 从 chunk.metadata 映射
  - `download_url`: 用 search_engine_url 的 base 拼接（`f"{base}/api/v1/documents/{doc_id}/download"`）
  - `excerpt`: chunk.text 前 150 字
- 如果 answer 中无 `[N]` 标记（chitchat 场景），输出空 citations 数组

**4. 临时简单图**（供本 issue 测试用）

构建临时图 `supervisor(rule-based stub) → call_tools → fusion → generator(stub) → citation`，验证检索→融合→引文链路。Stub supervisor 输出固定 plan，stub generator 返回固定带 `[N]` 的 answer。本图仅供 issue 内部测试，不替换最终拓扑。

## Acceptance criteria

- [ ] call_tools 并行检索：2 个子问题各自返回结果，分别挂在对应 sub_question.results
- [ ] call_tools 部分失败：一个子问题失败，另一个成功，流水线继续，日志中有 warn 记录
- [ ] fusion 去重：同一 chunk 出现在两个子问题结果中时，保留高分的一条
- [ ] fusion 排序截断：15 条结果按 score 降序排列，仅取 TOP-10（默认值）
- [ ] fusion 输出 fused_context 含 `[N]` 前缀标记
- [ ] citation 正确映射 `[1]` `[2]` 到对应 chunk metadata
- [ ] citation 的 download_url 为完整 URL
- [ ] citation 的 excerpt 取自 chunk 原文
- [ ] 集成测试：真实 search-engine + stub supervisor/generator，验证端到端链路
