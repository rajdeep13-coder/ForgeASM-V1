import json

from copilot.explainer import explain_trace, validate_citations


def test_citations_require_existing_cycle_and_matching_value():
    trace = [{"cycle": 12, "diff": {"registers": {"R2": 7}}}]
    checked = validate_citations(trace, [
        {"cycle": 12, "path": "registers.R2", "value": 7},
        {"cycle": 99, "path": "registers.R2", "value": 7},
        {"cycle": 12, "path": "registers.R2", "value": 8},
    ])
    assert checked["verified"] == [{"cycle": 12, "path": "registers.R2", "value": 7}]
    assert len(checked["warnings"]) == 2


def test_explainer_uses_trace_only_and_returns_warnings():
    class Gateway:
        def __init__(self):
            self.messages = None

        def generate(self, messages, **kwargs):
            self.messages = messages
            return {"text": json.dumps({
                "answer": "R2 became 7 at cycle 12.",
                "citations": [{"cycle": 12, "path": "registers.R2", "value": 7}],
            })}

    gateway = Gateway()
    result = explain_trace(gateway, {
        "trace": [{"cycle": 12, "diff": {"registers": {"R2": 7}}}],
    }, "why does R2 hold 7?")
    assert result["citations"][0]["cycle"] == 12
    assert result["warnings"] == []
    assert '"registers"' in gateway.messages[1]["content"]


def test_explainer_warns_when_answer_omits_cited_cycle():
    class Gateway:
        def generate(self, messages, **kwargs):
            return {"text": json.dumps({
                "answer": "R2 became 7.",
                "citations": [{"cycle": 12, "path": "registers.R2", "value": 7}],
            })}

    result = explain_trace(
        Gateway(),
        {"trace": [{"cycle": 12, "diff": {"registers": {"R2": 7}}}]},
        "why?",
    )
    assert any("does not state verified cycle 12" in warning for warning in result["warnings"])
