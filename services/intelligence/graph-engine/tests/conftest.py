import os
import sys
from pathlib import Path

import pytest

# Make graph-engine/src importable for tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Make daduhe_common importable (workspace sibling)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require external dependencies (Memgraph, PG, LLM)",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("GRAPH_SKIP_INTEGRATION_TESTS"):
        skip_mark = pytest.mark.skip(reason="GRAPH_SKIP_INTEGRATION_TESTS is set")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_mark)


@pytest.fixture
def integration_check():
    """Fixture: skip if integration tests disabled. Use as function parameter."""
    if os.environ.get("GRAPH_SKIP_INTEGRATION_TESTS"):
        pytest.skip("GRAPH_SKIP_INTEGRATION_TESTS is set")
