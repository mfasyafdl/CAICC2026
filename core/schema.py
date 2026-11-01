"""Shared patient-record schema for VisitPrep.

Owned by Person 1. Defines the data structures passed between ``core/`` and
``ui/``; see ``docs/data_contract.md`` for the full contract. This module uses
only the Python standard library and has no UI dependencies.

Conventions
-----------
- All text values are English.
- ``None`` (JSON ``null``) always means *unknown / not provided*. It is never
  a guess. An explicit patient denial ("I have no allergies") is recorded with
  the matching ``*_denied`` boolean set to ``True`` and an empty list, so
  *unknown* and *explicit denial* stay distinguishable.
- Patient wording is preserved verbatim in every text field. Core code must
  never paraphrase, diagnose, or recommend treatment.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ALERT_LEVELS",
    "Alert",
    "MEDICINE_TYPES",
    "MISSING_FIELD_KEYS",
    "Medicine",
    "PatientRecord",
    "QuestionAnswer",
    "SEVERITY_LEVELS",
    "SEX_VALUES",
    "SchemaError",
    "SummaryOutput",
    "empty_record",
    "missing_fields",
    "recompute_missing_information",
    "record_from_dict",
    "record_to_dict",
    "validate_record",
]

# Allowed values (all English).
SEVERITY_LEVELS: tuple[str, ...] = ("mild", "moderate", "severe")
MEDICINE_TYPES: tuple[str, ...] = (
    "prescription",
    "over-the-counter",
    "herbal",
    "supplement",
    "unknown",
)
SEX_VALUES: tuple[str, ...] = ("female", "male", "other", "not-specified")
ALERT_LEVELS: tuple[str, ...] = ("attention", "urgent")

# Labels usable in ``PatientRecord.missing_information``.
MISSING_FIELD_KEYS: tuple[str, ...] = (
    "age",
    "sex",
    "onset",
    "duration",
    "severity",
    "medicines",
    "allergies",
    "medical_history",
    "concerns",
)

MAX_AGE = 130


class SchemaError(ValueError):
    """Raised when a payload does not match the data contract."""


@dataclass
class Medicine:
    """A medicine or remedy the patient reports taking.

    ``medicine_type`` includes ``"herbal"`` so herbal remedies and supplements
    are captured explicitly instead of being lost. All text fields preserve the
    patient's own wording.
    """

    name: str
    medicine_type: str = "unknown"
    dose: str | None = None
    frequency: str | None = None
    duration: str | None = None
    notes: str | None = None


@dataclass
class QuestionAnswer:
    """One follow-up question asked by core and the patient's answer.

    The UI keeps the full list of previously asked pairs and passes it back to
    core on every call, so core stays stateless.
    """

    question: str
    answer: str


@dataclass
class Alert:
    """A rule-based attention flag.

    Alerts surface patient-reported content that may need the doctor's
    attention (or urgent attention). They are never diagnoses and never
    contain treatment advice.
    """

    code: str
    message: str
    level: str = "attention"


@dataclass
class SummaryOutput:
    """Output of ``core.summary.generate_summary``.

    - ``doctor_card``: concise structured card for the doctor.
    - ``patient_script``: short first-person script the patient can read aloud.
    - ``priority_questions``: up to three questions the patient should ask the
      doctor.
    """

    doctor_card: str
    patient_script: str
    priority_questions: list[str] = field(default_factory=list)


@dataclass
class PatientRecord:
    """The shared patient record.

    ``None`` means *unknown* (not provided / not answered). Explicit denials
    are stored as an empty list plus the matching ``*_denied`` flag set to
    ``True``. See ``docs/data_contract.md`` for the field-by-field contract.
    """

    # --- patient / reporter details -------------------------------------
    patient_name: str | None = None
    patient_age: int | None = None
    patient_age_text: str | None = None
    patient_sex: str | None = None
    reporting_on_behalf: bool | None = None
    reporter_relationship: str | None = None

    # --- complaint & symptoms (patient's own wording) --------------------
    complaint: str | None = None
    symptoms: list[str] = field(default_factory=list)

    # --- onset / duration -------------------------------------------------
    onset: str | None = None
    duration: str | None = None
    duration_days: int | None = None

    # --- severity -----------------------------------------------------------
    severity: str | None = None
    severity_note: str | None = None

    # --- medicines (including herbal remedies) ------------------------------
    medicines: list[Medicine] = field(default_factory=list)
    medicines_denied: bool | None = None

    # --- allergies & history -------------------------------------------------
    allergies: list[str] = field(default_factory=list)
    allergies_denied: bool | None = None
    medical_history: list[str] = field(default_factory=list)
    medical_history_denied: bool | None = None

    # --- concerns for the doctor ---------------------------------------------
    concerns: list[str] = field(default_factory=list)

    # --- bookkeeping ---------------------------------------------------------
    missing_information: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def empty_record() -> PatientRecord:
    """Return a brand-new record where everything is unknown (``None``)."""
    record = PatientRecord()
    return recompute_missing_information(record)


def missing_fields(record: PatientRecord) -> list[str]:
    """Return the labels of fields that are still *unknown*.

    A list field is *known* when it has entries or when its ``*_denied`` flag
    is ``True`` (explicit denial). A list field is *unknown* when it is empty
    and its ``*_denied`` flag is ``None`` (never answered).
    """
    missing: list[str] = []
    if record.patient_age is None:
        missing.append("age")
    if record.patient_sex is None:
        missing.append("sex")
    if record.onset is None:
        missing.append("onset")
    if record.duration is None:
        missing.append("duration")
    if record.severity is None:
        missing.append("severity")
    if not record.medicines and record.medicines_denied is None:
        missing.append("medicines")
    if not record.allergies and record.allergies_denied is None:
        missing.append("allergies")
    if not record.medical_history and record.medical_history_denied is None:
        missing.append("medical_history")
    if not record.concerns:
        missing.append("concerns")
    return missing


def recompute_missing_information(record: PatientRecord) -> PatientRecord:
    """Recompute ``record.missing_information`` in place and return it."""
    record.missing_information = missing_fields(record)
    return record


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _check_text(errors: list[str], name: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        errors.append(f"{name} must be a non-empty string or null")


def _check_choice(errors: list[str], name: str, value: Any, allowed: tuple[str, ...]) -> None:
    if value is not None and value not in allowed:
        errors.append(f"{name} must be one of {list(allowed)} or null")


def _check_int(errors: list[str], name: str, value: Any, lo: int, hi: int) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi
    ):
        errors.append(f"{name} must be an integer between {lo} and {hi}, or null")


def _check_bool(errors: list[str], name: str, value: Any) -> None:
    if value is not None and not isinstance(value, bool):
        errors.append(f"{name} must be true, false, or null")


def _check_str_list(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{name} must be a list of non-empty strings")


def validate_medicine(medicine: Any) -> list[str]:
    """Return a list of problems with one Medicine (empty list = valid)."""
    errors: list[str] = []
    if not isinstance(medicine, Medicine):
        return ["medicine must be a Medicine instance"]
    _check_text(errors, "medicine.name", medicine.name)
    _check_choice(errors, "medicine.medicine_type", medicine.medicine_type, MEDICINE_TYPES)
    for attr in ("dose", "frequency", "duration", "notes"):
        _check_text(errors, f"medicine.{attr}", getattr(medicine, attr))
    return errors


def validate_record(record: Any) -> list[str]:
    """Return a list of problems with a PatientRecord (empty list = valid)."""
    if not isinstance(record, PatientRecord):
        return ["record must be a PatientRecord instance"]
    errors: list[str] = []

    _check_text(errors, "patient_name", record.patient_name)
    _check_int(errors, "patient_age", record.patient_age, 0, MAX_AGE)
    _check_text(errors, "patient_age_text", record.patient_age_text)
    _check_choice(errors, "patient_sex", record.patient_sex, SEX_VALUES)
    _check_bool(errors, "reporting_on_behalf", record.reporting_on_behalf)
    _check_text(errors, "reporter_relationship", record.reporter_relationship)

    _check_text(errors, "complaint", record.complaint)
    _check_str_list(errors, "symptoms", record.symptoms)

    _check_text(errors, "onset", record.onset)
    _check_text(errors, "duration", record.duration)
    _check_int(errors, "duration_days", record.duration_days, 0, 3650)

    _check_choice(errors, "severity", record.severity, SEVERITY_LEVELS)
    _check_text(errors, "severity_note", record.severity_note)

    if not isinstance(record.medicines, list) or any(
        not isinstance(m, Medicine) for m in record.medicines
    ):
        errors.append("medicines must be a list of Medicine instances")
    else:
        for i, medicine in enumerate(record.medicines):
            errors.extend(f"medicines[{i}]: {e}" for e in validate_medicine(medicine))
    _check_bool(errors, "medicines_denied", record.medicines_denied)

    _check_str_list(errors, "allergies", record.allergies)
    _check_bool(errors, "allergies_denied", record.allergies_denied)
    _check_str_list(errors, "medical_history", record.medical_history)
    _check_bool(errors, "medical_history_denied", record.medical_history_denied)

    _check_str_list(errors, "concerns", record.concerns)
    _check_str_list(errors, "missing_information", record.missing_information)
    for label in record.missing_information:
        if label not in MISSING_FIELD_KEYS:
            errors.append(
                f"missing_information entry {label!r} is not one of {list(MISSING_FIELD_KEYS)}"
            )

    # An explicit denial contradicts a non-empty list.
    for denied, items in (
        ("medicines_denied", record.medicines),
        ("allergies_denied", record.allergies),
        ("medical_history_denied", record.medical_history),
    ):
        if record.__dict__[denied] is True and items:
            errors.append(f"{denied} is true but the list is not empty")
    return errors


# ---------------------------------------------------------------------------
# Dict (de)serialization — the JSON form used across the core/ui boundary
# ---------------------------------------------------------------------------

_Medicine_FIELDS = {f.name for f in dataclasses.fields(Medicine)}
_Record_FIELDS = {f.name for f in dataclasses.fields(PatientRecord)}


def record_to_dict(record: PatientRecord) -> dict:
    """Return the JSON-ready dict form of a record (``None`` stays ``null``)."""
    return dataclasses.asdict(record)


def _medicine_from_dict(data: Any) -> Medicine:
    if not isinstance(data, dict):
        raise SchemaError("each medicine must be an object")
    unknown = set(data) - _Medicine_FIELDS
    if unknown:
        raise SchemaError(f"unknown medicine field(s): {sorted(unknown)}")
    medicine = Medicine(
        name=data.get("name"),
        medicine_type=data.get("medicine_type", "unknown"),
        dose=data.get("dose"),
        frequency=data.get("frequency"),
        duration=data.get("duration"),
        notes=data.get("notes"),
    )
    errors = validate_medicine(medicine)
    if errors:
        raise SchemaError("; ".join(errors))
    return medicine


def record_from_dict(data: Any) -> PatientRecord:
    """Build and strictly validate a PatientRecord from its dict form.

    Raises ``SchemaError`` on unknown fields, wrong types, or invalid values.
    """
    if not isinstance(data, dict):
        raise SchemaError("record must be an object")
    unknown = set(data) - _Record_FIELDS
    if unknown:
        raise SchemaError(f"unknown record field(s): {sorted(unknown)}")

    medicines = [_medicine_from_dict(item) for item in data.get("medicines", [])]
    record = PatientRecord(
        patient_name=data.get("patient_name"),
        patient_age=data.get("patient_age"),
        patient_age_text=data.get("patient_age_text"),
        patient_sex=data.get("patient_sex"),
        reporting_on_behalf=data.get("reporting_on_behalf"),
        reporter_relationship=data.get("reporter_relationship"),
        complaint=data.get("complaint"),
        symptoms=data.get("symptoms", []),
        onset=data.get("onset"),
        duration=data.get("duration"),
        duration_days=data.get("duration_days"),
        severity=data.get("severity"),
        severity_note=data.get("severity_note"),
        medicines=medicines,
        medicines_denied=data.get("medicines_denied"),
        allergies=data.get("allergies", []),
        allergies_denied=data.get("allergies_denied"),
        medical_history=data.get("medical_history", []),
        medical_history_denied=data.get("medical_history_denied"),
        concerns=data.get("concerns", []),
        missing_information=data.get("missing_information", []),
    )
    errors = validate_record(record)
    if errors:
        raise SchemaError("; ".join(errors))
    return record
