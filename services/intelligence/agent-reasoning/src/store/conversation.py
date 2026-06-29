"""会话存储 — 多轮对话历史的管理和检索。

Phase A: 内存 dict 实现。
Phase B+: 替换为 PostgreSQL 后端持久化。
"""

import time
from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """单条对话消息。

    Attributes:
        role: 消息角色，'user'、'assistant' 或 'system'
        content: 消息文本内容
        timestamp: 消息时间戳（秒级 Unix 时间）
    """

    role: str = Field(description="'user' | 'assistant' | 'system'")
    content: str
    timestamp: float = Field(default_factory=time.time)


class InMemoryConversationStore:
    """内存会话存储。

    按 conversation_id 存储完整对话历史。存储层不限制上下文窗口大小，
    由消费方（如 get_recent）按需截取——存储和上下文加载策略解耦。
    """

    def __init__(self) -> None:
        """初始化空存储。"""
        self._store: dict[str, list[ConversationMessage]] = {}

    async def get_history(self, conversation_id: str) -> list[ConversationMessage]:
        """获取会话的完整消息历史。

        Args:
            conversation_id: 会话唯一标识

        Returns:
            list[ConversationMessage]: 消息列表，按时间顺序排列
        """
        return list(self._store.get(conversation_id, []))

    async def append_messages(
        self,
        conversation_id: str,
        messages: list[ConversationMessage],
    ) -> None:
        """向会话追加一条或多条消息。

        Args:
            conversation_id: 会话唯一标识
            messages: 待追加的消息列表
        """
        if conversation_id not in self._store:
            self._store[conversation_id] = []
        self._store[conversation_id].extend(messages)

    async def get_recent(
        self,
        conversation_id: str,
        turns: int = 5,
    ) -> list[ConversationMessage]:
        """获取最近 N 轮对话。

        Args:
            conversation_id: 会话唯一标识
            turns: 轮数，每轮 = 1 条 user + 1 条 assistant = 2 条消息

        Returns:
            list[ConversationMessage]: 最近的 N 轮消息
        """
        history = self._store.get(conversation_id, [])
        count = turns * 2
        return history[-count:] if len(history) > count else list(history)
