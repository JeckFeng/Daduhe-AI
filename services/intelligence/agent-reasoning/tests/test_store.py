"""Unit tests for InMemoryConversationStore."""

import pytest
from src.store.conversation import ConversationMessage, InMemoryConversationStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def store():
    return InMemoryConversationStore()


class TestInMemoryConversationStore:
    async def test_get_history_empty(self, store):
        history = await store.get_history("conv-1")
        assert history == []

    async def test_append_and_get_history(self, store):
        msg = ConversationMessage(role="user", content="你好")
        await store.append_messages("conv-1", [msg])

        history = await store.get_history("conv-1")
        assert len(history) == 1
        assert history[0].role == "user"
        assert history[0].content == "你好"

    async def test_append_multiple_messages(self, store):
        msgs = [
            ConversationMessage(role="user", content="q1"),
            ConversationMessage(role="assistant", content="a1"),
            ConversationMessage(role="user", content="q2"),
        ]
        await store.append_messages("conv-1", msgs)

        history = await store.get_history("conv-1")
        assert len(history) == 3

    async def test_get_recent_truncation(self, store):
        msgs = [
            ConversationMessage(role="user", content="q1"),
            ConversationMessage(role="assistant", content="a1"),
            ConversationMessage(role="user", content="q2"),
            ConversationMessage(role="assistant", content="a2"),
            ConversationMessage(role="user", content="q3"),
            ConversationMessage(role="assistant", content="a3"),
        ]
        await store.append_messages("conv-1", msgs)

        # get_recent(turns=1) = last 2 messages
        recent = await store.get_recent("conv-1", turns=1)
        assert len(recent) == 2
        assert recent[0].content == "q3"
        assert recent[1].content == "a3"

        # get_recent(turns=2) = last 4 messages
        recent = await store.get_recent("conv-1", turns=2)
        assert len(recent) == 4
        assert recent[0].content == "q2"

    async def test_get_recent_more_than_stored(self, store):
        msgs = [
            ConversationMessage(role="user", content="q1"),
            ConversationMessage(role="assistant", content="a1"),
        ]
        await store.append_messages("conv-1", msgs)

        recent = await store.get_recent("conv-1", turns=5)
        assert len(recent) == 2  # only 2 stored, return all

    async def test_isolated_conversations(self, store):
        await store.append_messages(
            "conv-1",
            [
                ConversationMessage(role="user", content="c1-msg"),
            ],
        )
        await store.append_messages(
            "conv-2",
            [
                ConversationMessage(role="user", content="c2-msg"),
            ],
        )

        h1 = await store.get_history("conv-1")
        h2 = await store.get_history("conv-2")
        assert len(h1) == 1
        assert len(h2) == 1
        assert h1[0].content == "c1-msg"
        assert h2[0].content == "c2-msg"

    async def test_timestamp_auto_generated(self, store):
        msg = ConversationMessage(role="user", content="test")
        assert msg.timestamp > 0

    async def test_timestamp_explicit(self, store):
        msg = ConversationMessage(role="user", content="test", timestamp=1000.0)
        assert msg.timestamp == 1000.0
