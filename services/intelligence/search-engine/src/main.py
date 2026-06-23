"""search-engine: 多模式检索引擎（关键词/模糊/向量/混合）"""
import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymilvus import MilvusClient

from daduhe_common import (
    TraceMiddleware,
    info,
    error as log_error,
    get_or_generate_trace_id,
    create_health_router,
)

from src.models import SearchRequest, SearchResponse, SearchResponseData
from src.settings import Settings
from src.backends.keyword import search_keyword
from src.backends.fuzzy import search_fuzzy
from src.backends.vector import search_vector
from src.backends.hybrid import search_hybrid

SERVICE = "search-engine"
settings = Settings()

milvus_client = MilvusClient(
    uri=settings.milvus_uri,
    user=settings.milvus_user,
    password=settings.milvus_password,
    db_name=settings.milvus_db,
)


def get_pg_conn():
    return psycopg2.connect(
        host=settings.pg_host, port=settings.pg_port,
        user=settings.pg_user, password=settings.pg_password,
        dbname=settings.pg_dbname,
    )


app = FastAPI(title="search-engine", version="0.1.0")
app.add_middleware(TraceMiddleware, service=SERVICE)

app.include_router(create_health_router(SERVICE, {}))


@app.post("/api/v1/search")
async def search(request: Request):
    trace_id = get_or_generate_trace_id(request, SERVICE)
    body = await request.json()
    req = SearchRequest(**body)

    if "rules" in req.include_sources:
        return JSONResponse(
            status_code=400,
            content={
                "code": 1002,
                "message": "include_sources 'rules' is not yet available: LSL rule-extractor service is not integrated",
                "data": None,
            },
        )

    info(SERVICE, "search executed", trace_id, query=req.query, mode=req.mode, top_k=req.top_k)

    conn = get_pg_conn()
    conn.autocommit = True
    try:
        if req.mode == "keyword":
            results = search_keyword(conn, req.query, req.filters, req.top_k)
        elif req.mode == "fuzzy":
            results = search_fuzzy(conn, req.query, req.filters, req.top_k)
        elif req.mode == "vector":
            results = search_vector(
                milvus_client, settings.ollama_url, conn,
                req.query, req.filters, req.top_k, settings.milvus_collection,
            )
        elif req.mode == "hybrid":
            results = search_hybrid(
                milvus_client, settings.ollama_url, conn,
                req.query, req.filters, req.top_k, settings.milvus_collection,
                rrf_k=settings.rrf_k,
            )
        else:
            results = []
    finally:
        conn.close()

    return SearchResponse(
        data=SearchResponseData(
            results=results,
            total_hits=len(results),
            mode_used=req.mode,
        )
    ).model_dump(mode="json")


@app.post("/api/v1/search/index")
async def search_index(request: Request):
    trace_id = get_or_generate_trace_id(request, SERVICE)
    body = await request.json()
    doc_id = body.get("doc_id", "")

    info(SERVICE, "index build triggered", trace_id, doc_id=doc_id)

    task_id = f"idx-task-{trace_id[-8:]}"

    # 1. Read chunks from PG
    conn = get_pg_conn()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT chunk_id, chunk_text FROM metadata.chunks WHERE doc_id = %s ORDER BY chunk_index",
            (doc_id,),
        )
        chunks = [{"chunk_id": row[0], "chunk_text": row[1]} for row in cur.fetchall()]
        cur.close()

        if not chunks:
            return JSONResponse(
                status_code=400,
                content={
                    "code": 3002,
                    "message": f"doc_id not found: {doc_id}",
                    "data": None,
                },
            )
    finally:
        conn.close()

    # 2. Generate embeddings
    import httpx
    vectors = []
    for chunk in chunks:
        resp = httpx.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": "bge-m3", "prompt": chunk["chunk_text"]},
            timeout=30,
        )
        resp.raise_for_status()
        vectors.append(resp.json()["embedding"])

    # 3. Upsert into Milvus
    coll = settings.milvus_collection

    # Ensure collection exists
    if not milvus_client.has_collection(coll):
        from pymilvus import DataType
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        milvus_client.create_collection(collection_name=coll, schema=schema)

    # Delete existing data for this doc_id (idempotent upsert)
    try:
        milvus_client.load_collection(coll)
        existing = milvus_client.query(coll, filter=f'doc_id == "{doc_id}"', output_fields=["id"], limit=100)
        if existing:
            ids_to_delete = [e["id"] for e in existing]
            milvus_client.delete(coll, ids=ids_to_delete)
    except Exception:
        pass  # No existing data or index not ready

    # Insert
    data = [
        {"vector": vec, "chunk_id": chunk["chunk_id"], "doc_id": doc_id}
        for chunk, vec in zip(chunks, vectors)
    ]
    insert_result = milvus_client.insert(collection_name=coll, data=data)

    # Build index if not already present
    try:
        idx = milvus_client.describe_index(coll, "vector")
        has_index = idx["index_type"] != "FLAT_INDEX"
    except Exception:
        has_index = False

    if not has_index:
        nlist = min(1024, max(1, len(chunks) // 2))
        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="vector", index_type="IVF_FLAT",
            metric_type="COSINE", params={"nlist": nlist},
        )
        try:
            milvus_client.create_index(collection_name=coll, index_params=index_params)
        except Exception:
            pass

    # Release so next load sees fresh data
    try:
        milvus_client.release_collection(coll)
    except Exception:
        pass

    info(SERVICE, "index build completed", trace_id, doc_id=doc_id,
         chunk_count=len(chunks), inserted=insert_result["insert_count"])

    return JSONResponse(
        status_code=202,
        content={
            "code": 0,
            "message": "accepted",
            "data": {"task_id": task_id, "status": "completed",
                     "chunk_count": len(chunks), "inserted": insert_result["insert_count"]},
        },
    )


@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("# TODO: daduh_* metrics\n")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
