import asyncio

from backend.agents.runtime import AgentRunResult, AgentRunStatus, RuntimeUsage
from backend.services.agent_runtime_turn_service import AgentRuntimeTurnService


class FakeRepository:
    def __init__(self):
        self.runs, self.messages, self.completed = {}, [], 0

    def create_or_get_run(self, session_id, user_id, client_turn_id, agent_name):
        key = (user_id, session_id, client_turn_id)
        if key in self.runs:
            return self.runs[key], True
        run = {"id": "run-1", "user_id": user_id, "session_id": session_id, "client_turn_id": client_turn_id, "status": "running", "agent_name": agent_name}
        self.runs[key] = run
        return run, False

    def complete_run(self, run, result, user_content, assistant_text, assistant_json):
        self.completed += 1
        run.update(status=result.status.value, final_output_json=result.final_output, model_request_count=result.usage.model_requests, tool_call_count=result.usage.requested_tool_calls)
        self.messages.extend([user_content, assistant_text])
        return run


class FakeDesignService:
    def __init__(self): self.calls = 0
    async def run_turn(self, *_args):
        self.calls += 1
        return AgentRunResult(run_id="runtime", status=AgentRunStatus.COMPLETED,
                              final_output={"result": {"kind": "direct_answer", "answer": "safe"}}, usage=RuntimeUsage(model_requests=1))


def test_runtime_turn_service_persists_once_and_replays_by_client_turn_id():
    repository, design = FakeRepository(), FakeDesignService()
    service = AgentRuntimeTurnService(repository, design)
    first, replayed = asyncio.run(service.run_turn("owner", "session", "hello", "turn"))
    second, replayed_second = asyncio.run(service.run_turn("owner", "session", "hello", "turn"))
    assert first["id"] == second["id"] == "run-1"
    assert not replayed and replayed_second
    assert design.calls == 1 and repository.completed == 1 and repository.messages == ["hello", "safe"]
