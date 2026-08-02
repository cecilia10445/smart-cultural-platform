import asyncio
import json
from datetime import datetime
import jwt
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from backend.domain.agent_dialogue import (
    AgentDecisionNotSupported, AgentSessionDetailResponse, AgentSessionNotFound,
    AgentPersistenceUnavailable, AgentSessionStateConflict, AgentSessionStatus, project_agent_session_detail,
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


def test_persisted_legacy_runtime_output_projects_to_a_natural_reply():
    detail = project_agent_session_detail(
        {"id": "s1", "status": "created", "current_stage": "created"},
        [{"id": "m1", "sequence_no": 1, "role": "assistant", "message_type": "runtime_result",
          "content_text": "旧版摘要", "created_at": datetime(2026, 8, 1),
          "content_json": json.dumps({"runtime_run_id": "run-legacy-1", "output": {"result": {"kind": "propose_brief", "brief": {"product_type": "杯垫"},
              "summary": "旧版初步方案", "assumptions": [], "evidence_source_ids": [], "used_skill_ids": []}}})}],
        [],
    )
    reply = detail.messages[0].structured_output
    assert reply["message"] == "旧版初步方案"
    assert reply["artifact_proposal"]["kind"] == "brief"
    assert reply["output_origin"] == "legacy_projection"
    assert detail.messages[0].runtime_run_id == "run-legacy-1"


def test_runtime_failure_projection_is_allow_listed_and_does_not_return_provider_detail():
    detail = project_agent_session_detail(
        {"id": "s1", "status": "created", "current_stage": "created"},
        [{"id": "m1", "sequence_no": 1, "role": "assistant", "message_type": "runtime_result",
          "content_text": "runtime_result", "created_at": datetime(2026, 8, 2),
          "content_json": {"runtime_failure": {"code": "RUNTIME_MODEL_TIMEOUT", "retryable": True,
                                                   "provider_body": "must not leave persistence"}}}],
        [],
    )

    assert detail.messages[0].runtime_failure == {"code": "RUNTIME_MODEL_TIMEOUT", "retryable": True}


def test_agent_generation_history_route_is_owner_scoped_and_read_only(agent_client, monkeypatch):
    application, _service = agent_client
    import backend.routes.agent_dialogue as route_module

    class HistoryService:
        def generation_history_detail(self, user_id, generation_log_id):
            assert user_id == "U1" and generation_log_id == 73
            return {"kind": "agent_artifact_image", "read_only": True, "generation_log": {"id": 73}}

    monkeypatch.setattr(route_module, "get_agent_action_service", lambda: HistoryService())
    from backend.routes.agent_dialogue import get_agent_generation_history

    denied = asyncio.run(get_agent_generation_history(73, build_request("GET", "/api/v2/agent-design/history/generation-logs/73")))
    assert denied.status_code == 401
    success = asyncio.run(get_agent_generation_history(73, build_request("GET", "/api/v2/agent-design/history/generation-logs/73", token_value=token())))
    body = response_json(success)
    assert success.status_code == 200
    assert body["status"] == "success" and body["data"]["read_only"] is True


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


def test_persistence_error_uses_its_safe_default_message():
    error = AgentPersistenceUnavailable()

    assert error.code == "AGENT_PERSISTENCE_UNAVAILABLE"
    assert error.message == "Agent session data service is temporarily unavailable."


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


def test_product_design_projection_allow_lists_complete_agent_text_contract():
    row = {
        "id": "session-1", "status": "waiting_text_feedback", "current_stage": "waiting_text_feedback", "text_revision_count": 1,
        "generation_log_id": None, "brief_json": None, "image_prompt_json": None, "error_json": None, "error_code": None,
        "failure_stage": None, "created_at": datetime(2026, 7, 30, 12), "updated_at": datetime(2026, 7, 30, 12),
        "confirmed_text_json": {"product_name": "环光灯", "design_concept": "现代", "cultural_translation": "环形转译",
            "structure": "环形结构", "materials": "磨砂金属", "color_plan": "暖白", "usage_scene": "桌面",
            "selling_points": ["轻巧"], "creative_origin": "纹样", "factual_background": "创意解读",
            "evidence_status": "creative_only", "evidence": [], "used_source_ids": [], "selected_text_skill": "retail-product-copy",
            "revision_summary": "调整材质", "provider_payload": {"never": "leak"}},
    }
    design = project_agent_session_detail(row, [], []).product_design.model_dump()
    assert design == {
        "product_name": "环光灯", "design_concept": "现代", "cultural_translation": "环形转译", "structure": "环形结构",
        "materials": "磨砂金属", "color_plan": "暖白", "usage_scene": "桌面", "selling_points": ["轻巧"],
        "creative_origin": "纹样", "factual_background": "创意解读", "evidence_status": "creative_only", "evidence": [],
        "used_source_ids": [], "selected_text_skill": "retail-product-copy", "revision_summary": "调整材质",
    }


def test_visual_direction_projection_never_leaks_prompt_payload():
    row = {"id": "session-1", "status": "waiting_image_confirmation", "current_stage": "waiting_image_confirmation",
           "text_revision_count": 0, "generation_log_id": None, "brief_json": None, "confirmed_text_json": None,
           "error_json": None, "error_code": None, "failure_stage": None, "created_at": datetime(2026, 7, 30, 12), "updated_at": datetime(2026, 7, 30, 12),
           "image_prompt_json": {"positive_prompt": "private prompt", "negative_prompt": "private negative", "required_constraints": ["完整产品"],
               "product_form": "环形结构", "materials": "磨砂金属", "color_plan": "暖白", "composition": "主视图", "scene": "桌面",
               "avoid": ["人物"], "presentation_mode": "single_hero", "selected_visual_skill": "commercial-product-presentation",
               "evidence_source_ids": ["met-1"], "user_facing_direction": "现代产品主视图", "provider_payload": {"secret": "never"}}}
    visual = project_agent_session_detail(row, [], []).visual_direction.model_dump()
    assert visual["summary"] == "现代产品主视图" and visual["materials"] == "磨砂金属"
    assert "positive_prompt" not in visual and "negative_prompt" not in visual and "provider_payload" not in visual
