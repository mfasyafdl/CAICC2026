"""Follow-up question selection and answer merging.

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (section 6).
Both functions are pure: the UI owns the conversation state (the current
record plus the list of previously asked questions) and passes it in on every
call.
"""

from __future__ import annotations

from core.schema import PatientRecord, QuestionAnswer

__all__ = ["MAX_FOLLOW_UP_QUESTIONS", "choose_follow_up_question", "merge_answer"]

MAX_FOLLOW_UP_QUESTIONS = 5


def choose_follow_up_question(
    record: PatientRecord,
    asked: list[QuestionAnswer],
    max_questions: int = MAX_FOLLOW_UP_QUESTIONS,
) -> str | None:
    """Return the next follow-up question to ask, or ``None`` when done.

    Contract (docs/data_contract.md, section 6.2):
    - ``asked`` is the list of previously asked questions with answers, in
      order, as kept by the UI.
    - Returns ``None`` once ``len(asked) >= max_questions`` or no useful
      question remains (nothing missing worth asking).
    - Never repeats a question already in ``asked`` (compared after stripping
      and case-folding).
    - Questions target ``record.missing_information`` first, then clarification
      of ambiguous fields; at most one question at a time, in plain English.
    """
    raise NotImplementedError(
        "core.questions.choose_follow_up_question is not implemented yet "
        "(see docs/data_contract.md)"
    )


def merge_answer(
    record: PatientRecord,
    question: str,
    answer: str,
) -> PatientRecord:
    """Return a new record with ``answer`` merged into ``record``.

    Contract (docs/data_contract.md, section 6.3):
    - Pure function: ``record`` is not mutated.
    - The answer is stored in the patient's own wording.
    - An explicit denial ("no", "I'm not taking anything") sets the matching
      ``*_denied`` flag to ``True``; an evasive or unclear answer leaves the
      field ``None`` (unknown).
    - ``missing_information`` is recomputed on the returned record.
    - The UI is responsible for appending
      ``QuestionAnswer(question, answer)`` to its own ``asked`` list.
    """
    raise NotImplementedError(
        "core.questions.merge_answer is not implemented yet "
        "(see docs/data_contract.md)"
    )
