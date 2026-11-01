"""Tests for the UI helpers and the actual event handlers.

Owned by Person 2. The event handlers are reached through ``demo.fns`` (each
``BlockFunction`` exposes ``.fn``), so these tests exercise the real wiring used
by the running app, not copies.
"""

import gradio as gr

from core.schema import Alert, Medicine
from ui import components
from ui.flow import (
    build_interface,
    list_from_text,
    list_to_text,
    medicines_from_text,
    medicines_to_text,
)
from ui.state import commit_if_current, new_state
from ui.welcome import build_welcome

_UNSET = object()


def _reporting_label(value):
    if value is True:
        return "Someone else"
    if value is False:
        return "Myself"
    return "Not answered"


def _confirm_args(record, *, age=_UNSET, reporting=_UNSET):
    return [
        record["complaint"],
        "\n".join(record["symptoms"]),
        record["onset"],
        record["duration"],
        record["severity"] or "",
        record["severity_note"] or "",
        "",
        record["medicines_denied"] is True,
        "",
        record["allergies_denied"] is True,
        "\n".join(record["medical_history"]),
        record["medical_history_denied"] is True,
        "\n".join(record["concerns"]),
        record["patient_age"] if age is _UNSET else age,
        record["patient_sex"] or "",
        _reporting_label(record["reporting_on_behalf"]) if reporting is _UNSET else reporting,
        record["reporter_relationship"] or "",
    ]


def test_build_welcome_renders_into_blocks():
    with gr.Blocks() as demo:
        build_welcome()
    assert demo is not None


def test_build_interface_renders_into_blocks():
    with gr.Blocks() as demo:
        build_interface()
    assert demo is not None


def test_list_round_trip():
    assert list_from_text("a\n\nb\n") == ["a", "b"]
    assert list_to_text(["a", "b"]) == "a\nb"
    assert list_from_text("") == []


def test_medicines_round_trip():
    medicines = [
        Medicine(name="paracetamol", medicine_type="over-the-counter", dose="one tablet"),
        Medicine(name="ginger tea", medicine_type="herbal", notes="for colds"),
    ]
    text = medicines_to_text(medicines)
    restored = medicines_from_text(text)
    assert restored[0].name == "paracetamol"
    assert restored[0].medicine_type == "over-the-counter"
    assert restored[0].dose == "one tablet"
    assert restored[1].name == "ginger tea"
    assert restored[1].medicine_type == "herbal"
    assert restored[1].notes == "for colds"


def test_medicines_invalid_type_falls_back_to_unknown():
    medicines = medicines_from_text("mystery drug | not-a-real-type")
    assert medicines[0].medicine_type == "unknown"


def test_medicines_ignores_blank_lines():
    assert medicines_from_text("\n\n") == []


def test_start_extracts_a_record(handlers):
    state = handlers["on_start"](None, "a dry cough", None, "")[0]
    assert state["record"] is not None
    assert state["step"] in (2, 3)


def test_answer_skip_finish_confirm_flow(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER")[0]
    assert state["step"] == 2 and state["question"]

    state = handlers["on_answer"](state, "no medicines, only honey tea")[0]
    assert len(state["asked"]) == 1

    state = handlers["on_skip"](state)[0]
    assert len(state["skipped"]) == 1

    state = handlers["on_finish"](state)[0]
    assert state["step"] == 3

    state = handlers["on_confirm"](state, *_confirm_args(state["record"]))[0]
    assert state["step"] == 4
    assert state["summary"] and state["summary_rev"] == state["rev"]


def test_five_question_cap_covers_skips(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_EMPTY_RECORD")[0]
    assert state["step"] == 2
    for _ in range(5):
        state = handlers["on_skip"](state)[0]
    assert state["step"] == 3
    assert len(state["skipped"]) == 5
    assert len(state["asked"]) == 0


def test_five_question_cap_counts_asked_and_skipped(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_EMPTY_RECORD")[0]
    for _ in range(3):
        state = handlers["on_answer"](state, "mild")[0]
    for _ in range(2):
        state = handlers["on_skip"](state)[0]
    assert state["step"] == 3
    assert len(state["asked"]) + len(state["skipped"]) == 5


def test_back_from_summary_invalidates(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER")[0]
    state = handlers["on_finish"](state)[0]
    state = handlers["on_confirm"](state, *_confirm_args(state["record"]))[0]
    assert state["step"] == 4 and state["summary"]

    state = handlers["on_back_from_output"](state)[0]
    assert state["step"] == 3
    assert state["summary"] is None
    assert state["summary_rev"] == -1


def test_reset_clears_state(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_RASH_WITH_ALLERGY")[0]
    state = handlers["on_reset"](state)[0]
    assert state["step"] == 1
    assert state["record"] is None
    assert state["asked"] == []
    assert state["skipped"] == []
    assert state["summary"] is None


def test_age_clearing_sets_both_age_fields_null(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER")[0]
    state = handlers["on_finish"](state)[0]
    state = handlers["on_confirm"](state, *_confirm_args(state["record"], age=None))[0]
    assert state["record"]["patient_age"] is None
    assert state["record"]["patient_age_text"] is None


def test_age_unchanged_keeps_original_wording(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER")[0]
    record = state["record"]
    assert record["patient_age"] == 7 and record["patient_age_text"] == "7 years old"
    state = handlers["on_finish"](state)[0]
    state = handlers["on_confirm"](state, *_confirm_args(state["record"], age=7))[0]
    assert state["record"]["patient_age"] == 7
    assert state["record"]["patient_age_text"] == "7 years old"


def test_reporting_on_behalf_stays_null_when_not_answered(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER")[0]
    state = handlers["on_finish"](state)[0]
    state = handlers["on_confirm"](
        state, *_confirm_args(state["record"], reporting="Not answered")
    )[0]
    assert state["record"]["reporting_on_behalf"] is None


def test_step_guards_ignore_clicks_from_wrong_step(handlers):
    fresh = new_state()
    out = handlers["on_answer"](fresh, "hello")
    assert out[0]["step"] == 1 and out[0]["record"] is None
    out = handlers["on_confirm"](fresh, *_confirm_args({
        "complaint": "x", "symptoms": [], "onset": None, "duration": None,
        "severity": None, "severity_note": None, "medicines": [],
        "medicines_denied": None, "allergies": [], "allergies_denied": None,
        "medical_history": [], "medical_history_denied": None, "concerns": [],
        "patient_age": None, "patient_sex": None,
        "reporting_on_behalf": None, "reporter_relationship": None,
    }))
    assert out[0]["step"] == 1


def test_late_confirm_result_is_dropped_after_reset(handlers):
    state = handlers["on_load_fixture"](None, "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER")[0]
    state = handlers["on_finish"](state)[0]
    captured = state["token"]

    reset_state = handlers["on_reset"](state)[0]
    assert reset_state["record"] is None and reset_state["step"] == 1
    assert reset_state["token"] > captured

    late = dict(reset_state)
    late.update({"step": 4, "record": state["record"], "summary": {"doctor_card": "late"}})
    final = commit_if_current(reset_state, captured, late)
    assert final is reset_state
    assert final["step"] == 1 and final["record"] is None


def test_patient_text_is_escaped_in_every_html_output():
    for malicious in ["<script>alert(1)</script>", "<img src=x onerror=alert(2)>"]:
        assert "<script>" not in components.summary_box_html(malicious)
        assert "<img" not in components.summary_box_html(malicious)
        assert "<script>" not in components.priority_list_html([malicious])
        assert "<img" not in components.question_box_html(malicious)
        assert "<script>" not in components.alerts_html(
            [Alert(code="x", message=malicious, level="attention")]
        )
    assert "&lt;script&gt;" in components.summary_box_html("<script>alert(1)</script>")
    assert "&lt;img" in components.summary_box_html("<img src=x onerror=y>")