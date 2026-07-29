import asyncio
import json
from datetime import datetime
import jwt
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from backend.domain.agent_dialogue import (
    AgentDecisionNotSupported, AgentSessionDetailResponse, AgentSessionNotFound,
    AgentSessionStateConflict, AgentSessionStatus, project_agent_session_detail,
)


class RouteService:
    def __init__(self):
        self.owner, self.detail = "U1", self._detail("session-1", AgentSessionStatus.CREATED)

    @staticmethod
    def _detail(session_id, status):
        return AgentSessionDetailResponse(
            session_id=session_id, status=status, current_stage=status, revision_count=0,
            created_at="2026-07-30T12:00:00", updated_at="2026-07-30T12:00:00",
        )

    def create_session(self, user_id):
        self.owner, self.detail = user_id, self._detail("session-1", AgentSessionStatus.CREATED)
        return self.detail

    def get_session(self, session_id, user_id):
        if session_id != self.detail.session_id or user_id != self.owner:
            raise AgentSessionNotFound()
        return self.detail

    def append_message(self, session_id, user_id, **kwargs):
        self.get_session(session_id, user_id)
        if kwargs.get("expected_status") is AgentSessionStatus.WAITING_TEXT_FEEDBACK:
            raise AgentSessionStateConflict()
        self.detail = self._detail(session_id, AgentSessionStatus.EXTRACTING_BRIEF)
        return self.detail, False

    def submit_decision(self, session_id, user_id, **_kwargs):
        self.get_session(session_id, user_id)
        raise AgentDecisionNotSupported()


@pytest.fixture()
def agent_client(monkeypatch):
    from backend.routes.agent_dialogue import router
    import backend.routes.agent_dialogue as route_module

    service = RouteService()
    monkeypatch.setattr(route_module, "get_jwt_config", lambda: ("agent-route-test-secret", "HS256"))
    monkeypatch.setattr(route_module, "get_agent_dialogue_service", lambda: service)
    application = FastAPI()
    application.include_router(router)
    return application, service


def token():
    return jwt.encode({"user_id": "U1"}, "agent-route-test-secret", algorithm="HS256")


def build_request(method, path, payload=None, token_value=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    headers = [(b"content-type", b"application/json")]
    if token_value:
        headers.append((b"authorization", f"Bearer {token_value}".encode("ascii")))

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": method, "path": path, "headers": headers, "query_string": b""}, receive)


def response_json(response):
    return json.loads(response.body)


def test_routes_require_jwt_and_return_stable_success_envelope(agent_client):
    application, _service = agent_client
    from backend.routes.agent_dialogue import create_session

    assert any(route.path == "/api/v2/agent-design/sessions" for route in application.routes)
    denied = asyncio.run(create_session(build_request("POST", "/api/v2/agent-design/sessions", {})))
    assert denied.status_code == 401
    assert response_json(denied)["code"] == "AUTH_REQUIRED"
    response = asyncio.run(create_session(build_request("POST", "/api/v2/agent-design/sessions", {}, token())))

    body = response_json(response)
    assert response.status_code == 200
    assert body["status"] == "success" and isinstance(body["request_id"], str)
    assert set(body["data"]) == {
        "schema_version", "session_id", "status", "current_stage", "revision_count", "generation_log_id",
        "brief_summary", "product_design", "visual_direction", "final_result", "messages", "steps", "error",
        "created_at", "updated_at",
    }


def test_routes_hide_foreign_session_and_preserve_409_error_contract(agent_client):
    _application, service = agent_client
    from backend.routes.agent_dialogue import append_message, get_session, submit_decision

    authenticated = token()
    foreign = asyncio.run(get_session("not-owned", build_request("GET", "/api/v2/agent-design/sessions/not-owned", token_value=authenticated)))
    conflict = asyncio.run(append_message("session-1", build_request("POST", "/api/v2/agent-design/sessions/session-1/messages", {
        "client_turn_id": "t1", "text": "调整", "expected_status": "waiting_text_feedback",
    }, authenticated)))
    decision = asyncio.run(submit_decision("session-1", build_request("POST", "/api/v2/agent-design/sessions/session-1/decisions", {
        "decision_id": "d1", "decision": "confirm_brief", "expected_status": "created",
    }, authenticated)))

    assert foreign.status_code == 404 and response_json(foreign)["code"] == "AGENT_SESSION_NOT_FOUND"
    assert conflict.status_code == 409 and response_json(conflict)["code"] == "SESSION_STATE_CONFLICT"
    assert decision.status_code == 409 and response_json(decision)["code"] == "AGENT_DECISION_NOT_SUPPORTED"
    assert all(isinstance(response_json(item)["request_id"], str) for item in (foreign, conflict, decision))
    assert service.detail.status is AgentSessionStatus.CREATED


@pytest.mark.parametrize("status", [
    AgentSessionStatus.CREATED,
    AgentSessionStatus.WAITING_BRIEF_CONFIRMATION,
    AgentSessionStatus.WAITING_TEXT_FEEDBACK,
    AgentSessionStatus.WAITING_IMAGE_CONFIRMATION,
    AgentSessionStatus.COMPLETED,
    AgentSessionStatus.FAILED,
])
def test_detail_contract_has_stable_types_for_every_public_state(status):
    row = {
        "id": "session-1", "status": status.value, "current_stage": status.value, "text_revision_count": 0,
        "generation_log_id": None, "brief_json": None, "confirmed_text_json": None, "image_prompt_json": None,
        "error_json": {"code": "X", "retryable": False} if status is AgentSessionStatus.FAILED else None,
        "error_code": "X" if status is AgentSessionStatus.FAILED else None,
        "failure_stage": "generating_image" if status is AgentSessionStatus.FAILED else None,
        "created_at": datetime(2026, 7, 30, 12), "updated_at": datetime(2026, 7, 30, 12),
        "unexpected_database_column": {"provider_payload": "never returned"},
    }
    body = project_agent_session_detail(row, [], []).model_dump()

    assert set(body) == {
        "schema_version", "session_id", "status", "current_stage", "revision_count", "generation_log_id",
        "brief_summary", "product_design", "visual_direction", "final_result", "messages", "steps", "error",
        "created_at", "updated_at",
    }
    assert body["messages"] == [] and body["steps"] == [] and body["revision_count"] == 0
    assert body["brief_summary"] is None and body["product_design"] is None and body["visual_direction"] is None
    assert body["error"] is None if status is not AgentSessionStatus.FAILED else body["error"]["code"] == "X"
