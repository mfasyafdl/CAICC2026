"""Tests for the fictional fixtures.

Owned by Person 1.
"""

from core import fixtures
from core.schema import record_from_dict, record_to_dict, validate_record


def test_all_fixtures_are_valid_records():
    for name, record in fixtures.all_fixtures().items():
        assert validate_record(record) == [], name


def test_fixtures_round_trip_through_dict():
    for name, record in fixtures.all_fixtures().items():
        restored = record_from_dict(record_to_dict(record))
        assert restored == record, name


def test_empty_fixture_is_all_unknown():
    record = fixtures.FIXTURE_EMPTY_RECORD
    assert record.patient_name is None
    assert record.complaint is None
    assert set(record.missing_information) == {
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


def test_fever_adult_shows_explicit_denial_and_herbal_medicine():
    record = fixtures.FIXTURE_FEVER_ADULT
    assert record.allergies == []
    assert record.allergies_denied is True
    assert "allergies" not in record.missing_information
    types = [m.medicine_type for m in record.medicines]
    assert "herbal" in types


def test_child_cough_shows_unknowns_and_on_behalf_report():
    record = fixtures.FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER
    assert record.reporting_on_behalf is True
    assert record.reporter_relationship == "mother"
    assert record.allergies_denied is None
    assert record.medicines_denied is None
    assert "allergies" in record.missing_information
    assert "medicines" in record.missing_information


def test_rash_fixture_is_complete():
    record = fixtures.FIXTURE_RASH_WITH_ALLERGY
    assert record.missing_information == []
    assert record.allergies == ["penicillin"]
    assert record.allergies_denied is False
    assert record.severity == "severe"
