import sys
from pathlib import Path

import httpx
import pytest

# Make agent-reasoning/src importable for tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Make daduhe_common importable (workspace sibling)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))

from src.settings import Settings


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
async def llm():
    """LLMClient (calls llm-gateway)."""
    from src.llm.client import LLMClient

    client = LLMClient(Settings())
    yield client


@pytest.fixture
async def httpx_client():
    """Shared httpx.AsyncClient whose lifecycle is managed by pytest."""
    async with httpx.AsyncClient(timeout=10) as client:
        yield client
