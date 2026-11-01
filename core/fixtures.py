"""Fictional test fixtures for VisitPrep.

Owned by Person 1; intended to be imported by Person 2 for UI development and
checks. **All names and details are fictional.** These fixtures are pure data:
they need no network, no LLM, and no Gradio.

Coverage:
- ``FIXTURE_EMPTY_RECORD``: a fresh record where everything is unknown.
- ``FIXTURE_FEVER_ADULT``: explicit "no allergies" denial, two medicines
  including a herbal remedy, partial missing information.
- ``FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER``: reported on behalf of a child;
  allergies and medicines left *unknown* (``None``) to contrast with explicit
  denial.
- ``FIXTURE_RASH_WITH_ALLERGY``: a complete record with an explicit allergy
  list, a prescription medicine, and severe severity.
"""

from __future__ import annotations

from core.schema import Medicine, PatientRecord, empty_record

__all__ = [
    "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER",
    "FIXTURE_EMPTY_RECORD",
    "FIXTURE_FEVER_ADULT",
    "FIXTURE_RASH_WITH_ALLERGY",
    "all_fixtures",
]


def _finish(record: PatientRecord) -> PatientRecord:
    from core.schema import recompute_missing_information

    return recompute_missing_information(record)


FIXTURE_EMPTY_RECORD = empty_record()


FIXTURE_FEVER_ADULT = _finish(
    PatientRecord(
        patient_name="Alex D.",
        patient_age=34,
        patient_age_text="34",
        patient_sex="female",
        reporting_on_behalf=False,
        complaint="I feel feverish and my head has been hurting since yesterday.",
        symptoms=["fever", "headache", "chills"],
        onset="yesterday afternoon",
        duration="since yesterday",
        duration_days=1,
        severity="moderate",
        severity_note="I can still work but I feel weak.",
        medicines=[
            Medicine(
                name="paracetamol",
                medicine_type="over-the-counter",
                dose="one tablet",
                frequency="when the fever spikes",
                notes="I usually take it after meals.",
            ),
            Medicine(
                name="ginger and honey tea",
                medicine_type="herbal",
                dose="one cup",
                frequency="in the morning",
                notes="My neighbor suggested it for colds.",
            ),
        ],
        medicines_denied=False,
        allergies=[],
        allergies_denied=True,
        medical_history=[],
        medical_history_denied=False,
        concerns=["Will I need a test?", "Can I keep working?"],
    )
)


FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER = _finish(
    PatientRecord(
        patient_name="Sam",
        patient_age=7,
        patient_age_text="7 years old",
        patient_sex="male",
        reporting_on_behalf=True,
        reporter_relationship="mother",
        complaint="He's had a bad cough for about five days and it's worse at night.",
        symptoms=["cough, worse at night", "runny nose", "vomited once after a coughing fit"],
        onset="about five days ago",
        duration="about five days",
        duration_days=5,
        severity="moderate",
        severity_note="It wakes him up at night.",
        medicines=[],
        medicines_denied=None,
        allergies=[],
        allergies_denied=None,
        medical_history=["mild asthma as a baby"],
        medical_history_denied=None,
        concerns=["Is this just a cold?", "Should he stay home from school?"],
    )
)


FIXTURE_RASH_WITH_ALLERGY = _finish(
    PatientRecord(
        patient_name="Maya R.",
        patient_age=41,
        patient_age_text="41",
        patient_sex="female",
        reporting_on_behalf=False,
        complaint="A red itchy rash on my arms since Monday.",
        symptoms=["red itchy rash on both arms", "small blisters on my wrist"],
        onset="Monday morning",
        duration="four days",
        duration_days=4,
        severity="severe",
        severity_note="The itching stops me from sleeping.",
        medicines=[
            Medicine(
                name="diphenhydramine",
                medicine_type="prescription",
                dose="25 mg",
                frequency="at night",
                duration="for two weeks",
                notes="Prescribed last year for a similar rash.",
            )
        ],
        medicines_denied=False,
        allergies=["penicillin"],
        allergies_denied=False,
        medical_history=["eczema as a child"],
        medical_history_denied=False,
        concerns=["Could this be an allergy to a new detergent?", "How long will it take to go away?"],
    )
)


def all_fixtures() -> dict[str, PatientRecord]:
    """Return all fixtures by name (useful in tests and UI dev tools)."""
    return {
        "FIXTURE_EMPTY_RECORD": FIXTURE_EMPTY_RECORD,
        "FIXTURE_FEVER_ADULT": FIXTURE_FEVER_ADULT,
        "FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER": FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER,
        "FIXTURE_RASH_WITH_ALLERGY": FIXTURE_RASH_WITH_ALLERGY,
    }
