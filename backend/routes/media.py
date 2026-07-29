"""Generated image delivery endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGE_ROOT = PROJECT_ROOT / "static" / "images"

router = APIRouter(tags=["media"])


@router.get("/static/images/{filename}")
def serve_generated_image(filename: str):
    target = (IMAGE_ROOT / filename).resolve()
    if IMAGE_ROOT.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(target)
