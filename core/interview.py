"""Follow-up interview: question selection and safe answer merging.

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (v0.3,
section 4).

- ``choose_follow_up_question`` is rule-based (no API call): deterministic,
  fast, and keeps working when the ModelScope API is unavailable.
- ``merge_answer`` is LLM-backed but conservative: the updated record is
  validated and any update that drops a previously known fact is rejected
  (unless the change is an explicit denial via a ``*_denied`` flag). On API or
  validation failure the input record is returned untouched (not mutated) and
  a safe error is raised; the UI keeps the Q&A in its ``asked`` list so the
  patient's input is never lost.
- Answer-aware checks run inside the same bounded repair path: a newly set
  ``severity`` must be backed by an explicit mild/moderate/severe word in the
  answer (descriptive words like "bad" do not count), ``severity_note`` must
  not duplicate a symptom, and a ``*_denied`` flag that just became true must
  not be based on a hedged/uncertain answer ("I don't think I have
  allergies").
"""

from __future__ import annotations

import json

from core import prompts
from core._checks import (
    norm,
    severity_note_duplication_problems,
    severity_source_problems,
    uncertain_denial_problems,
)
from core.llm import chat_json_repairable
from core.schema import (
    PatientRecord,
    QuestionAnswer,
    SchemaError,
    missing_fields,
    record_from_dict,
    record_to_dict,
    recompute_missing_information,
)

__all__ = [
    "MAX_DISPLAYED_QUESTIONS",
    "PRIORITY_FIELDS",
    "QUESTION_TEMPLATES",
    "choose_follow_up_question",
    "merge_answer",
]

MAX_DISPLAYED_QUESTIONS = 5

#: Order in which missing fields are asked about (most important first).
PRIORITY_FIELDS: tuple[str, ...] = (
    "severity",
    "onset",
    "duration",
    "medicines",
    "allergies",
    "medical_history",
    "age",
    "sex",
    "concerns",
)

#: (self-report question, on-behalf question) per missing-field label.
QUESTION_TEMPLATES: dict[str, tuple[str, str]] = {
    "severity": (
        "How severe are your symptoms right now: mild, moderate, or severe?",
        "How severe are the patient's symptoms right now: mild, moderate, or severe?",
    ),
    "onset": (
        "When did your symptoms first start?",
        "When did the patient's symptoms first start?",
    ),
    "duration": (
        "How long have your symptoms been going on?",
        "How long has the patient's illness been going on?",
    ),
    "medicines": (
        "Are you currently taking any medicines, including herbal remedies or supplements?",
        "Is the patient currently taking any medicines, including herbal remedies or supplements?",
    ),
    "allergies": (
        "Do you have any known allergies?",
        "Does the patient have any known allergies?",
    ),
    "medical_history": (
        "Is there any past medical history the doctor should know about?",
        "Is there any past medical history the doctor should know about?",
    ),
    "age": (
        "How old are you?",
        "How old is the patient?",
    ),
    "sex": (
        "What is your sex (female, male, or other)?",
        "What is the patient's sex (female, male, or other)?",
    ),
    "concerns": (
        "What would you most like to ask the doctor?",
        "What would the patient most like to ask the doctor?",
    ),
}

#: List fields whose emptiness is acceptable when the matching *_denied flag
#: becomes true (an explicit retraction). The values are the *_denied flag keys
#: that may newly become true during a merge.
_LIST_DENY_FLAGS = {
    "medicines": "medicines_denied",
    "allergies": "allergies_denied",
    "medical_history": "medical_history_denied",
}
_DENIAL_FLAG_KEYS = tuple(_LIST_DENY_FLAGS.values())


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def choose_follow_up_question(
    record: PatientRecord,
    asked: list[QuestionAnswer],
    skipped: list[str] | None = None,
    max_questions: int = MAX_DISPLAYED_QUESTIONS,
) -> str | None:
    """Return the next short English question, or ``None`` when done.

    - The displayed-question budget counts questions the patient has already
      seen: ``len(asked) + len(skipped) >= max_questions`` stops the
      interview.
    - Never repeats a question already in ``asked`` or ``skipped`` (compared
      after stripping/case-folding).
    - Questions follow :data:`PRIORITY_FIELDS` for the fields still missing,
      adapted for on-behalf reports.
    """
    skipped = list(skipped or [])
    displayed = {_normalize(qa.question) for qa in asked}
    displayed.update(_normalize(s) for s in skipped)
    if len(asked) + len(skipped) >= max_questions:
        return None
    on_behalf = record.reporting_on_behalf is True
    missing = set(missing_fields(record))
    for field in PRIORITY_FIELDS:
        if field not in missing:
            continue
        question = QUESTION_TEMPLATES[field][1 if on_behalf else 0]
        if _normalize(question) in displayed:
            continue
        return question
    return None


def _lost_facts(before: dict, after: dict) -> list[str]:
    """Return labels of previously known facts that the update would drop.

    A list field becoming empty is acceptable only when the matching
    ``*_denied`` flag becomes ``True`` (explicit retraction). Scalar fields
    going from a value to null, and ``*_denied`` flags going from true to
    anything else, are always treated as loss.
    """
    lost: list[str] = []
    for key, old in before.items():
        if key == "missing_information":
            continue
        new = after.get(key)
        if key in _LIST_DENY_FLAGS or key == "symptoms":
            if old and not new:
                flag = _LIST_DENY_FLAGS.get(key)
                if not (flag is not None and after.get(flag) is True):
                    lost.append(key)
            continue
        if old in (None, ""):
            continue
        if new in (None, ""):
            lost.append(key)
        elif key.endswith("_denied") and old is True and new is not True:
            lost.append(key)
    return lost


def merge_answer(
    record: PatientRecord,
    question: str,
    answer: str,
    *,
    config=None,
    max_tokens: int = 4000,
    timeout: float = 120.0,
    max_retries: int = 2,
    max_repairs: int = 1,
) -> PatientRecord:
    """Return a **new** record with the answer merged in.

    - Pure with respect to the input: ``record`` is never mutated.
    - The update must keep every previously known fact unless the answer
      explicitly corrects it; drops are rejected (bounded repair, then a safe
      ``LLMResponseError``).
    - On API/validation failure the input record is unchanged and a safe
      error is raised; the UI should keep ``QuestionAnswer(question, answer)``
      in its ``asked`` list so the patient's input survives into the summary.
    """
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("answer must be a non-empty string")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    base = record_to_dict(record)
    answer_norm = norm(answer)

    def _validate(data: dict) -> list[str]:
        try:
            updated = record_from_dict(data)
        except SchemaError as exc:
            return [str(exc)]
        after = record_to_dict(updated)
        lost = _lost_facts(base, after)
        if lost:
            return ["the update would drop previously known fact(s): " + ", ".join(lost)]
        problems: list[str] = []
        if data.get("severity") is not None and data.get("severity") != base.get("severity"):
            problems.extend(severity_source_problems(data.get("severity"), answer_norm))
        problems.extend(
            severity_note_duplication_problems(
                data.get("severity_note"), data.get("symptoms")
            )
        )
        became_true = tuple(
            key for key in _DENIAL_FLAG_KEYS
            if base.get(key) is not True and data.get(key) is True
        )
        if became_true:
            problems.extend(
                uncertain_denial_problems(data, answer_norm, only_keys=became_true)
            )
        return problems

    user = prompts.merge_user(base, question, answer)
    data = chat_json_repairable(
        prompts.MERGE_SYSTEM,
        user,
        validate=_validate,
        repair_note=prompts.REPAIR_NOTE,
        max_repairs=max_repairs,
        config=config,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    updated = record_from_dict(data)
    return recompute_missing_information(updated)
