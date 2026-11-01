"""Tests for the backend switch and the preview-only fixture backend.

Owned by Person 2. The whole test process runs with ``VISITPREP_PREVIEW=1``
(see conftest.py), so here we verify that the preview backend returns fictional
data and placeholders only — never re-implementing alert rules or summary
composition. The "preview off" path is verified in a fresh subprocess.
"""

import os
import subprocess
import sys

from core import fixtures

from ui import backend
from ui import fixture_backend as fb


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_preview_mode_is_enabled_for_these_tests():
    assert backend.preview_mode() is True
    assert backend.core_available() is True


def test_extract_record_returns_a_fictional_fixture_verbatim():
    record = fb.extract_record("I have crushing chest pain", {"age": 99})
    assert record == fixtures.FIXTURE_FEVER_ADULT
    assert record.complaint == fixtures.FIXTURE_FEVER_ADULT.complaint
    assert record.patient_name == "Alex D."


def test_choose_returns_fixed_fictional_questions_capped_at_five():
    asked = []
    seen = []
    for _ in range(10):
        question = fb.choose_follow_up_question(fixtures.FIXTURE_EMPTY_RECORD, asked)
        if question is None:
            break
        assert question.startswith("Preview:")
        assert question not in seen
        seen.append(question)
        from core.schema import QuestionAnswer

        asked.append(QuestionAnswer(question, ""))
    assert len(seen) <= 5


def test_merge_answer_returns_record_unchanged():
    record = fixtures.FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER
    merged = fb.merge_answer(record, "Preview: any medicines?", "aspirin")
    assert merged == record
    assert merged is not record


def test_check_alerts_returns_nothing():
    assert fb.check_alerts(fixtures.FIXTURE_RASH_WITH_ALLERGY) == []


def test_generate_summary_returns_placeholder_only():
    summary = fb.generate_summary(fixtures.FIXTURE_RASH_WITH_ALLERGY, [])
    assert "Preview:" in summary.doctor_card
    assert "Preview:" in summary.patient_script
    assert all("Preview:" in q for q in summary.priority_questions)


def test_preview_off_with_core_stub_raises_not_implemented():
    code = (
        "import os\n"
        "os.environ.pop('VISITPREP_PREVIEW', None)\n"
        "from ui import backend\n"
        "assert backend.preview_mode() is False\n"
        "assert backend.core_available() is False\n"
        "try:\n"
        "    backend.extract_record('x', None)\n"
        "except NotImplementedError:\n"
        "    print('NOT_IMPLEMENTED_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_project_root(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "NOT_IMPLEMENTED_OK" in result.stdout