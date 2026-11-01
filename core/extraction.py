"""Free-text extraction into a PatientRecord.

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (section 6).
The LLM-backed implementation arrives in a later core task; this module exists
so the contract has stable, importable names.
"""

from __future__ import annotations

from core.schema import PatientRecord

__all__ = ["extract_record"]


def extract_record(symptom_text: str, patient_details: dict | None = None) -> PatientRecord:
    """Parse the patient's free text into a structured record.

    Contract (docs/data_contract.md, section 6.1):
    - ``symptom_text`` is the patient's raw description, in their own words.
    - ``patient_details`` optionally carries name/age/sex entered by the UI.
    - The returned record preserves the patient's wording, uses ``None`` for
      anything not stated, and has ``missing_information`` recomputed.
    - Never paraphrases, diagnoses, or recommends treatment.
    """
    raise NotImplementedError(
        "core.extraction.extract_record is not implemented yet "
        "(see docs/data_contract.md)"
    )
