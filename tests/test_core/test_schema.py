"""Tests for the shared patient-record schema.

Owned by Person 1.
"""

import copy

import pytest

from core.schema import (
    ALERT_LEVELS,
    MEDICINE_TYPES,
    MISSING_FIELD_KEYS,
    SEVERITY_LEVELS,
    SEX_VALUES,
    Alert,
    Medicine,
    PatientRecord,
    QuestionAnswer,
    SchemaError,
    SummaryOutput,
    empty_record,
    missing_fields,
    record_from_dict,
    record_to_dict,
    validate_record,
)


def test_empty_record_is_valid_and_fully_missing():
    record = empty_record()
    assert validate_record(record) == []
    assert set(record.missing_information) == set(MISSING_FIELD_KEYS)


def test_record_round_trips_through_dict():
    from core.fixtures import FIXTURE_RASH_WITH_ALLERGY

    original = FIXTURE_RASH_WITH_ALLERGY
    data = record_to_dict(original)
    restored = record_from_dict(copy.deepcopy(data))
    assert restored == original
    assert validate_record(restored) == []


def test_null_means_unknown_not_denied():
    record = empty_record()
    assert record.onset is None
    assert record.severity is None
    assert record.allergies == []
    assert record.allergies_denied is None
    assert "allergies" in missing_fields(record)


def test_explicit_denial_distinguished_from_unknown():
    denied = empty_record()
    denied.allergies_denied = True
    assert "allergies" not in missing_fields(denied)

    known_history = empty_record()
    known_history.medical_history = ["eczema"]
    assert "medical_history" not in missing_fields(known_history)


def test_denial_with_entries_is_invalid():
    record = empty_record()
    record.allergies = ["peanuts"]
    record.allergies_denied = True
    assert any("allergies_denied" in e for e in validate_record(record))


def test_invalid_severity_rejected():
    record = empty_record()
    record.severity = "extreme"
    assert validate_record(record)


def test_invalid_age_rejected():
    record = empty_record()
    record.patient_age = -3
    assert validate_record(record)

    record.patient_age = 999
    assert validate_record(record)


def test_invalid_sex_rejected():
    record = empty_record()
    record.patient_sex = "robot"
    assert validate_record(record)


def test_bad_payload_rejected_by_from_dict():
    with pytest.raises(SchemaError):
        record_from_dict({"severity": "catastrophic"})
    with pytest.raises(SchemaError):
        record_from_dict({"medicines": "paracetamol"})
    with pytest.raises(SchemaError):
        record_from_dict({"unknown_field": 1})
    with pytest.raises(SchemaError):
        record_from_dict("not a dict")


def test_medicine_type_covers_herbal():
    assert "herbal" in MEDICINE_TYPES
    medicine = Medicine(name="ginger tea", medicine_type="herbal")
    assert validate_record(empty_record()) == []
    record = empty_record()
    record.medicines = [medicine]
    record.medicines_denied = False
    assert validate_record(record) == []
    assert "medicines" not in missing_fields(record)


def test_structured_outputs_validate():
    assert Alert(code="x", message="y", level="urgent").level in ALERT_LEVELS
    summary = SummaryOutput(
        doctor_card="d", patient_script="p", priority_questions=["q1", "q2", "q3"]
    )
    assert len(summary.priority_questions) == 3
    assert QuestionAnswer("q", "a").answer == "a"


def test_enum_constants_are_english_and_stable():
    assert SEVERITY_LEVELS == ("mild", "moderate", "severe")
    assert SEX_VALUES == ("female", "male", "other", "not-specified")
    assert set(MISSING_FIELD_KEYS) == {
        "age",
        "sex",
        "onset",
        "duration",
        "severity",
        "medicines",
        "allergies",
        "medical_history",
        "concerns",
    }


def test_patient_wording_fields_are_plain_strings():
    record = empty_record()
    record.complaint = "My knee hurts like when I fell off the bike."
    record.symptoms = ["a funny hot feeling on my left knee"]
    assert validate_record(record) == []
    assert record.complaint == "My knee hurts like when I fell off the bike."
