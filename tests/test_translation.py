from copilot.translation import (
    TranslationSpec,
    TranslationVector,
    verify_translation,
)


def test_translation_compares_observables_not_registers():
    spec = TranslationSpec(
        source_isa="risc1",
        target_isa="risc2",
        source="mov $65\nout $1\nhalt",
        vectors=[TranslationVector("v1")],
    )
    result = verify_translation(spec, "mov $65\nout $1\nhalt")
    assert result["passed"] is True
    assert result["vectors"][0]["differences"] == {}


def test_translation_feedback_is_limited_to_differences():
    spec = TranslationSpec(
        source_isa="risc1",
        target_isa="risc2",
        source="mov $65\nout $1\nhalt",
        vectors=[TranslationVector("v1")],
    )
    result = verify_translation(spec, "mov $66\nout $1\nhalt")
    vector = result["vectors"][0]
    assert result["passed"] is False
    assert vector["vector_id"] == "v1"
    assert set(vector["differences"]) == {"output"}
    assert "registers" not in vector["differences"]


def test_translation_rejects_non_halting_target():
    spec = TranslationSpec(
        source_isa="risc1",
        target_isa="risc2",
        source="halt",
        vectors=[TranslationVector("v1", max_cycles=2)],
    )
    result = verify_translation(spec, "jmp 0")
    assert result["passed"] is False
    assert result["vectors"][0]["differences"]["halted"] == {
        "source": True, "target": False,
    }
