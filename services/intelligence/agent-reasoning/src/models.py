"""Pydantic 请求/响应模型 — ICD-03 §6 定义的 API 契约。

定义 /api/v1/chat 和 /api/v1/llm/completion 两个接口的
请求体和响应体结构，以及错误响应格式。
"""

from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════
# POST /api/v1/chat
# ═══════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """智能问答请求体。

    Attributes:
        query: 用户输入的问题（必填）
        conversation_id: 会话 ID，首次不传则由服务端创建
        retrieval_mode: 检索模式，当前仅作保留字段
        stream: 是否启用 SSE 流式输出
    """

    query: str = Field(min_length=1)
    conversation_id: Optional[str] = None
    retrieval_mode: str = Field(
        default="auto", pattern=r"^(auto|keyword|fuzzy|vector|hybrid)$"
    )
    stream: bool = False


class Citation(BaseModel):
    """单条引用信息。

    Attributes:
        index: 引用在答案中的角标编号 [N]
        chunk_id: 关联的 chunk 唯一标识
        doc_title: 来源文档标题
        doc_type: 文档类型（规范/案例/文献）
        section: 章节信息
        page: 页码
        download_url: 文档下载链接
        excerpt: 引用文本摘录（最多 150 字）
    """

    index: int
    chunk_id: str
    doc_title: str
    doc_type: str
    section: str = ""
    page: Optional[int] = None
    download_url: str
    excerpt: str


class ChatResponseData(BaseModel):
    """智能问答成功响应数据体。

    Attributes:
        answer: 生成的答案文本（含 [N] 引用标记）
        citations: 引用信息数组
        retrieval_mode_used: 实际使用的检索模式
        conversation_id: 会话 ID
        trace_id: 链路追踪 ID
    """

    answer: str
    citations: list[Citation] = []
    retrieval_mode_used: str
    conversation_id: str
    trace_id: str


class ChatResponse(BaseModel):
    """智能问答顶层响应体。

    Attributes:
        code: 业务状态码，0=成功
        data: 响应数据体
    """

    code: int = 0
    data: ChatResponseData


# ═══════════════════════════════════════════════════
# POST /api/v1/llm/completion
# ═══════════════════════════════════════════════════


class Message(BaseModel):
    """单条对话消息。

    Attributes:
        role: 消息角色（system/user/assistant）
        content: 消息内容
    """

    role: str
    content: str


class LLMCompletionRequest(BaseModel):
    """LLM 调用请求体。

    Attributes:
        model: 模型名称
        messages: 对话消息列表
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        caller: 调用方标识（"agent-reasoning" 或 "graph-engine"）
        priority: 优先级（realtime 低延迟 / batch 高吞吐）
    """

    model: str = "deepseek-chat"
    messages: list[Message]
    temperature: float = 0.1
    max_tokens: int = 2000
    caller: str
    priority: str = Field(default="batch", pattern=r"^(realtime|batch)$")


class Usage(BaseModel):
    """LLM Token 用量统计。

    Attributes:
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMCompletionData(BaseModel):
    """LLM 调用成功响应数据体。

    Attributes:
        id: 响应唯一标识
        content: LLM 输出文本
        model: 实际使用的模型
        usage: Token 用量
        latency_ms: 调用耗时（毫秒）
    """

    id: str
    content: str
    model: str
    usage: Usage
    latency_ms: float = 0


class LLMCompletionResponse(BaseModel):
    """LLM 调用顶层响应体。

    Attributes:
        code: 业务状态码
        data: 响应数据体
    """

    code: int = 0
    data: LLMCompletionData


# ═══════════════════════════════════════════════════
# 错误响应（ICD-03 §8）
# ═══════════════════════════════════════════════════


class ErrorResponse(BaseModel):
    """统一错误响应体。

    Attributes:
        code: 错误码
        message: 错误描述
        trace_id: 链路追踪 ID
    """

    code: int
    message: str
    trace_id: str
