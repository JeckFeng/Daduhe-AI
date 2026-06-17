"""search-engine: 多模式检索引擎（关键词/模糊/向量/混合）"""
import os
import sys

sys.path.insert(0, "/app")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging import info, error as log_error
from common.tracing import get_or_generate_trace_id
from common.health import create_health_router
from common.error_codes import ErrorCode, error_response

SERVICE = "search-engine"

app = FastAPI(title="search-engine", version="0.1.0")

app.include_router(create_health_router(SERVICE, {}))


# ============================================================
# POST /api/v1/search/index — 接收HT异步通知，触发索引构建
# ============================================================

@app.post("/api/v1/search/index")
async def search_index(request: Request):
    trace_id = get_or_generate_trace_id(request, "search-engine")
    body = await request.json()
    doc_id = body.get("doc_id", "")

    info(SERVICE, "index build triggered", trace_id, doc_id=doc_id)

    return JSONResponse(
        status_code=202,
        content={
            "code": 0,
            "message": "accepted",
            "data": {"task_id": f"idx-task-{trace_id[-8:]}", "status": "processing"},
        },
    )


# ============================================================
# POST /api/v1/search — 统一检索入口
# ============================================================

@app.post("/api/v1/search")
async def search(request: Request):
    trace_id = get_or_generate_trace_id(request, "search-engine")
    body = await request.json()

    query = body.get("query", "")
    mode = body.get("mode", "hybrid")
    top_k = body.get("top_k", 10)
    filters = body.get("filters", {})
    include_sources = body.get("include_sources", ["chunks"])

    info(SERVICE, "search executed", trace_id, query=query, mode=mode, top_k=top_k)

    # TODO: 实现 keyword/fuzzy/vector/hybrid 多模式检索
    return JSONResponse(
        content={
            "code": 0,
            "data": {
                "results": [],
                "total_hits": 0,
                "mode_used": mode,
            },
        }
    )


@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
