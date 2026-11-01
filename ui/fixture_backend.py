"""Preview backend (fictional data only) for the VisitPrep UI.

Owned by Person 2. This is a *preview-only* stand-in for the three LLM-backed
core calls, used when ``VISITPREP_PREVIEW=1`` is set so the interface can be
demoed without an API key. It contains **no business logic** and only wraps the
fictional fixtures:

- ``extract_record`` returns one of the clearly-labeled fictional records from
  ``core/fixtures.py`` verbatim (it never parses the patient's free text).
- ``merge_answer`` returns the record unchanged.
- ``generate_summary`` returns fixed, clearly-fictional placeholder text.

The rule-based core calls (follow-up questions and alerts) are **not** wrapped
here: they are real ``core.interview`` / ``core.redflag`` code and are always
used, in preview and otherwise. The preview banner is shown on every step so
the fictional data is never presented unlabeled.
"""

from __future__ import annotations

import copy

from core.fixtures import FIXTURE_FEVER_ADULT
from core.schema import SummaryOutput

__all__ = ["extract_record", "generate_summary", "merge_answer"]


def extract_record(symptom_text, patient_details=None):
    """Return a fictional fixture record; the free text is never parsed."""
    del symptom_text, patient_details
    return copy.deepcopy(FIXTURE_FEVER_ADULT)


def merge_answer(record, question, answer):
    """Return ``record`` unchanged (no answer merging in preview)."""
    del question, answer
    return copy.deepcopy(record)


def generate_summary(record, asked):
    """Return fixed, clearly-fictional placeholder summary text."""
    del record, asked
    return SummaryOutput(
        doctor_card=(
            "Preview: this is placeholder text shown with fictional data. The "
            "doctor card will appear here once the real ModelScope API is "
            "available and core summarization runs."
        ),
        patient_script=(
            "Preview: fictional patient-script placeholder for a demo run."
        ),
        priority_questions=[
            "Preview: a fictional example question.",
            "Preview: another fictional example question.",
            "Preview: a third fictional example question.",
        ],
    )