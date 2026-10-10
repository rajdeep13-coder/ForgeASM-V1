from __future__ import annotations

import json

from copilot.gateway import ModelGateway, MockBackend


def test_mock_routing_and_response_shape(tmp_path):
    gateway = ModelGateway(
        backend=MockBackend([
            {"text": "OK", "usage": {"in": 1, "out": 1}},
            {"text": "hello", "usage": {"in": 4, "out": 2}},
        ]),
        telemetry_path=str(tmp_path / "telemetry.jsonl"),
    )
    capabilities = gateway.startup_check()
    result = gateway.generate([{"role": "user", "content": "hi"}])
    assert result["text"] == "hello"
    assert result["backend"] == "MOCK"
    assert result["usage"] == {"in": 4, "out": 2}
    assert capabilities.available is True


def test_text_protocol_fallback_validates_tool_schema(tmp_path):
    backend = MockBackend(
        [
            {"text": "OK"},
            {"text": json.dumps({"tool": "assemble_and_run", "args": {"assembly": "halt"}})},
        ],
        capabilities={
            "supports_images": False,
            "supports_tool_calling": False,
            "supports_json_schema": True,
        },
    )
    gateway = ModelGateway(backend=backend, telemetry_path=str(tmp_path / "telemetry.jsonl"))
    gateway.startup_check()
    result = gateway.generate(
        [{"role": "user", "content": "run"}],
        tools=[{
            "type": "function",
            "function": {
                "name": "assemble_and_run",
                "parameters": {
                    "type": "object",
                    "properties": {"assembly": {"type": "string"}},
                    "required": ["assembly"],
                    "additionalProperties": False,
                },
            },
        }],
    )
    assert result["tool_calls"] == [
        {"name": "assemble_and_run", "arguments": {"assembly": "halt"}}
    ]


def test_telemetry_math_and_jsonl_persistence(tmp_path):
    telemetry_path = tmp_path / "telemetry.jsonl"
    gateway = ModelGateway(
        backend=MockBackend([
            {"text": "OK"},
            {"text": "ok", "usage": {"in": 10, "out": 5}},
        ]),
        telemetry_path=str(telemetry_path),
    )
    gateway.startup_check()
    gateway.set_session_id("session-42")
    gateway.generate([{"role": "user", "content": "measure"}])
    record = gateway.telemetry()[0]
    assert record["session_id"] == "session-42"
    assert record["tokens_in"] == 10
    assert record["tokens_out"] == 5
    assert record["tokens_per_sec"] >= 0
    assert record["latency_ms"] >= 0
    assert record["bytes_off_device"] > 0
    persisted = json.loads(telemetry_path.read_text(encoding="utf-8").splitlines()[-1])
    assert persisted["tokens_per_sec"] == record["tokens_per_sec"]
