"""健康检查端点"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def create_health_router(service_name: str, checks: dict[str, callable]) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @router.get("/ready")
    async def ready():
        results = {}
        all_ok = True
        for name, check_fn in checks.items():
            try:
                results[name] = check_fn()
            except Exception:
                results[name] = "fail"
                all_ok = False

        status_code = 200 if all_ok else 503
        return JSONResponse(
            {"status": "ready" if all_ok else "not ready", "checks": results},
            status_code=status_code,
        )

    return router
