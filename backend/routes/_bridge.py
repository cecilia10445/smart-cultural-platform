"""Temporary request binding for legacy business implementations.

This module does not register routes. It lets native FastAPI endpoint functions
call an unchanged implementation while that implementation is split into
services.
"""

from fastapi import Request

async def invoke(handler, request: Request, *, run_id: str | None = None, filename: str | None = None):
    from backend.routes import api
    try:
        body = await request.json()
    except Exception:
        body = None
    return api._dispatch(handler, request, body, run_id, filename)
