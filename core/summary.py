"""Doctor-card / patient-script summary generation.

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (section 6).
"""

from __future__ import annotations

from core.schema import QuestionAnswer, SummaryOutput, PatientRecord

__all__ = ["generate_summary"]


def generate_summary(
    record: PatientRecord,
    asked: list[QuestionAnswer],
) -> SummaryOutput:
    """Generate the summary outputs for the finished record.

    Contract (docs/data_contract.md, section 6.5):
    - ``record`` is the reviewed, merged record; ``asked`` is the full list of
      previously asked questions with answers, as kept by the UI.
    - Returns ``SummaryOutput`` with:
      - ``doctor_card``: concise structured card for the doctor.
      - ``patient_script``: short first-person script the patient can read
        aloud to the doctor.
      - ``priority_questions``: up to three questions the patient should ask
        the doctor.
    - Unknown fields are presented as "not provided", never guessed. No
      diagnosis, no treatment recommendation.
    """
    raise NotImplementedError(
        "core.summary.generate_summary is not implemented yet "
        "(see docs/data_contract.md)"
    )
