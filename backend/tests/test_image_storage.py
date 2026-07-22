import requests

import pytest

from backend.services.image_storage import ImagePersistenceError, persist_generated_image


class Response:
    def __init__(self, status=200, content_type="image/png", chunks=(b"png",)):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.chunks = chunks if chunks != (b"png",) else (b"\x89PNG\r\n\x1a\nbody",)
        self.closed = False

    def iter_content(self, chunk_size):
        return iter(self.chunks)

    def close(self):
        self.closed = True


def test_persists_supported_image(tmp_path):
    value = persist_generated_image("https://provider.invalid/image?secret=value", tmp_path, lambda *_args, **_kwargs: Response())
    assert value.startswith("/static/images/image_") and value.endswith(".png")
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("getter", [
    lambda *_args, **_kwargs: Response(status=503),
    lambda *_args, **_kwargs: Response(content_type="text/html"),
    lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout()),
])
def test_rejects_unusable_download(tmp_path, getter):
    with pytest.raises(ImagePersistenceError):
        persist_generated_image("https://provider.invalid/image", tmp_path, getter)


def test_rejects_file_write_failure(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.services.image_storage.open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk")), raising=False)
    with pytest.raises(ImagePersistenceError):
        persist_generated_image("https://provider.invalid/image", tmp_path, lambda *_args, **_kwargs: Response())


def test_rejects_mime_signature_mismatch_and_closes(tmp_path):
    response = Response(content_type="image/jpeg", chunks=(b"\x89PNG\r\n\x1a\nbody",))
    with pytest.raises(ImagePersistenceError):
        persist_generated_image("https://provider.invalid/image", tmp_path, lambda *_args, **_kwargs: response)
    assert response.closed
