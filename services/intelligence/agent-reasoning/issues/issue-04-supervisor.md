# Issue 4: Supervisor — 查询分析与问题分解

## Type

AFK

## Blocked by

- Issue #1 (Foundation) — 依赖 AgentState、SubQuestion、ConversationStore
- Issue #3 (Generator) — 需要 Generator 就绪以测试 chitchat 路由

## What to build

实现 Supervisor 节点，LLM 驱动的查询分析器：判断问题类型、拆解复合问题，以及 chitchat 的快捷路由。

**1. Supervisor 节点**（`src/graph/supervisor.py` 重写）

- 调用 LLMClient（本地 vLLM），参数 temperature=0.0, max_tokens=500, priority=realtime
- 读取 ConversationStore.get_recent(turns=5) 获取近期对话历史（用于语义判断，不做指代消解）
- 输入：原始 query + 近期对话历史
- 输出：JSON 包含 `query_type` 和 `sub_questions` 列表

**2. query_type 四分类**

- `chitchat`: 问候/自我介绍等非专业问题。sub_questions 为一个特殊条目：`{id: "q1", question: 原始query, topic: "chitchat"}`
- `spec_lookup`: 指向具体规范条文的查询
- `knowledge_qa`: 需要多源知识组装的问题
- `comparison`: 对比/比较类问题，每个对比对象拆一个子问题

**3. 问题分解输出格式**

```json
{
  "query_type": "knowledge_qa",
  "sub_questions": [
    {
      "id": "q1",
      "question": "子问题原文",
      "topic": "问题主题",
      "requires_history": false,
      "history_reference": null
    }
  ]
}
```

简单问题可不分解（1 个子问题）。复合问题按语义维度拆 2-3 个。

**4. Supervisor system prompt**（`src/llm/prompts.py` 新增）

明确四分类的判断标准、分解原则、输出 JSON 格式约束。告知 LLM "使用历史做语义判断，不做指代消解"。

**5. 条件路由**（`src/graph/router.py` 重写）

- `query_type == "chitchat"` → 路由到 `generator`
- 非 chitchat → 路由到 `context_resolution`（Issue #5 实现，本 issue 先用 stub）
- chitchat 路径：`supervisor → generator → END`（跳过 citation，因为无检索结果）

**6. 失败策略**

Supervisor LLM 调用失败 → 整个请求返回错误（不可降级，因为没有 query_type 和 sub_questions 流水线无法继续）。

## Acceptance criteria

- [ ] Supervisor 正确分类 chitchat（"你好"→chitchat, "什么是裂缝"→knowledge_qa）
- [ ] Supervisor 正确分类 spec_lookup（"DL/T 2628 裂缝怎么规定的"→spec_lookup）
- [ ] Supervisor 正确分类 comparison（"A 和 B 有什么区别"→comparison）
- [ ] 复合问题拆解为 2+ 个子问题，每个包含 id/question/topic
- [ ] 简单问题不拆解（1 个子问题）
- [ ] chitchat 路由到 generator，跳过 context_resolution 和 citation
- [ ] Supervisor 消费近期对话历史做语义判断（不依赖上下文的情况下也能正确分类）
- [ ] Supervisor LLM 调用失败返回错误，不可降级
- [ ] 集成测试：真实 LLM 驱动 Supervisor，验证 query_type 正确性和分解合理性
