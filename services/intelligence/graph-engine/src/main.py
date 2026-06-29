"""graph-engine 服务入口：FastAPI 应用，提供知识图谱抽取与查询 API。

端点：
- POST /api/v1/graph/extract — 触发实体关系抽取任务
- POST /api/v1/graph/query   — 向量+图混合查询（entity_search / relation_search）
- GET  /health /ready        — 健康检查（由 daduhe_common 提供）
- GET  /metrics              — Prometheus 指标
"""

import asyncio
from contextlib import asynccontextmanager

import prometheus_client
import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from neo4j import GraphDatabase

from daduhe_common import (
    TraceMiddleware,
    info,
    error as log_error,
    get_or_generate_trace_id,
    create_health_router,
)

from src.extraction.worker import process_extraction_task
from src.models import ExtractionTaskRequest, GraphQueryRequest
from src.query.service import GraphQueryService
from src.settings import Settings
from src.store.memgraph import MemgraphStore
from src.store.milvus import MilvusStore
from src.store.task_store import TaskStore

SERVICE = "graph-engine"
settings = Settings()

# ── Prometheus 指标 ────────────────────────────────────────────────
http_requests_total = prometheus_client.Counter(
    "daduh_http_requests_total",
    "Total HTTP requests.",
    labelnames=["service"],
)
extraction_duration_s = prometheus_client.Histogram(
    "daduh_graph_extraction_duration_s",
    "Extraction duration in seconds.",
    labelnames=["doc_id"],
)

_MEMGRAPH_UP = False


def _check_memgraph() -> str:
    """检查 Memgraph 连通性。

    Returns:
        "ok" 表示连接正常，否则返回错误描述字符串。
    """
    global _MEMGRAPH_UP
    try:
        driver = GraphDatabase.driver(
            settings.memgraph_uri,
            auth=(settings.memgraph_username, settings.memgraph_password),
        )
        with driver.session(database=settings.memgraph_database) as session:
            session.run("MATCH (n) RETURN count(n) LIMIT 1")
        driver.close()
        _MEMGRAPH_UP = True
        return "ok"
    except Exception as e:
        _MEMGRAPH_UP = False
        return str(e)


def _create_pg_tables() -> None:
    """创建 graph_engine schema 及 extraction_tasks、llm_cache 表（幂等）。"""
    try:
        conn = psycopg2.connect(
            host=settings.pg_host,
            port=settings.pg_port,
            user=settings.pg_user,
            password=settings.pg_password,
            dbname=settings.pg_database,
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("CREATE SCHEMA IF NOT EXISTS graph_engine")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_engine.extraction_tasks (
                task_id       VARCHAR(64) PRIMARY KEY,
                doc_id        VARCHAR(64) NOT NULL,
                status        VARCHAR(20) NOT NULL DEFAULT 'pending',
                progress      JSONB DEFAULT '{}',
                result        JSONB DEFAULT '{}',
                error_message TEXT,
                created_at    TIMESTAMPTZ DEFAULT now(),
                updated_at    TIMESTAMPTZ DEFAULT now(),
                completed_at  TIMESTAMPTZ
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_engine.llm_cache (
                cache_key  VARCHAR(64) PRIMARY KEY,
                model      VARCHAR(128) NOT NULL,
                system_prompt TEXT NOT NULL,
                user_prompt   TEXT NOT NULL,
                response   JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)

        cur.close()
        conn.close()
        info(SERVICE, "PG tables ensured", trace_id=None)
    except Exception as e:
        log_error(SERVICE, "failed to create PG tables", trace_id=None, error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时创建表并检查 Memgraph，关闭时无操作。"""
    _create_pg_tables()
    _check_memgraph()
    yield


app = FastAPI(title="graph-engine", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware, service=SERVICE)


@app.middleware("http")
async def _count_requests(request: Request, call_next):
    """中间件：记录每次 HTTP 请求的 Prometheus 计数器。"""
    http_requests_total.labels(service=SERVICE).inc()
    response = await call_next(request)
    return response


app.include_router(create_health_router(SERVICE, {"memgraph": _check_memgraph}))


# ============================================================
# POST /api/v1/graph/extract — 触发实体关系抽取
# ============================================================


@app.post("/api/v1/graph/extract")
async def graph_extract(request: Request):
    """触发文档的实体关系抽取任务。

    对同一 doc_id 幂等：已完成返回 200，进行中返回 409，否则创建新任务并异步执行。
    """
    trace_id = get_or_generate_trace_id(request, "graph-engine")
    body = await request.json()

    try:
        req = ExtractionTaskRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "code": 1001,
                "message": f"invalid request: {e}",
                "trace_id": trace_id,
            },
        )

    doc_id = req.doc_id
    info(SERVICE, "graph extraction triggered", trace_id, doc_id=doc_id)

    task_store = TaskStore(settings)
    existing = task_store.find_by_doc_id(doc_id)

    if existing:
        if existing["status"] in ("pending", "processing"):
            return JSONResponse(
                status_code=409,
                content={
                    "code": 5003,
                    "message": f"graph extraction failed: already in progress for doc_id={doc_id}",
                    "trace_id": trace_id,
                },
            )
        if existing["status"] == "completed":
            return JSONResponse(
                status_code=200,
                content={
                    "code": 0,
                    "message": "already done",
                    "data": {
                        "task_id": existing["task_id"],
                        "status": "completed",
                    },
                    "trace_id": trace_id,
                },
            )

    # 创建新任务并异步启动抽取管线
    task = task_store.create_task(doc_id, "processing")

    asyncio.create_task(process_extraction_task(task["task_id"], doc_id, settings))

    return JSONResponse(
        status_code=202,
        content={
            "code": 0,
            "message": "accepted",
            "data": {"task_id": task["task_id"], "status": "processing"},
            "trace_id": trace_id,
        },
    )


# ============================================================
# POST /api/v1/graph/query — 知识图谱查询
# ============================================================

_query_service: GraphQueryService | None = None
_query_lock = asyncio.Lock()


async def _get_query_service() -> GraphQueryService:
    """延迟初始化 GraphQueryService（双重检查锁）。

    首次调用时初始化 Memgraph + Milvus 连接，后续调用复用单例。
    """
    global _query_service
    if _query_service is not None:
        return _query_service
    async with _query_lock:
        if _query_service is not None:
            return _query_service
        store = MemgraphStore(settings)
        await store.initialize()
        milvus = MilvusStore(settings)
        milvus.initialize()
        _query_service = GraphQueryService(store, milvus, settings)
    return _query_service


@app.post("/api/v1/graph/query")
async def graph_query(request: Request):
    """知识图谱查询：支持 entity_search 和 relation_search 两种模式。

    entity_search:  向量搜索实体 → Memgraph 批量获取节点 + 图扩展边
    relation_search: 向量搜索关系 → Memgraph 获取端点实体 + 格式化边
    """
    trace_id = get_or_generate_trace_id(request, "graph-engine")
    body = await request.json()

    try:
        req = GraphQueryRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "code": 1001,
                "message": f"invalid request: {e}",
                "trace_id": trace_id,
            },
        )

    info(SERVICE, "graph query", trace_id, query_type=req.query_type, params=req.params)

    try:
        service = await _get_query_service()
        result = await service.query(req.query_type, req.params)
        result["query_type"] = req.query_type
        return JSONResponse(
            content={"code": 0, "message": "ok", "data": result, "trace_id": trace_id},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"code": 1002, "message": str(e), "trace_id": trace_id},
        )
    except Exception as e:
        log_error(SERVICE, "graph query failed", trace_id, error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "code": 9001,
                "message": f"query failed: {e}",
                "trace_id": trace_id,
            },
        )


# ============================================================
# Prometheus 指标端点
# ============================================================


@app.get("/metrics")
async def metrics():
    """Prometheus 指标暴露端点。"""
    return PlainTextResponse(prometheus_client.generate_latest())
