"""Safe local storage for generated image bytes; never persists provider URLs."""

from __future__ import annotations

import hashlib
import os
import secrets

import requests

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAGIC_BYTES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}


class ImagePersistenceError(Exception):
    pass


def persist_generated_image(image_url, static_images_dir, http_get=requests.get):
    """Fetch a bounded image and return a stable local URL, or raise a safe error."""
    try:
        response = http_get(image_url, timeout=(5, 20), stream=True)
    except requests.Timeout as exc:
        raise ImagePersistenceError("Generated image download timed out.") from exc
    except requests.RequestException as exc:
        raise ImagePersistenceError("Generated image download failed.") from exc
    try:
        if response.status_code != 200:
            raise ImagePersistenceError("Generated image download failed.")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        suffix = ALLOWED_CONTENT_TYPES.get(content_type)
        if not suffix:
            raise ImagePersistenceError("Generated image response was not a supported image.")
        declared_length = response.headers.get("Content-Length")
        if declared_length and (not declared_length.isdigit() or int(declared_length) > MAX_IMAGE_BYTES):
            raise ImagePersistenceError("Generated image was too large.")
        data = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ImagePersistenceError("Generated image was too large.")
        except (OSError, requests.RequestException) as exc:
            raise ImagePersistenceError("Generated image download failed.") from exc
        if not data:
            raise ImagePersistenceError("Generated image response was empty.")
        if content_type == "image/webp":
            valid = data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        else:
            valid = data.startswith(MAGIC_BYTES[content_type])
        if not valid:
            raise ImagePersistenceError("Generated image content did not match its type.")
        digest = hashlib.sha256(data).hexdigest()[:16]
        filename = f"image_{digest}_{secrets.token_hex(4)}{suffix}"
        try:
            os.makedirs(static_images_dir, exist_ok=True)
            with open(os.path.join(static_images_dir, filename), "xb") as file:
                file.write(data)
        except OSError as exc:
            raise ImagePersistenceError("Generated image could not be saved.") from exc
        return f"/static/images/{filename}"
    finally:
        response.close()


def remove_persisted_image(local_url, static_images_dir):
    """Remove only a generated filename in this request's static image directory."""
    filename = os.path.basename(local_url)
    if not local_url.startswith("/static/images/image_") or filename != local_url.rsplit("/", 1)[-1]:
        return False
    try:
        os.unlink(os.path.join(static_images_dir, filename))
        return True
    except OSError:
        return False
