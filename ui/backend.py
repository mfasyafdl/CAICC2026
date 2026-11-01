"""Backend selection for the VisitPrep UI.

The backend is chosen exactly once, at startup, by the environment variable
``VISITPREP_PREVIEW``:

- ``VISITPREP_PREVIEW=1`` — use the clearly-labeled preview backend
  (``ui.fixture_backend``), which returns fictional records and placeholder
  text only. The preview banner is shown on every step.
- otherwise (default) — use the real core modules. If core is not implemented
  yet its calls raise ``NotImplementedError``; the UI catches that and shows a
  clear English error rather than fake output.
"""

from __future__ import annotations

import os

from core.schema import empty_record

_PREVIEW = os.environ.get("VISITPREP_PREVIEW", "0") == "1"

__all__ = [
    "CORE_UNAVAILABLE_NOTICE",
    "check_alerts",
    "choose_follow_up_question",
    "core_available",
    "extract_record",
    "generate_summary",
    "max_follow_up_questions",
    "merge_answer",
    "preview_mode",
]

CORE_UNAVAILABLE_NOTICE = (
    "The core pipeline is not implemented yet. Set VISITPREP_PREVIEW=1 and "
    "restart to view the fictional preview."
)

max_follow_up_questions: int = 5


def preview_mode() -> bool:
    """Return ``True`` when the fictional preview backend is active."""
    return _PREVIEW


if _PREVIEW:
    from ui import fixture_backend as _fb

    def extract_record(symptom_text, patient_details=None):
        return _fb.extract_record(symptom_text, patient_details)

    def choose_follow_up_question(record, asked, max_questions=None):
        if max_questions is None:
            max_questions = max_follow_up_questions
        return _fb.choose_follow_up_question(record, asked, max_questions)

    def merge_answer(record, question, answer):
        return _fb.merge_answer(record, question, answer)

    def check_alerts(record):
        return _fb.check_alerts(record)

    def generate_summary(record, asked):
        return _fb.generate_summary(record, asked)

    def core_available() -> bool:
        return True

else:
    from core.alerts import check_alerts as _check_alerts
    from core.extraction import extract_record as _extract_record
    from core.questions import (
        MAX_FOLLOW_UP_QUESTIONS as _MAX_Q,
        choose_follow_up_question as _choose,
        merge_answer as _merge,
    )
    from core.summary import generate_summary as _generate_summary

    max_follow_up_questions = _MAX_Q

    def extract_record(symptom_text, patient_details=None):
        return _extract_record(symptom_text, patient_details)

    def choose_follow_up_question(record, asked, max_questions=None):
        if max_questions is None:
            max_questions = max_follow_up_questions
        return _choose(record, asked, max_questions)

    def merge_answer(record, question, answer):
        return _merge(record, question, answer)

    def check_alerts(record):
        return _check_alerts(record)

    def generate_summary(record, asked):
        return _generate_summary(record, asked)

    _core_available = True
    try:
        _check_alerts(empty_record())
    except NotImplementedError:
        _core_available = False

    def core_available() -> bool:
        return _core_available