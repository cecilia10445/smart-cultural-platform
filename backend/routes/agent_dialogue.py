"""Owner-scoped HTTP boundary for collaborative design sessions (round one)."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from starlette.responses import JSONResponse

from backend.domain.agent_dialogue import (
    AgentDecisionRequest,
    AgentDialogueError,
    AgentPersistenceUnavailable,
    AppendAgentMessageRequest,
    CreateAgentSessionRequest,
)
from backend.services.agent_dialogue_repository import AgentDialogueRepository
from backend.services.agent_dialogue_service import AgentDialogueService


router = APIRouter(tags=["agent-design"])


def _request_id(request: Request) -> str:
    value = getattr(request.state, "agent_request_id", None)
    if not isinstance(value, str):
        value = str(uuid.uuid4())
        request.state.agent_request_id = value
    return value


def _error(request: Request, code: str, message: str, status_code: int, *, retryable: bool = False, unavailable: bool = False):
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "unavailable" if unavailable else "error",
            "code": code,
            "message": message,
            "request_id": _request_id(request),
            "retryable": retryable,
        },
    )


def get_jwt_config() -> tuple[str, str]:
    """Read the established compatibility JWT configuration lazily."""
    from backend.routes import api

    return api.JWT_SECRET, api.JWT_ALGORITHM


def _authenticated_user_id(request: Request) -> str | None:
    """Use the established JWT secret/algorithm without accepting an owner body field."""
    secret, algorithm = get_jwt_config()

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not secret:
        return None
    try:
        payload = jwt.decode(header[7:], secret, algorithms=[algorithm])
    except jwt.InvalidTokenError:
        return None
    user_id = payload.get("user_id")
    return user_id if isinstance(user_id, str) and user_id else None


def get_agent_dialogue_service() -> AgentDialogueService:
    # Keep the current application-wide Engine pool; no ORM Session is created.
    from backend.routes import api

    return AgentDialogueService(AgentDialogueRepository(api.mysql_service))


async def _payload(request: Request, model):
    try:
        raw = await request.json()
        return model.model_validate(raw)
    except (ValidationError, ValueError, TypeError):
        return None


def _success(request: Request, detail):
    return JSONResponse(content=jsonable_encoder({"status": "success", "request_id": _request_id(request), "data": detail.model_dump()}))


def _handle_domain_error(request: Request, error: AgentDialogueError):
    return _error(
        request, error.code, error.message, error.status_code,
        retryable=error.retryable, unavailable=isinstance(error, AgentPersistenceUnavailable),
    )


@router.post("/api/v2/agent-design/sessions")
async def create_session(request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, CreateAgentSessionRequest)
    if payload is None:
        return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        return _success(request, get_agent_dialogue_service().create_session(user_id))
    except AgentDialogueError as error:
        return _handle_domain_error(request, error)


@router.get("/api/v2/agent-design/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try:
        return _success(request, get_agent_dialogue_service().get_session(session_id, user_id))
    except AgentDialogueError as error:
        return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/sessions/{session_id}/messages")
async def append_message(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, AppendAgentMessageRequest)
    if payload is None:
        return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        detail, _replayed = get_agent_dialogue_service().append_message(
            session_id, user_id, text=payload.text, client_turn_id=payload.client_turn_id,
            expected_status=payload.expected_status, expected_version=payload.expected_version,
        )
        return _success(request, detail)
    except AgentDialogueError as error:
        return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/sessions/{session_id}/decisions")
async def submit_decision(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, AgentDecisionRequest)
    if payload is None:
        return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        detail = get_agent_dialogue_service().submit_decision(
            session_id, user_id, decision_id=payload.decision_id, decision=payload.decision,
            expected_status=payload.expected_status, expected_version=payload.expected_version,
        )
        return _success(request, detail)
    except AgentDialogueError as error:
        return _handle_domain_error(request, error)
