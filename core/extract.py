"""Free-text extraction into a validated PatientRecord (LLM-backed).

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (v0.3,
section 4).

Guarantees:
- The model output is strictly validated against the data contract
  (``record_from_dict``); invalid output is repaired at most once (bounded)
  and then surfaced as a safe ``LLMResponseError``.
- Source-aware checks run inside the same bounded repair path: the complaint
  must be a verbatim excerpt of the patient's text, ``severity`` may only be
  set when the patient explicitly says mild/moderate/severe (descriptive words
  like "bad" do not count), ``severity_note`` must not duplicate a symptom,
  and an uncertain statement ("I don't think I have allergies") must not be
  recorded as an explicit denial.
- Patient text is treated as data: it is wrapped in tags and the system prompt
  explicitly says to ignore instructions inside it.
- On any failure the raw patient text is not modified or lost: the caller (UI)
  keeps its copy and can retry.
"""

from __future__ import annotations

from core import prompts
from core._checks import (
    complaint_verbatim_problems,
    norm,
    severity_note_duplication_problems,
    severity_source_problems,
    uncertain_denial_problems,
)
from core.llm import chat_json_repairable
from core.schema import (
    PatientRecord,
    SchemaError,
    record_from_dict,
    recompute_missing_information,
    validate_record,
)

__all__ = ["extract_record"]

_DETAIL_KEYS = ("patient_name", "patient_age", "patient_sex")


def _validate_factory(source: str):
    source_norm = norm(source)

    def _validate(data: dict) -> list[str]:
        try:
            record_from_dict(data)
        except SchemaError as exc:
            return [str(exc)]
        problems: list[str] = []
        problems.extend(complaint_verbatim_problems(data.get("complaint"), source_norm))
        problems.extend(severity_source_problems(data.get("severity"), source_norm))
        problems.extend(
            severity_note_duplication_problems(
                data.get("severity_note"), data.get("symptoms")
            )
        )
        problems.extend(uncertain_denial_problems(data, source_norm))
        return problems

    return _validate


def _apply_patient_details(
    record: PatientRecord, patient_details: dict | None
) -> PatientRecord:
    if not patient_details:
        return record
    for key in _DETAIL_KEYS:
        value = patient_details.get(key)
        if value is not None:
            setattr(record, key, value)
    errors = validate_record(record)
    if errors:
        raise SchemaError("; ".join(errors))
    return record


def extract_record(
    symptom_text: str,
    patient_details: dict | None = None,
    *,
    config=None,
    max_tokens: int = 4000,
    timeout: float = 120.0,
    max_retries: int = 2,
    max_repairs: int = 1,
) -> PatientRecord:
    """Parse the patient's raw description into a validated record.

    - Preserves patient wording, uncertainty, and negation (per contract).
    - Uses ``None`` for anything not stated; never invents facts.
    - ``patient_details`` (name/age/sex entered in the UI) overrides the
      extracted values when provided.
    - Raises ``ValueError`` on empty input, ``SchemaError`` on invalid
      patient details, and safe ``LLMError`` subclasses on API or output
      failures. On failure the input text is left untouched.
    """
    if not isinstance(symptom_text, str) or not symptom_text.strip():
        raise ValueError("symptom_text must be a non-empty string")
    user = prompts.extraction_user(symptom_text, patient_details)
    data = chat_json_repairable(
        prompts.EXTRACTION_SYSTEM,
        user,
        validate=_validate_factory(symptom_text),
        repair_note=prompts.REPAIR_NOTE,
        max_repairs=max_repairs,
        config=config,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
    record = record_from_dict(data)
    record = _apply_patient_details(record, patient_details)
    return recompute_missing_information(record)
