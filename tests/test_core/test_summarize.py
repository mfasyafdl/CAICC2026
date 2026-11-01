"""Tests for core.summarize (shape, validation, failure safety).

Owned by Person 1. Transport faked — no network.
"""

import json
import urllib.error

import pytest

from core import llm
from core.fixtures import FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER, FIXTURE_FEVER_ADULT
from core.llm import LLMConfig, LLMNetworkError, LLMResponseError
from core.redflag import check_alerts
from core.schema import QuestionAnswer
from core.summarize import generate_summary

FAKE_KEY = "ms-fake-key-do-not-use"
CFG = LLMConfig(api_key=FAKE_KEY, model="zai-org/GLM-5.2")

SCRIPT = ("I would like to tell you that I have had a fever and headaches since "
          "yesterday afternoon, and I feel weak, although I can still work. ") * 3


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, url, payload, headers, timeout):
        self.calls.append({"payload": payload, "headers": headers})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _install(monkeypatch, outcomes):
    transport = FakeTransport(outcomes)
    monkeypatch.setattr(llm, "_http_post", transport)
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    return transport


def _ok(payload: dict) -> tuple[int, bytes]:
    return 200, json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": json.dumps(payload)}}]}
    ).encode("utf-8")


def _valid_payload():
    return {
        "doctor_card": (
            "Patient: Alex D., 34, female. Complaint: I feel feverish and my head "
            "has been hurting since yesterday. Symptoms: fever, headache, chills. "
            "Medicines: paracetamol (over-the-counter); ginger and honey tea (herbal). "
            "Allergies: none reported. Patient's concerns (patient's own words): "
            "\"Will I need a test?\" \"Can I keep working?\" Not provided: medical history."
        ),
        "patient_script": SCRIPT,
        "priority_questions": [
            "Will I need a test?",
            "Can I keep working?",
            "What should I watch out for?",
        ],
    }


def test_summary_shape_and_limits(monkeypatch):
    _install(monkeypatch, [_ok(_valid_payload())])
    asked = [QuestionAnswer("How old are you?", "34")]
    summary = generate_summary(FIXTURE_FEVER_ADULT, asked, config=CFG, max_retries=0)
    assert summary.doctor_card.startswith("Patient:")
    assert 20 <= len(summary.patient_script.split()) <= 260
    assert 1 <= len(summary.priority_questions) <= 3
    # patient concerns preserved verbatim and labeled as the patient's words
    assert "Will I need a test?" in summary.doctor_card
    assert "patient's own words" in summary.doctor_card.lower()


def test_summary_rejects_degenerate_script(monkeypatch):
    bad = _valid_payload()
    bad["patient_script"] = "Too short."
    transport = _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError):
        generate_summary(FIXTURE_FEVER_ADULT, [], config=CFG, max_retries=0, max_repairs=1)
    assert len(transport.calls) == 2  # bounded repair


def test_summary_rejects_too_many_priority_questions(monkeypatch):
    bad = _valid_payload()
    bad["priority_questions"] = ["q1", "q2", "q3", "q4"]
    _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError):
        generate_summary(FIXTURE_FEVER_ADULT, [], config=CFG, max_retries=0, max_repairs=1)


def test_summary_api_error_is_safe(monkeypatch):
    _install(monkeypatch, [urllib.error.URLError("dns fail")])
    with pytest.raises(LLMNetworkError) as exc:
        generate_summary(FIXTURE_FEVER_ADULT, [], config=CFG, max_retries=0)
    assert FAKE_KEY not in str(exc.value)
    assert "feel feverish" not in str(exc.value)


def test_model_cannot_remove_rule_generated_alerts():
    import copy
    from dataclasses import fields

    from core.schema import SummaryOutput

    record = copy.deepcopy(FIXTURE_FEVER_ADULT)
    record.complaint = "I feel feverish and I also have chest pain."
    alerts = check_alerts(record)
    assert any(a.code == "chest_pain" for a in alerts)
    # the summary output has no alerts field: alerts exist only via core.redflag,
    # so the model can never remove (or add) a rule-generated alert
    assert not any(f.name == "alerts" for f in fields(SummaryOutput))


# --- record-aware regression tests (issue fixes) -----------------------------


def _payload(card, script=None, questions=None):
    return {
        "doctor_card": card,
        "patient_script": script if script is not None else SCRIPT,
        "priority_questions": questions
        if questions is not None
        else ["Could this be related to his asthma as a baby?"],
    }


def test_summary_rejects_invented_allergy_denial_for_unknown(monkeypatch):
    """Allergies unknown (denied null) must NOT be written as 'none'."""
    # child-cough fixture: allergies_denied is None (unknown)
    bad = _payload(
        "Patient: Sam, 7, male. Complaint: bad cough. Symptoms: cough, worse at "
        "night. Medicines: Not provided. Allergies: none. Not provided: medicines."
    )
    transport = _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError):
        generate_summary(
            FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER, [], config=CFG, max_retries=0, max_repairs=1
        )
    assert len(transport.calls) == 2  # bounded repair


def test_summary_rejects_completeness_claim(monkeypatch):
    """'no other symptoms' invents a negative; mentioning one is not completeness."""
    bad = _payload(
        "Patient: Alex D., 34, female. Complaint: fever. Symptoms: fever, "
        "headache; no other symptoms. Medicines: paracetamol. Allergies: none "
        "— patient confirms no allergies."
    )
    transport = _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError):
        generate_summary(FIXTURE_FEVER_ADULT, [], config=CFG, max_retries=0, max_repairs=1)
    assert len(transport.calls) == 2


def test_summary_requires_not_provided_label_for_unknown(monkeypatch):
    """Unknown fields must be labeled 'Not provided', not silently omitted."""
    # child-cough fixture has unknown medicines + allergies; card avoids denial
    # phrases but never says "not provided".
    bad = _payload(
        "Patient: Sam, 7, male. Complaint: bad cough. Symptoms: cough, worse at "
        "night. Medicines: not mentioned. Allergies: not mentioned."
    )
    transport = _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError):
        generate_summary(
            FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER, [], config=CFG, max_retries=0, max_repairs=1
        )
    assert len(transport.calls) == 2


def test_summary_accepts_confirmed_denial_wording(monkeypatch):
    """When *_denied is true, a clear 'none — patient confirms' is allowed."""
    good = _payload(
        "Patient: Alex D., 34, female. Complaint: fever and headache. Symptoms: "
        "fever, headache, chills. Medicines: paracetamol; ginger and honey tea. "
        "Allergies: none — patient confirms no allergies. Patient's concerns "
        "(patient's own words): \"Will I need a test?\""
    )
    _install(monkeypatch, [_ok(good)])
    summary = generate_summary(FIXTURE_FEVER_ADULT, [], config=CFG, max_retries=0)
    assert "confirms no allergies" in summary.doctor_card


def test_summary_accepts_short_script_without_filler(monkeypatch):
    """A short record must not be padded with filler to hit a word target."""
    short_script = (
        "I have had a fever and headache since yesterday. I feel weak. "
        "I take paracetamol and ginger tea. I have no allergies."
    )  # 22 words
    assert 20 <= len(short_script.split()) <= 40  # genuinely short
    good = _payload(
        "Patient: Alex D., 34, female. Complaint: fever and headache. Symptoms: "
        "fever, headache, chills. Medicines: paracetamol; ginger and honey tea. "
        "Allergies: none — patient confirms no allergies. Patient's concerns "
        "(patient's own words): \"Will I need a test?\"",
        script=short_script,
    )
    _install(monkeypatch, [_ok(good)])
    summary = generate_summary(FIXTURE_FEVER_ADULT, [], config=CFG, max_retries=0)
    assert summary.patient_script == short_script.strip()
