"""Tests for daduhe_common.middleware — TraceMiddleware behavior through public HTTP interface."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from daduhe_common.middleware import TraceMiddleware


def _app_with_middleware(service: str = "test-svc"):
    app = FastAPI()
    app.add_middleware(TraceMiddleware, service=service)

    @app.get("/echo")
    async def echo(request: Request):
        return {"trace_id": request.state.trace_id}

    return app


def test_generates_trace_id_when_header_missing():
    """When no X-Trace-Id in request, middleware generates one with service prefix."""
    client = TestClient(_app_with_middleware("graph-engine"))
    resp = client.get("/echo")

    assert resp.status_code == 200
    assert resp.json()["trace_id"].startswith("graph-engine-")
    assert resp.headers["X-Trace-Id"] == resp.json()["trace_id"]


def test_uses_existing_trace_id():
    """When X-Trace-Id header present, middleware uses it as-is and echoes in response."""
    client = TestClient(_app_with_middleware())
    resp = client.get("/echo", headers={"X-Trace-Id": "ht-abc123-def456"})

    assert resp.json()["trace_id"] == "ht-abc123-def456"
    assert resp.headers["X-Trace-Id"] == "ht-abc123-def456"


def test_trace_id_available_in_request_state():
    """Endpoint can read trace_id from request.state without manual extraction."""
    client = TestClient(_app_with_middleware("search-engine"))

    # Two requests should have different trace_ids
    r1 = client.get("/echo")
    r2 = client.get("/echo")

    assert r1.json()["trace_id"] != r2.json()["trace_id"]
    assert r1.json()["trace_id"].startswith("search-engine-")
    assert r2.json()["trace_id"].startswith("search-engine-")
