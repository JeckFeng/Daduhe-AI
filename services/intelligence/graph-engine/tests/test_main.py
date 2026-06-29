"""Test FastAPI endpoints: /health, /ready, /metrics."""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


class TestHealth:
    def test_health_returns_200(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


class TestReady:
    def test_ready_returns_200(self):
        r = client.get("/ready")
        assert r.status_code in (200, 503)  # 503 if memgraph not reachable

    def test_ready_includes_memgraph_check(self):
        r = client.get("/ready")
        data = r.json()
        assert "checks" in data
        assert "memgraph" in data["checks"]


class TestMetrics:
    def test_metrics_returns_required_metric_names(self):
        r = client.get("/metrics")
        assert r.status_code == 200
        text = r.text
        assert "daduh_graph_extraction_duration_s" in text
        assert "daduh_http_requests_total" in text

    def test_http_counter_uses_real_prometheus_client(self):
        """Real prometheus_client generates process_* and python_info metrics."""
        r = client.get("/metrics")
        assert r.status_code == 200
        text = r.text
        # prometheus_client's generate_latest() always includes these defaults
        assert "python_info" in text, "Should use real prometheus_client (not stub)"


class TestExtractEndpoint:
    @pytest.mark.integration
    def test_extract_returns_202_with_task_id(self):
        r = client.post("/api/v1/graph/extract", json={"doc_id": "seed-doc-001"})
        assert r.status_code == 202
        data = r.json()
        assert data["code"] == 0
        assert "task_id" in data["data"]


class TestQueryEndpoint:
    @pytest.mark.integration
    def test_query_entity_search_returns_200(self):
        r = client.post(
            "/api/v1/graph/query",
            json={
                "query_type": "entity_search",
                "params": {"query": "裂缝"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert "entities" in data["data"]
        assert "edges" in data["data"]
