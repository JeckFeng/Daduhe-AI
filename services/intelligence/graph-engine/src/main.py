"""graph-engine: 知识图谱实体关系抽取与推理"""
import os
import sys

sys.path.insert(0, "/app")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging import info, error as log_error
from common.tracing import get_or_generate_trace_id
from common.health import create_health_router
from common.error_codes import ErrorCode, error_response

SERVICE = "graph-engine"

app = FastAPI(title="graph-engine", version="0.1.0")

# 健康检查
app.include_router(create_health_router(SERVICE, {}))


# ============================================================
# POST /api/v1/graph/extract — 触发实体关系抽取
# ============================================================

@app.post("/api/v1/graph/extract")
async def graph_extract(request: Request):
    trace_id = get_or_generate_trace_id(request, "graph-engine")
    body = await request.json()
    doc_id = body.get("doc_id", "")

    info(SERVICE, "graph extraction triggered", trace_id, doc_id=doc_id)

    return JSONResponse(
        status_code=202,
        content={
            "code": 0,
            "message": "accepted",
            "data": {"task_id": f"g-task-{trace_id[-8:]}", "status": "processing"},
        },
    )


# ============================================================
# POST /api/v1/graph/query — 知识图谱查询
# ============================================================

@app.post("/api/v1/graph/query")
async def graph_query(request: Request):
    trace_id = get_or_generate_trace_id(request, "graph-engine")
    body = await request.json()
    query_type = body.get("query_type", "")
    params = body.get("params", {})

    info(SERVICE, "graph query", trace_id, query_type=query_type)

    # TODO: Neo4j Cypher查询实现
    return JSONResponse(
        content={
            "code": 0,
            "data": {
                "nodes": [],
                "edges": [],
                "query_type": query_type,
            },
        }
    )


# ============================================================
# POST /api/v1/graph/reasoning — 知识图谱推理
# ============================================================

@app.post("/api/v1/graph/reasoning")
async def graph_reasoning(request: Request):
    trace_id = get_or_generate_trace_id(request, "graph-engine")
    body = await request.json()

    info(SERVICE, "graph reasoning", trace_id, entity=body.get("entity_name", ""))

    # TODO: Neo4j多跳推理实现
    return JSONResponse(
        content={
            "code": 0,
            "data": {
                "root": {"type": body.get("entity_type", ""), "name": body.get("entity_name", "")},
                "paths": [],
                "depth": body.get("depth", 3),
            },
        }
    )


# ============================================================
# Prometheus metrics
# ============================================================

@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
