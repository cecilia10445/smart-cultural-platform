import asyncio
import json
import jwt
from starlette.requests import Request

from backend.domain.agent_dialogue import AgentSessionNotFound


class FakeTurns:
    def __init__(self): self.calls = 0; self.run = {"id": "run-1", "status": "completed"}
    async def run_turn(self, user, session, content, turn):
        if user != "U1" or session != "s1": raise AgentSessionNotFound()
        self.calls += 1
        return self.run, self.calls > 1
    @property
    def repository(self): return self
    def get_run(self, session, user, run):
        if (session, user, run) != ("s1", "U1", "run-1"): raise AgentSessionNotFound()
        return self.run
    def get_safe_run_display(self, session, user, run):
        if (session, user, run) != ("s1", "U1", "run-1"): raise AgentSessionNotFound()
        return {"id": "run-1", "status": "completed", "output": {"message": "ok", "intent": "general_answer", "suggestions": [], "artifact_proposal": None, "business_action": None, "output_origin": "provider"}, "safe_tool_events": [], "context_metadata": {}, "rag": {"status": None, "summary": None}}


def request(path, payload=None, owner="U1"):
    body = json.dumps(payload).encode() if payload is not None else b""
    headers = [(b"content-type", b"application/json"), (b"authorization", f"Bearer {jwt.encode({'user_id': owner}, 'secret', algorithm='HS256')}".encode())]
    async def receive(): return {"type": "http.request", "body": body, "more_body": False}
    return Request({"type": "http", "method": "POST", "path": path, "headers": headers, "query_string": b""}, receive)


def body(response): return json.loads(response.body)


def test_assistant_turn_route_is_owner_scoped_and_delegates_to_injected_service(monkeypatch):
    import backend.routes.agent_dialogue as routes
    service = FakeTurns()
    monkeypatch.setattr(routes, "get_jwt_config", lambda: ("secret", "HS256"))
    monkeypatch.setattr(routes, "get_agent_runtime_turn_service", lambda: service)
    first = asyncio.run(routes.assistant_turn("s1", request("/", {"content": "hello", "client_turn_id": "turn"})))
    replay = asyncio.run(routes.assistant_turn("s1", request("/", {"content": "hello", "client_turn_id": "turn"})))
    foreign = asyncio.run(routes.assistant_turn("s1", request("/", {"content": "hello", "client_turn_id": "turn"}, "other")))
    read = asyncio.run(routes.get_assistant_turn("s1", "run-1", request("/")))
    assert body(first)["data"]["run"]["id"] == "run-1"
    assert body(first)["data"]["display"]["output"]["message"] == "ok"
    assert body(replay)["data"]["replayed"] is True
    assert foreign.status_code == 404 and body(read)["data"]["id"] == "run-1"
