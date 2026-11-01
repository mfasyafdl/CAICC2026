"""Tests for the backend switch, the preview backend, and the real-core path.

Owned by Person 2. The whole test process runs with ``VISITPREP_PREVIEW=1``
(see conftest.py), so the preview backend is exercised directly here. The
real-core (LLM) path is exercised with a faked HTTP transport so no network is
touched, and the "preview off" routing is verified in a fresh subprocess.
"""

import json
import os
import subprocess
import sys

from core import fixtures
from core import llm as llm_module
from core.llm import LLMConfig

from ui import backend
from ui import fixture_backend as fb


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_preview_mode_is_enabled_for_these_tests():
    assert backend.preview_mode() is True


def test_rule_based_calls_are_always_real_core():
    import core.interview
    import core.redflag

    assert backend.choose_follow_up_question is not None
    assert backend.check_alerts is core.redflag.check_alerts
    assert backend.scan_text is core.redflag.scan_text
    assert backend.max_follow_up_questions == core.interview.MAX_DISPLAYED_QUESTIONS


def test_extract_record_returns_a_fictional_fixture_verbatim():
    record = fb.extract_record("I have crushing chest pain", {"patient_age": 99})
    assert record == fixtures.FIXTURE_FEVER_ADULT
    assert record.complaint == fixtures.FIXTURE_FEVER_ADULT.complaint
    assert record.patient_name == "Alex D."


def test_merge_answer_returns_record_unchanged():
    record = fixtures.FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER
    merged = fb.merge_answer(record, "Preview: any medicines?", "aspirin")
    assert merged == record
    assert merged is not record


def test_generate_summary_returns_placeholder_only():
    summary = fb.generate_summary(fixtures.FIXTURE_RASH_WITH_ALLERGY, [])
    assert "Preview:" in summary.doctor_card
    assert "Preview:" in summary.patient_script
    assert all("Preview:" in q for q in summary.priority_questions)


def test_preview_off_imports_without_crash_and_routes_to_core():
    code = (
        "import os\n"
        "os.environ.pop('VISITPREP_PREVIEW', None)\n"
        "from ui import backend\n"
        "import core.extract as e\n"
        "import core.interview as i\n"
        "import core.summarize as s\n"
        "assert backend.preview_mode() is False\n"
        "assert backend.extract_record is e.extract_record\n"
        "assert backend.merge_answer is i.merge_answer\n"
        "assert backend.generate_summary is s.generate_summary\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_project_root(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --- real-core path (LLM transport faked; no network) -----------------------

_RECORD = {
    "patient_name": None,
    "patient_age": None,
    "patient_age_text": None,
    "patient_sex": None,
    "reporting_on_behalf": None,
    "reporter_relationship": None,
    "complaint": "I have a cough",
    "symptoms": ["a cough"],
    "onset": None,
    "duration": None,
    "duration_days": None,
    "severity": None,
    "severity_note": None,
    "medicines": [],
    "medicines_denied": None,
    "allergies": [],
    "allergies_denied": None,
    "medical_history": [],
    "medical_history_denied": None,
    "concerns": [],
    "missing_information": [],
}

_MERGED = dict(_RECORD, severity="mild")

_SUMMARY = {
    "doctor_card": (
        "Patient: not provided. Complaint: I have a cough. Symptoms: a cough. "
        "Onset & duration: not provided. Severity: mild. Medicines: not "
        "provided. Allergies: not provided. Medical history: not provided. "
        "Patient's concerns: not provided. Not provided: age, sex."
    ),
    "patient_script": (
        "I have had a cough and I wanted to tell you about it today. I can "
        "describe how it feels and how long it has been going on so that we "
        "can decide together what to do next and whether any tests are needed."
    ),
    "priority_questions": ["What could be causing my cough?"],
}

CFG = LLMConfig(api_key="fake-key", model="zai-org/GLM-5.2")


def _body(obj) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": json.dumps(obj)}}]}
    ).encode("utf-8")


class _FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, url, payload, headers, timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_real_core_path_runs_end_to_end_without_network(monkeypatch):
    from core.extract import extract_record
    from core.interview import choose_follow_up_question, merge_answer
    from core.redflag import check_alerts
    from core.summarize import generate_summary

    transport = _FakeTransport(
        [(200, _body(_RECORD)), (200, _body(_MERGED)), (200, _body(_SUMMARY))]
    )
    monkeypatch.setattr(llm_module, "_http_post", transport)
    monkeypatch.setattr(llm_module, "_sleep", lambda s: None)

    record = extract_record("I have a cough", config=CFG)
    assert record.complaint == "I have a cough"
    assert record.severity is None

    question = choose_follow_up_question(record, [], [])
    assert question is not None and "severe" in question.lower()

    merged = merge_answer(record, question, "mild", config=CFG)
    assert merged.severity == "mild"
    assert merged.complaint == "I have a cough"

    assert check_alerts(merged) == []

    summary = generate_summary(merged, [], config=CFG)
    assert summary.doctor_card
    assert summary.patient_script
    assert 1 <= len(summary.priority_questions) <= 3
    assert transport.calls == 3