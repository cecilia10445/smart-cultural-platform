"""User profile, history, rating, and download endpoints."""

from fastapi import APIRouter, Request

from backend.routes._bridge import invoke

router = APIRouter(tags=["users"])


@router.get("/api/user/profile")
async def get_profile(request: Request):
    from backend.routes import api
    return await invoke(api.get_user_profile, request)


@router.get("/api/user/history")
async def get_history(request: Request):
    from backend.routes import api
    return await invoke(api.get_user_history, request)


@router.post("/api/rating")
async def submit_rating(request: Request):
    from backend.routes import api
    return await invoke(api.submit_rating, request)


@router.post("/api/download")
async def record_download(request: Request):
    from backend.routes import api
    return await invoke(api.record_download, request)
