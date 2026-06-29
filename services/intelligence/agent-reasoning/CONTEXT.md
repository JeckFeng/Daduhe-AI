# agent-reasoning — 领域术语表

## 查询分析

- **Query Type（问题类型）**：Supervisor 对用户问题的分类，决定后续路由。
  - `chitchat` — 问候/闲聊，跳过检索和 citation，直接生成
  - `spec_lookup` — 规范条文查询，指向具体规范
  - `knowledge_qa` — 需要多源知识组装
  - `comparison` — 对比/比较类问题
- **Sub-Question（子问题）**：Supervisor 将复合问题拆解为多个独立语义单元。每个子问题有独立 id、topic、resolved_query、results，作为贯穿流水线的核心对象。
- **Retrieval Mode（检索模式）**：全局统一，Phase A 用户指定或 `auto` → `hybrid`。不做按子问题的差异化。

## 上下文消解

- **Context Resolution（上下文消解）**：独立的 graph node，对每个 sub_question 做指代消解。消费 ConversationStore.get_recent() 获取历史对话。失败时降级：resolved_query 回退为原始 question。
- **Supervisor 使用历史做语义判断**（判断 query_type、分解维度），**Context Resolution 使用历史做指代消解**。两者都看历史，但解决的问题不同。

## State 设计

- **State Enrichment 模式**：SubQuestion 对象随 graph 节点执行逐步补充字段（先分解后消解），而非每个节点创建新的平行对象。便于 trace 和调试。
- **先分解后消解**：Supervisor → Context Resolution 对每个 sub_question 分别消解 → call_tools 用消解后的 resolved_query 检索。

## 检索与融合

- **并行检索**：无依赖的子问题并行调用 search-engine。部分失败不中断，有结果就继续（方案 A）。
- **Fusion**：按 chunk_id 去重（保留高分），按 score 降序排序，取 TOP-K（默认 10），输出扁平列表。
- **检索结果为空**：Generator 照常生成"未找到"风格回复，不返回错误码。

## 生成与引用

- **引用标记**：LLM 在生成时自动插入 `[N]` 标记，N 对应 Fusion 扁平列表序号。
- **Citation excerpt**：取自 chunk 原文（前 150 字），确保可核查，而非取自 LLM 答案。
- **统一 Prompt**：所有 query_type 共用同一个 Generator prompt，靠检索结果和 sub_questions 让 LLM 自适应。

## 多轮对话

- **ConversationStore**：内存实现，三个接口 — `get_history()`、`append_messages()`、`get_recent(turns=N)`。存储完整会话，上下文窗口由消费者决定（Supervisor 读最近 5 轮，Generator 不直读历史）。
- **存储与窗口解耦**：后续迁移到 PG 只需替换 ConversationStore 实现，Agent 逻辑不变。

## LLM 调用

- **内部直连**：Graph 节点直接调 `LLMClient.completion()`（同进程）。`/api/v1/llm/completion` 只对 graph-engine 等外部消费者暴露。
- **全局可配置**：temperature、max_tokens、priority 等参数通过 `Settings`（环境变量前缀 `AGENT_`）配置。
