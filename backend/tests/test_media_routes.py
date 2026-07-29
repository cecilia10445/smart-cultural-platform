from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import media


def test_generated_image_route_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "IMAGE_ROOT", tmp_path / "images")
    application = FastAPI()
    application.include_router(media.router)

    response = TestClient(application).get("/static/images/../secret.png")

    assert response.status_code == 404
