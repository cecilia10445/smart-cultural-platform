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
    AssistantTurnRequest,
    CreateAgentSessionRequest,
)
from backend.domain.agent_design_domain import (
    ApproveActionRequest, CreateActionRequest, CreateDesignTaskRequest,
    RejectActionRequest, SelectDesignTaskRequest,
)
from backend.services.agent_action_service import AgentActionService
from backend.services.agent_design_domain_repository import AgentDesignDomainRepository
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


def get_agent_action_service() -> AgentActionService:
    from backend.routes import api
    return AgentActionService(AgentDesignDomainRepository(api.mysql_service))


def get_agent_runtime_turn_service():
    """Build the opt-in Runtime without changing legacy generation providers."""
    from backend.agents.design_conversation import DesignConversationService, build_design_tool_registry
    from backend.agents.runtime import ToolExecutor
    from backend.agents.runtime.adapters import PydanticAIRuntimeEngine
    from backend.agents.runtime.providers import RuntimeProviderError, build_runtime_model
    from backend.services.agent_runtime_repository import AgentRuntimeRepository
    from backend.services.agent_runtime_turn_service import AgentRuntimeTurnService
    from backend.routes import api
    try:
        model = build_runtime_model()
    except RuntimeProviderError:
        return None
    repository = AgentRuntimeRepository(api.mysql_service)
    def state_reader(user_id: str, session_id: str):
        return repository.get_session(session_id, user_id)
    return AgentRuntimeTurnService(
        repository,
        DesignConversationService(PydanticAIRuntimeEngine(ToolExecutor(build_design_tool_registry()), model), state_reader,
                                  cultural_rag=api.get_cultural_rag_service()),
    )


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


@router.get("/api/v2/agent-design/sessions")
async def list_sessions(request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try:
        return JSONResponse(content=jsonable_encoder({
            "status": "success", "request_id": _request_id(request),
            "data": [item.model_dump() for item in get_agent_dialogue_service().list_sessions(user_id)],
        }))
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


@router.post("/api/v2/agent-design/sessions/{session_id}/assistant-turns")
async def assistant_turn(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, AssistantTurnRequest)
    if payload is None:
        return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    service = get_agent_runtime_turn_service()
    if service is None:
        return _error(request, "RUNTIME_PROVIDER_UNAVAILABLE", "Assistant runtime is not configured.", 503, unavailable=True)
    try:
        run, replayed = await service.run_turn(user_id, session_id, payload.content, payload.client_turn_id)
        display = service.repository.get_safe_run_display(session_id, user_id, run["id"])
        return JSONResponse(content=jsonable_encoder({"status": "success", "request_id": _request_id(request), "data": {"run": run, "display": display, "replayed": replayed}}))
    except AgentDialogueError as error:
        return _handle_domain_error(request, error)


@router.get("/api/v2/agent-design/sessions/{session_id}/assistant-turns/{run_id}")
async def get_assistant_turn(session_id: str, run_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id:
        return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    service = get_agent_runtime_turn_service()
    if service is None:
        return _error(request, "RUNTIME_PROVIDER_UNAVAILABLE", "Assistant runtime is not configured.", 503, unavailable=True)
    try:
        return JSONResponse(content=jsonable_encoder({"status": "success", "request_id": _request_id(request), "data": service.repository.get_safe_run_display(session_id, user_id, run_id)}))
    except AgentDialogueError as error:
        return _handle_domain_error(request, error)


def _action_success(request: Request, detail, *, replayed: bool = False):
    return JSONResponse(content=jsonable_encoder({"status": "success", "request_id": _request_id(request), "data": detail, "replayed": replayed}))


@router.get("/api/v2/agent-design/sessions/{session_id}/tasks")
async def list_design_tasks(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try:
        tasks = get_agent_action_service().repository.list_tasks(user_id, session_id)
        return _action_success(request, [item.model_dump() for item in tasks])
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/sessions/{session_id}/tasks")
async def create_design_task(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, CreateDesignTaskRequest)
    if payload is None: return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        repository = get_agent_action_service().repository
        task = repository.create_task(user_id, session_id, title=payload.title, client_task_id=payload.client_task_id)
        if payload.select:
            repository.select_active_task(user_id, session_id, task.id, expected_session_version=payload.expected_session_version)
        return _action_success(request, task.model_dump())
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.get("/api/v2/agent-design/sessions/{session_id}/tasks/{task_id}")
async def get_design_task(session_id: str, task_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try: return _action_success(request, get_agent_action_service().task_view(user_id, session_id, task_id).model_dump())
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/sessions/{session_id}/tasks/{task_id}/select")
async def select_design_task(session_id: str, task_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, SelectDesignTaskRequest)
    if payload is None: return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        task = get_agent_action_service().repository.select_active_task(user_id, session_id, task_id, expected_session_version=payload.expected_session_version)
        return _action_success(request, task.model_dump())
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.get("/api/v2/agent-design/sessions/{session_id}/available-actions")
async def get_available_design_actions(session_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try: return _action_success(request, get_agent_action_service().available(user_id, session_id))
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/sessions/{session_id}/tasks/{task_id}/actions")
async def request_design_action(session_id: str, task_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, CreateActionRequest)
    if payload is None: return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        detail, replayed = get_agent_action_service().request_action(user_id, session_id, task_id, action_type=payload.action_type,
            idempotency_key=payload.idempotency_key, source_runtime_run_id=payload.source_runtime_run_id,
            source_proposal_digest=payload.source_proposal_digest, expected_task_version=payload.expected_task_version)
        return _action_success(request, detail, replayed=replayed)
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.get("/api/v2/agent-design/sessions/{session_id}/tasks/{task_id}/actions")
async def list_design_actions(session_id: str, task_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try:
        service = get_agent_action_service()
        return _action_success(request, [service._safe_action(item) for item in service.repository.list_actions(user_id, session_id, task_id)])
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.get("/api/v2/agent-design/sessions/{session_id}/tasks/{task_id}/actions/{action_id}")
async def get_design_action(session_id: str, task_id: str, action_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    try:
        service = get_agent_action_service()
        return _action_success(request, service._safe_action(service.repository.get_action(action_id, user_id, session_id, task_id)))
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/actions/{action_id}/approve")
async def approve_design_action(action_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, ApproveActionRequest)
    if payload is None: return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        detail, replayed = get_agent_action_service().approve(user_id, action_id, expected_action_status=payload.expected_action_status,
            expected_task_version=payload.expected_task_version, idempotency_key=payload.idempotency_key, approval_snapshot=payload.approval_snapshot)
        return _action_success(request, detail, replayed=replayed)
    except AgentDialogueError as error: return _handle_domain_error(request, error)


@router.post("/api/v2/agent-design/actions/{action_id}/reject")
async def reject_design_action(action_id: str, request: Request):
    user_id = _authenticated_user_id(request)
    if not user_id: return _error(request, "AUTH_REQUIRED", "Please sign in before using agent design.", 401)
    payload = await _payload(request, RejectActionRequest)
    if payload is None: return _error(request, "INVALID_AGENT_REQUEST", "Request body is invalid.", 400)
    try:
        detail, replayed = get_agent_action_service().reject(user_id, action_id, idempotency_key=payload.idempotency_key, reason=payload.reason)
        return _action_success(request, detail, replayed=replayed)
    except AgentDialogueError as error: return _handle_domain_error(request, error)
