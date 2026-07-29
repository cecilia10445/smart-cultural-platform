"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.auth import router as auth_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.frontend import router as frontend_router
from backend.routes.generation import router as generation_router
from backend.routes.health import router as health_router
from backend.routes.media import router as media_router
from backend.routes.system import router as system_router
from backend.routes.users import router as users_router


def create_app() -> FastAPI:
    """Create the ASGI application and preserve established HTTP contracts.

    Existing synchronous handlers are registered as FastAPI routes; their HTTP
    paths and response contracts remain stable while domains are split further.
    """
    application = FastAPI(title="智能文创平台 API", docs_url=None, redoc_url=None)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(media_router)
    application.include_router(system_router, include_in_schema=False)
    application.include_router(users_router)
    application.include_router(dashboard_router)
    application.include_router(generation_router)
    application.include_router(frontend_router)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=5000, reload=True)
