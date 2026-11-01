"""Backend selection for the VisitPrep UI.

The three LLM-backed core calls are chosen at startup by ``VISITPREP_PREVIEW``:

- ``VISITPREP_PREVIEW=1`` — use the clearly-labeled preview backend
  (``ui.fixture_backend``) for ``extract_record`` / ``merge_answer`` /
  ``generate_summary``, so the interface runs without an API key.
- otherwise (default) — use the real ``core.extract`` / ``core.interview`` /
  ``core.summarize`` calls, which talk to the ModelScope API through
  ``core.llm``.

The rule-based calls are **always** the real core code (they never touch the
network): ``choose_follow_up_question`` (``core.interview``), and
``check_alerts`` / ``scan_text`` (``core.redflag``).
"""

from __future__ import annotations

import os

from core.extract import extract_record as _extract_record
from core.interview import (
    MAX_DISPLAYED_QUESTIONS,
    choose_follow_up_question as _choose,
    merge_answer as _merge,
)
from core.redflag import check_alerts as _check_alerts
from core.redflag import scan_text as _scan_text
from core.summarize import generate_summary as _generate_summary

_PREVIEW = os.environ.get("VISITPREP_PREVIEW", "0") == "1"

__all__ = [
    "check_alerts",
    "choose_follow_up_question",
    "extract_record",
    "generate_summary",
    "max_follow_up_questions",
    "merge_answer",
    "preview_mode",
    "scan_text",
]

max_follow_up_questions: int = MAX_DISPLAYED_QUESTIONS


def preview_mode() -> bool:
    """Return ``True`` when the fictional preview backend is active."""
    return _PREVIEW


scan_text = _scan_text
check_alerts = _check_alerts


def choose_follow_up_question(record, asked, skipped=None, max_questions=None):
    if max_questions is None:
        max_questions = max_follow_up_questions
    return _choose(record, asked, skipped=skipped, max_questions=max_questions)


if _PREVIEW:
    from ui import fixture_backend as _fb

    def extract_record(symptom_text, patient_details=None):
        return _fb.extract_record(symptom_text, patient_details)

    def merge_answer(record, question, answer):
        return _fb.merge_answer(record, question, answer)

    def generate_summary(record, asked):
        return _fb.generate_summary(record, asked)

else:
    extract_record = _extract_record
    merge_answer = _merge
    generate_summary = _generate_summary