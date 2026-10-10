import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request

from copilot.agent import CopilotAgent
from copilot.explainer import explain_trace
from copilot.gateway import LocalBackend, ModelGateway
from copilot.tasks import TaskSpec


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_full_local_solve_and_explain_blocks_non_local(monkeypatch, tmp_path):
    requests = []
    responses = iter([
        {"models": [{"id": "gemma-local"}]},
        {"choices": [{"message": {"content": "OK"}}]},
        {"choices": [{"message": {"content": "image"}}]},
        {"choices": [{"message": {"tool_calls": [
            {"function": {"name": "ping", "arguments": "{}"}}
        ]}}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"tool_calls": [
            {"function": {"name": "submit", "arguments": json.dumps({"source": "halt"})}}
        ]}}]},
        {"choices": [{"message": {"content": json.dumps({
            "answer": "cycle 0 halted",
            "citations": [{"cycle": 0, "path": "halted", "value": True}],
        })}}]},
    ])

    def guarded_urlopen(request: Request, timeout=None):
        parsed = urlparse(request.full_url)
        requests.append(parsed)
        assert parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        return _Response(next(responses))

    monkeypatch.setenv("GEMMA_FAST_MODEL", "gemma-local")
    monkeypatch.setenv("GEMMA_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr("copilot.gateway.urlopen", guarded_urlopen)
    gateway = ModelGateway(telemetry_path=str(tmp_path / "telemetry.jsonl"))
    gateway.startup_check()
    task = TaskSpec("local", "local", "halt", "risc3", {}, {"halted": True})
    episode = CopilotAgent(gateway, episode_dir=str(tmp_path)).solve(task, max_repairs=0)
    assert episode["verdict"] == "passed"
    result = episode["results"][-1]
    explanation = explain_trace(
        gateway,
        {"trace": [{"cycle": 0, "diff": {"halted": True}}]},
        "why did the program halt?",
    )
    assert requests and all(item.hostname in {"127.0.0.1", "localhost", "::1"} for item in requests)
    assert result["halted"] is True
    assert explanation["citations"][0]["cycle"] == 0
