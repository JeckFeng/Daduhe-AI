# Issue 3: Generator — LLM 答案生成

## Type

AFK

## Blocked by

- Issue #2 (Retrieval Pipeline) — 依赖 call_tools + fusion 产出 fused_context

## What to build

实现 Generator 节点，接入本地 LLM，将融合后的检索上下文生成带 `[N]` 引用标记的自然语言答案。

**1. Generator 节点**（`src/graph/generator.py` 重写）

- 使用 LLMClient 调用本地 vLLM（model 通过 Settings 配置）
- LLM 参数：temperature=0.1, max_tokens=2000, priority=realtime
- System prompt: 统一模板（所有 query_type 共用），要求 LLM：
  - 基于提供的检索上下文回答问题
  - 在引用处自动插入 `[N]` 标记（N 对应上下文中的序号）
  - 未找到相关信息时生成"抱歉，未找到..."风格回复
- User message: 将 fused_context + sub_questions + original query 组装
- fused_context 为空时，LLM 应生成"未找到"回复而非编造
- 输出写入 state.answer

**2. Generator prompt 设计**（`src/llm/prompts.py` 更新）

统一 system prompt，核心要求：
- 你是水工建筑物缺陷诊疗专家助手
- 严格依据提供的检索上下文回答，不要编造
- 引用原文时在句末添加 `[N]` 标记
- 上下文未覆盖的问题诚实告知"未找到"
- 保持专业、简洁的工程术语风格

**3. 端到端测试（无 Supervisor）**

使用临时图：`call_tools → fusion → generator → citation`，输入单一子问题（如"混凝土坝裂缝宽度超过多少需要处理"），验证：
- answer 非空，内容与检索结果相关
- answer 中包含 `[N]` 标记
- citation 数组非空且与 `[N]` 对应

## Acceptance criteria

- [ ] Generator 生成非空 answer，内容与检索上下文相关
- [ ] answer 中自动插入了 `[N]` 引用标记
- [ ] fused_context 为空时，Generator 生成"未找到"风格回复而非编造
- [ ] LLM 调用超时时返回错误，日志记录 trace_id
- [ ] 集成测试：真实 search-engine 检索 + 真实本地 LLM 生成，端到端验证 answer 质量
