# Issue 5: Context Resolution + Multi-Turn — 指代消解与多轮对话

## Type

AFK

## Blocked by

- Issue #4 (Supervisor) — 依赖 Supervisor 产出的 sub_questions，以及 ConversationStore 中的历史数据

## What to build

实现 Context Resolution 节点，对每个子问题做指代消解，补全上下文缺失。同时将 ConversationStore 完整接入 Supervisor 和 Context Resolution，实现多轮对话链路。

**1. Context Resolution 节点**（`src/graph/context_resolution.py` 新建）

- 调用 LLMClient（本地 vLLM），参数 temperature=0.0, max_tokens=500, priority=realtime
- 输入：每个 sub_question + ConversationStore.get_recent(turns=5)
- 输出：对每个 sub_question 补充 `resolved_query` 和 `resolved_context`
- 职责：指代消解（"之前那本规范"→"DL/T 2628-2023"，"那个分类标准"→"裂缝宽度分类标准"），不做语义判断

**2. 输出格式**

对每个 sub_question 补充：
```json
{
  "resolved_query": "DL/T 2628-2023 对贯穿性裂缝如何规定",
  "resolved_context": {
    "current_specification": {
      "code": "DL/T 2628-2023",
      "name": "水电站水工建筑物缺陷管理规范",
      "source": "conversation_history",
      "confidence": 0.98
    },
    "current_topic": {
      "entity": "贯穿性裂缝",
      "source": "current_query"
    }
  }
}
```

`resolved_query` 是消解后的完整查询文本（供 call_tools 检索使用），`resolved_context` 是结构化的消解实体（供 Generator 和其他节点复用）。

**3. 降级策略**

Context Resolution LLM 调用失败 → resolved_query 回退为原始 sub_question.question，resolved_context 设为 None，记录 warn 日志。流水线继续。

**4. 多轮对话接入**

- Supervisor 通过 ConversationStore.get_recent(turns=5) 获取历史做语义判断
- Context Resolution 通过 ConversationStore.get_recent(turns=5) 获取历史做指代消解
- main.py 的 chat endpoint 在请求完成后调用 ConversationStore.append_messages() 存储本轮对话

**5. Context Resolution 的 system prompt**（`src/llm/prompts.py` 新增）

要求 LLM 识别子问题中的指代词（代词、模糊引用），从对话历史中找到具体所指，输出 JSON。

## Acceptance criteria

- [ ] "之前问的那条规范里对贯穿性裂缝怎么规定的" → resolved_query 替换为具体规范名
- [ ] 无需消解的子问题 → resolved_query 等于原始 question
- [ ] Context Resolution 失败时降级为原始 question，warn 日志记录
- [ ] ConversationStore 正确追加对话：请求前后 get_history 和 get_recent 数据正确
- [ ] Context Resolution 消费 get_recent(turns=5) 获取对话历史
- [ ] 多轮对话测试：第一轮问"DL/T 2628 里裂缝怎么分类"，第二轮问"之前那个规范里对贯穿性裂缝怎么规定的"，第二轮能正确消解
- [ ] 集成测试：真实 LLM + ConversationStore，验证历史存储和读取、指代消解正确性
