"""Doctor card, patient script, and priority questions (LLM-backed).

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (v0.3,
section 4).

Guarantees:
- Returns ``SummaryOutput`` with ``doctor_card``, ``patient_script`` (a
  concise first-person read with NO filler), and ``priority_questions``
  (1-3 items).
- The model output is validated (types, non-empty, script length window);
  invalid output is repaired at most once (bounded) and then surfaced as a
  safe ``LLMResponseError``.
- Record-aware checks run inside the same bounded repair path: the doctor
  card must not invent negatives for unknown fields (use "Not provided"),
  must not claim completeness ("no other symptoms"), and must distinguish
  confirmed denials (``*_denied`` true) from unknown (``*_denied`` null).
- The summary contains no alerts: rule-based alerts are produced only by
  ``core.redflag`` and rendered by the UI, so the model can never remove a
  rule-generated alert.
- On failure the record and ``asked`` list are untouched; the UI keeps them
  and can retry.
"""

from __future__ import annotations

from core import prompts
from core.llm import chat_json_repairable
from core.schema import QuestionAnswer, SummaryOutput, PatientRecord, record_to_dict

__all__ = ["generate_summary"]

#: Loose word-count window for the script. The lower bound only rejects
#: degenerate output; the prompt explicitly forbids filler, so a short record
#: is allowed to produce a short script (issue: do not pad to a word target).
_SCRIPT_MIN_WORDS = 20
_SCRIPT_MAX_WORDS = 260

#: (label, list key, denied flag key, denial phrases that are only valid when
#: the matching *_denied flag is true). When the field is unknown (denied is
#: null and the list empty), these phrases invent a negative and are rejected.
_DENIAL_FIELDS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "allergies",
        "allergies",
        "allergies_denied",
        (
            "no allergies",
            "no known allergies",
            "allergies: none",
            "allergies - none",
            "allergies — none",
            "allergies none",
        ),
    ),
    (
        "medicines",
        "medicines",
        "medicines_denied",
        (
            "no medicines",
            "not taking any medicines",
            "no medications",
            "not taking any medications",
            "medicines: none",
            "medicines - none",
            "medicines — none",
            "takes none",
            "takes nothing",
        ),
    ),
    (
        "medical history",
        "medical_history",
        "medical_history_denied",
        (
            "no medical history",
            "no history of",
            "medical history: none",
            "medical history - none",
            "medical history — none",
        ),
    ),
)

#: Phrases that assert completeness — mentioning one item does not mean there
#: are no others, so these invented negatives are always rejected.
_COMPLETENESS_PHRASES: tuple[str, ...] = (
    "no other symptoms",
    "no other medicines",
    "no other medications",
    "no other conditions",
    "only symptom",
    "only medicine",
    "the only symptom",
    "the only medicine",
    "takes nothing else",
    "nothing else to report",
)


def _validate_factory(record: PatientRecord):
    rec = record_to_dict(record)

    def _unknown_fields() -> list[str]:
        unknown: list[str] = []
        for scalar in ("patient_age", "patient_sex", "onset", "duration", "severity"):
            if rec.get(scalar) is None:
                unknown.append(scalar)
        for _label, list_key, denied_key, _phrases in _DENIAL_FIELDS:
            if rec.get(denied_key) is None and not rec.get(list_key):
                unknown.append(list_key)
        if not rec.get("concerns"):
            unknown.append("concerns")
        return unknown

    def _validate(data: dict) -> list[str]:
        errors: list[str] = []
        if not isinstance(data, dict):
            return ["the response was not a JSON object"]
        card = data.get("doctor_card")
        script = data.get("patient_script")
        questions = data.get("priority_questions")
        if not isinstance(card, str) or not card.strip():
            errors.append("doctor_card must be a non-empty string")
        else:
            card_low = card.lower()
            for label, list_key, denied_key, phrases in _DENIAL_FIELDS:
                is_unknown = rec.get(denied_key) is None and not rec.get(list_key)
                if is_unknown:
                    for phrase in phrases:
                        if phrase in card_low:
                            errors.append(
                                f"doctor_card says '{phrase}' for {label}, but the "
                                f"record does not confirm that denial (the field is "
                                "unknown); write 'Not provided' instead"
                            )
                            break
            for phrase in _COMPLETENESS_PHRASES:
                if phrase in card_low:
                    errors.append(
                        f"doctor_card says '{phrase}'; mentioning one symptom or "
                        "remedy does not mean there are no others"
                    )
                    break
            if _unknown_fields() and "not provided" not in card_low:
                errors.append(
                    "doctor_card must label unknown information as 'Not provided'"
                )
        if not isinstance(script, str) or not script.strip():
            errors.append("patient_script must be a non-empty string")
        else:
            words = len(script.split())
            if not _SCRIPT_MIN_WORDS <= words <= _SCRIPT_MAX_WORDS:
                errors.append(
                    "patient_script must be a concise first-person script with no "
                    f"filler (got {words} words; allowed {_SCRIPT_MIN_WORDS}-"
                    f"{_SCRIPT_MAX_WORDS})"
                )
        if (
            not isinstance(questions, list)
            or not questions
            or not all(isinstance(q, str) and q.strip() for q in questions)
        ):
            errors.append("priority_questions must be a list of non-empty strings")
        elif len(questions) > 3:
            errors.append("priority_questions must have at most 3 items")
        return errors

    return _validate


def generate_summary(
    record: PatientRecord,
    asked: list[QuestionAnswer],
    *,
    config=None,
    max_tokens: int = 4000,
    timeout: float = 120.0,
    max_retries: int = 2,
    max_repairs: int = 1,
) -> SummaryOutput:
    """Generate the visit summary from the confirmed record and Q&A history.

    The patient's concerns are quoted verbatim in the doctor card and kept
    separate from the app's organization; no diagnosis, no prescription, no
    medication-change recommendation (enforced by prompt and validation).
    """
    asked = list(asked)
    user = prompts.summary_user(record_to_dict(record), asked)
    data = chat_json_repairable(
        prompts.SUMMARY_SYSTEM,
        user,
        validate=_validate_factory(record),
        repair_note=prompts.REPAIR_NOTE,
        max_repairs=max_repairs,
        config=config,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    return SummaryOutput(
        doctor_card=data["doctor_card"].strip(),
        patient_script=data["patient_script"].strip(),
        priority_questions=[q.strip() for q in data["priority_questions"]],
    )
