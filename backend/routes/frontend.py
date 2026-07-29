"""Frontend static asset delivery."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
router = APIRouter(tags=["frontend"])


@router.get("/")
def home():
    login = FRONTEND_ROOT / "login.html"
    if login.is_file():
        return FileResponse(login)
    return HTMLResponse("<h1>智能文创平台</h1>")


@router.get("/{filename:path}")
def static_file(filename: str):
    target = (FRONTEND_ROOT / filename.removeprefix("frontend/")).resolve()
    if FRONTEND_ROOT.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "文件未找到")
    return FileResponse(target)
