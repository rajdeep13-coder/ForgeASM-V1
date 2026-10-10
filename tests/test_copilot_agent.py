from __future__ import annotations

import json

from copilot.agent import CopilotAgent
from copilot.spec import build_isa_card
from copilot.tasks import TaskSpec
from copilot.gateway import MockBackend, ModelGateway


def _task(expected=None):
    return TaskSpec(
        task_id="agent-test",
        title="halt",
        nl_description="Halt immediately.",
        isa_applicability="risc3",
        init={},
        expected=expected or {"halted": True},
    )


def _agent(tmp_path, responses):
    gateway = ModelGateway(
        backend=MockBackend([{"text": "probe"}, *responses], capabilities={
            "supports_images": False, "supports_tool_calling": True,
            "supports_json_schema": True,
        }),
        telemetry_path=str(tmp_path / "telemetry.jsonl"),
    )
    gateway.startup_check()
    return CopilotAgent(gateway, episode_dir=str(tmp_path / "episodes"))


def test_card_is_definition_backed_and_budgeted():
    card = build_isa_card("risc3", token_budget=1200)
    assert card["token_count"] <= 1200
    assert "R00" in card["text"]
    assert "halt" in card["text"]
    assert card["verified_examples"] >= 2


def test_agent_repairs_assembler_error_and_persists_episode(tmp_path):
    agent = _agent(tmp_path, [
        {"tool_calls": [{"name": "assemble", "arguments": {"isa": "risc3", "source": "hallt"}}]},
        {"tool_calls": [{"name": "submit", "arguments": {"source": "halt"}}]},
    ])
    episode = agent.solve(_task())
    assert episode["verdict"] == "passed"
    assert episode["results"][0]["errors"][0]["kind"] == "unknown_mnemonic"
    saved = list((tmp_path / "episodes").glob("*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["verdict"] == "passed"


def test_agent_wrong_answer_and_timeout_are_checker_visible(tmp_path):
    agent = _agent(tmp_path, [
        {"tool_calls": [{"name": "run", "arguments": {
            "isa": "risc3", "memory_arch": "neumann", "source": "nop",
            "init": {}, "max_cycles": 1,
        }}]},
        {"tool_calls": [{"name": "run", "arguments": {
            "isa": "risc3", "memory_arch": "neumann", "source": "jmp $0",
            "init": {}, "max_cycles": 2,
        }}]},
    ])
    episode = agent.solve(_task({"halted": True}), max_repairs=1)
    assert episode["verdict"] == "failed"
    assert any(item.get("timed_out") for item in episode["results"])
    assert any(item.get("checker", {}).get("failures") for item in episode["results"])


def test_agent_rejects_hallucinated_tool_and_does_not_change_checker(tmp_path):
    agent = _agent(tmp_path, [
        {"tool_calls": [{"name": "not_a_tool", "arguments": {}}]},
    ])
    episode = agent.solve(_task({"halted": True}), max_repairs=0)
    assert episode["verdict"] == "failed"
    assert episode["results"][0]["ok"] is False
