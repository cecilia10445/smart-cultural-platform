"""Text and cultural-product generation endpoints."""

from fastapi import APIRouter, Request

from backend.routes._bridge import invoke

router = APIRouter(tags=["generation"])


@router.post("/api/generate")
async def generate(request: Request):
    from backend.routes import api
    return await invoke(api.generate_content_api, request)


@router.post("/api/v2/cultural-products/generate")
async def generate_cultural_product(request: Request):
    from backend.routes import api
    return await invoke(api.generate_cultural_product_api, request)


@router.post("/api/v2/cultural-products/generate-with-text-skill")
async def generate_with_text_skill(request: Request):
    from backend.routes import api
    return await invoke(api.generate_cultural_product_with_text_skill_api, request)


@router.get("/api/v2/cultural-products/text-skill-generations/{run_id}")
async def get_text_skill_generation(run_id: str, request: Request):
    from backend.routes import api
    return await invoke(api.get_cultural_product_text_skill_generation_api, request, run_id=run_id)
