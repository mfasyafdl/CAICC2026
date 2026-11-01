"""Tests for core.interview (question limit, merging, fact preservation).

Owned by Person 1. Transport faked — no network.
"""

import copy
import json
import urllib.error

import pytest

from core import llm
from core.fixtures import (
    FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER,
    FIXTURE_EMPTY_RECORD,
    FIXTURE_FEVER_ADULT,
)
from core.interview import (
    MAX_DISPLAYED_QUESTIONS,
    choose_follow_up_question,
    merge_answer,
)
from core.llm import LLMConfig, LLMNetworkError, LLMResponseError
from core.schema import QuestionAnswer, record_to_dict

FAKE_KEY = "ms-fake-key-do-not-use"
CFG = LLMConfig(api_key=FAKE_KEY, model="zai-org/GLM-5.2")


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


def _ok(record: dict) -> tuple[int, bytes]:
    return 200, json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": json.dumps(record)}}]}
    ).encode("utf-8")


def _asked(n: int) -> list[QuestionAnswer]:
    return [QuestionAnswer(f"Unrelated question number {i}?", "answer") for i in range(n)]


# --- question selection (rule-based, no API) --------------------------------


def test_first_question_targets_highest_priority_missing_field():
    from core.fixtures import FIXTURE_EMPTY_RECORD

    question = choose_follow_up_question(FIXTURE_EMPTY_RECORD, [])
    assert question == "How severe are your symptoms right now: mild, moderate, or severe?"


def test_question_limit_counts_asked():
    from core.fixtures import FIXTURE_EMPTY_RECORD

    asked = _asked(MAX_DISPLAYED_QUESTIONS)
    assert choose_follow_up_question(FIXTURE_EMPTY_RECORD, asked) is None
    assert choose_follow_up_question(FIXTURE_EMPTY_RECORD, _asked(4)) is not None


def test_question_limit_counts_skipped_questions():
    from core.fixtures import FIXTURE_EMPTY_RECORD

    asked = _asked(3)
    skipped = ["Skipped question one?", "Skipped question two?"]
    assert choose_follow_up_question(FIXTURE_EMPTY_RECORD, asked, skipped) is None
    assert (
        choose_follow_up_question(FIXTURE_EMPTY_RECORD, asked[:4], skipped[:1])
        is not None
    )


def test_never_repeats_asked_or_skipped_questions():
    from core.fixtures import FIXTURE_EMPTY_RECORD

    severity_q = "How severe are your symptoms right now: mild, moderate, or severe?"
    asked = [QuestionAnswer(severity_q, "moderate")]
    question = choose_follow_up_question(FIXTURE_EMPTY_RECORD, asked)
    assert question == "When did your symptoms first start?"

    onset_q = "When did your symptoms first start?"
    question = choose_follow_up_question(FIXTURE_EMPTY_RECORD, [], skipped=[onset_q, severity_q])
    assert question == "How long have your symptoms been going on?"


def test_on_behalf_questions_use_patient_wording():
    child = FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER
    question = choose_follow_up_question(child, [])
    assert "the patient" in question
    assert question == (
        "Is the patient currently taking any medicines, including herbal remedies or supplements?"
    )


def test_no_question_when_nothing_missing():
    complete = FIXTURE_FEVER_ADULT
    # fully populated record: nothing left to ask, even without a budget
    assert choose_follow_up_question(complete, []) is None
    asked = _asked(MAX_DISPLAYED_QUESTIONS)
    assert choose_follow_up_question(complete, asked) is None


# --- answer merging (LLM-backed, transport faked) ----------------------------


def test_merge_preserves_earlier_facts(monkeypatch):
    base = copy.deepcopy(FIXTURE_FEVER_ADULT)
    snapshot = record_to_dict(base)
    updated = record_to_dict(base)
    updated["medical_history"] = ["a thyroid condition since 2019"]
    _install(monkeypatch, [_ok(updated)])

    result = merge_answer(base, "Is there any past medical history the doctor should know about?", "A thyroid condition since 2019.", config=CFG, max_retries=0)

    assert result.medical_history == ["a thyroid condition since 2019"]
    # every other fact survived the merge
    for key, value in snapshot.items():
        if key in ("medical_history", "missing_information"):
            continue
        assert record_to_dict(result)[key] == value, key
    # input record untouched
    assert record_to_dict(base) == snapshot


def test_merge_rejects_fact_loss(monkeypatch):
    base = copy.deepcopy(FIXTURE_FEVER_ADULT)
    snapshot = record_to_dict(base)
    bad = record_to_dict(base)
    bad["severity"] = None  # drops a known fact without explicit correction
    transport = _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError) as exc:
        merge_answer(base, "How severe are your symptoms right now: mild, moderate, or severe?", "I am unsure.", config=CFG, max_retries=0, max_repairs=1)
    assert "drop previously known fact" in str(exc.value) or "invalid response" in str(exc.value)
    assert len(transport.calls) == 2  # bounded: 1 original + 1 repair
    assert record_to_dict(base) == snapshot  # input preserved


def test_merge_accepts_explicit_denial(monkeypatch):
    base = copy.deepcopy(FIXTURE_FEVER_ADULT)
    updated = record_to_dict(base)
    updated["medicines"] = []
    updated["medicines_denied"] = True
    _install(monkeypatch, [_ok(updated)])

    result = merge_answer(
        base,
        "Are you currently taking any medicines, including herbal remedies or supplements?",
        "I'm not taking anything now.",
        config=CFG,
        max_retries=0,
    )
    assert result.medicines == []
    assert result.medicines_denied is True
    assert "medicines" not in result.missing_information


def test_merge_api_error_preserves_record(monkeypatch):
    base = copy.deepcopy(FIXTURE_FEVER_ADULT)
    snapshot = record_to_dict(base)
    _install(monkeypatch, [urllib.error.URLError("dns fail")])
    with pytest.raises(LLMNetworkError) as exc:
        merge_answer(base, "When did your symptoms first start?", "Last Tuesday.", config=CFG, max_retries=0)
    assert FAKE_KEY not in str(exc.value)
    assert "Last Tuesday." not in str(exc.value)
    assert record_to_dict(base) == snapshot  # user input preserved on failure


def test_merge_rejects_empty_answer():
    with pytest.raises(ValueError):
        merge_answer(FIXTURE_FEVER_ADULT, "question?", "   ")


# --- answer-aware regression tests (issue fixes) -----------------------------


def test_merge_rejects_severity_mapped_from_descriptive_words(monkeypatch):
    """'really bad' in an answer must not become severity=severe."""
    base = FIXTURE_EMPTY_RECORD
    updated = record_to_dict(base)
    updated["severity"] = "severe"  # wrongly inferred from "really bad"
    transport = _install(monkeypatch, [_ok(updated), _ok(updated)])
    with pytest.raises(LLMResponseError):
        merge_answer(
            base,
            "How severe are your symptoms right now: mild, moderate, or severe?",
            "It's really bad at night.",
            config=CFG,
            max_retries=0,
            max_repairs=1,
        )
    assert len(transport.calls) == 2  # bounded repair


def test_merge_repair_fixes_severity_mapping(monkeypatch):
    """When the model corrects severity to null on repair, the merge succeeds."""
    base = FIXTURE_EMPTY_RECORD
    bad = record_to_dict(base)
    bad["severity"] = "severe"
    good = record_to_dict(base)  # severity stays null (unknown)
    transport = _install(monkeypatch, [_ok(bad), _ok(good)])
    result = merge_answer(
        base,
        "How severe are your symptoms right now: mild, moderate, or severe?",
        "It's really bad at night.",
        config=CFG,
        max_retries=0,
        max_repairs=1,
    )
    assert result.severity is None
    assert "severity" in result.missing_information
    assert len(transport.calls) == 2


def test_merge_rejects_uncertain_allergy_recorded_as_denial(monkeypatch):
    """'I don't think I have allergies' is uncertain, not an explicit denial."""
    base = FIXTURE_EMPTY_RECORD
    bad = record_to_dict(base)
    bad["allergies_denied"] = True  # wrongly treated as explicit denial
    transport = _install(monkeypatch, [_ok(bad), _ok(bad)])
    with pytest.raises(LLMResponseError):
        merge_answer(
            base,
            "Do you have any known allergies?",
            "I don't think I have allergies.",
            config=CFG,
            max_retries=0,
            max_repairs=1,
        )
    assert len(transport.calls) == 2


def test_merge_accepts_explicit_allergy_denial(monkeypatch):
    """A clear 'I have no allergies' correctly sets the denial flag."""
    base = FIXTURE_EMPTY_RECORD
    updated = record_to_dict(base)
    updated["allergies_denied"] = True
    _install(monkeypatch, [_ok(updated)])
    result = merge_answer(
        base,
        "Do you have any known allergies?",
        "I have no allergies.",
        config=CFG,
        max_retries=0,
    )
    assert result.allergies == []
    assert result.allergies_denied is True
    assert "allergies" not in result.missing_information
