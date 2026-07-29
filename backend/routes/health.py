"""Dependency-free liveness endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/api/health")
@router.get("/api/health/live")
def health_check() -> dict[str, str]:
    return {"status": "alive"}
