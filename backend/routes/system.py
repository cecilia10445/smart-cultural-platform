"""Native FastAPI system endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/api/health/ready")
def readiness_check():
    from backend.routes import api

    mysql_ready = False
    if api.mysql_service is not None:
        try:
            mysql_ready = bool(api.mysql_service.connect())
        except Exception:
            mysql_ready = False
    model_configured = bool(api.load_settings().dashscope_api_key)
    checks = {
        "mysql": "ready" if mysql_ready else "unavailable",
        "generation_model": "configured" if model_configured else "unavailable",
        "hive": "optional",
    }
    return {"status": "ready" if mysql_ready and model_configured else "unavailable", "checks": checks}
