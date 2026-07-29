from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_app_factory_returns_fastapi_and_registers_api_routes():
    from backend.app import app, create_app

    fresh_app = create_app()

    assert isinstance(app, FastAPI)
    assert isinstance(fresh_app, FastAPI)
    assert any(route.path == "/api/health" for route in fresh_app.routes)


def test_fastapi_serves_the_health_endpoint():
    from backend.routes.health import router

    application = FastAPI()
    application.include_router(router)
    response = TestClient(application).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
