from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from api.copilot.agent import run_agent
from api.copilot.provider import ModelResponse, ToolCall
from api.copilot.tasks import load_task
from api.main import app


@dataclass
class FakeProvider:
    responses: list[ModelResponse]

    def complete(self, messages, tools):
        return self.responses.pop(0)


def test_checker_is_deterministic_and_server_owned():
    task = load_task("risc3_halt")
    provider = FakeProvider([
        ModelResponse("", [ToolCall("assemble_and_run", {"assembly": "halt"})]),
    ])
    result = run_agent(task, provider=provider)
    assert result["status"] == "passed"
    assert result["final"]["checker"] == {"passed": True, "failures": []}


def test_agent_repairs_after_failed_attempt():
    task = load_task("risc3_halt")
    provider = FakeProvider([
        ModelResponse("", [ToolCall("assemble_and_run", {"assembly": "nop"})]),
        ModelResponse("", [ToolCall("assemble_and_run", {"assembly": "halt"})]),
    ])
    result = run_agent(task, provider=provider)
    assert result["status"] == "passed"
    assert len(result["attempts"]) == 2


def test_copilot_route_reports_missing_provider_configuration(monkeypatch):
    monkeypatch.delenv("GEMMA_MODEL", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/copilot/run", json={"task_id": "risc3_halt"})
    assert response.status_code == 503
    assert response.json()["code"] == "COPILOT_NOT_CONFIGURED"

