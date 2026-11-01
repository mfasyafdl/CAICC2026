"""Private source/record-aware validation helpers for the LLM workflow.

Owned by Person 1. These checks run *inside* the bounded repair/error path of
``core.llm.chat_json_repairable``: when a model output breaks one of the
data-contract invariants that structural validation alone cannot catch, the
check returns a non-empty problem list, which triggers the existing bounded
repair attempt and (on repeated failure) the existing safe
``LLMResponseError``.

The helpers never log or return patient text; problem strings are fixed
English labels. They take a *source* string (the patient's raw text for
extraction, or the patient's answer for a merge) and/or the candidate record
dict, and return a list of problem strings (empty list = OK).

Conventions enforced (see ``docs/data_contract.md``):
- ``complaint`` is a verbatim, contiguous excerpt of the patient's text.
- ``severity`` is set only when the patient explicitly says mild/moderate/severe;
  descriptive adjectives ("bad", "really bad") do not map to a severity level.
- ``severity_note`` describes impact/pattern and must not duplicate a symptom.
- An uncertain/hedged statement ("I don't think I have allergies") is NOT an
  explicit denial: the matching ``*_denied`` flag must stay null.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "SEVERITY_WORDS",
    "norm",
    "complaint_verbatim_problems",
    "severity_source_problems",
    "severity_note_duplication_problems",
    "uncertain_denial_problems",
]

SEVERITY_WORDS: tuple[str, ...] = ("mild", "moderate", "severe")

#: Explicit severity words the patient must use for a severity level to be set.

_UNCERTAINTY_MARKERS: tuple[str, ...] = (
    "i don't think",
    "i dont think",
    "i think",
    "i'm not sure",
    "im not sure",
    "i am not sure",
    "not sure",
    "maybe",
    "probably",
    "possibly",
    "i guess",
    "i suppose",
    "i believe",
    "might be",
    "could be",
    "as far as i know",
)

#: Topic patterns used to locate a denial field's subject in the source text,
#: so an uncertainty marker can be checked in a window around it. Matched
#: case-insensitively against the normalized source.
_DENIAL_TOPICS: dict[str, tuple[str, ...]] = {
    "allergies_denied": (r"allerg", r"allergic"),
    "medicines_denied": (
        r"\bmedic",
        r"tablet",
        r"pill",
        r"herbal",
        r"supplement",
        r"taking",
        r"\btake\b",
        r"on any",
        r"\bnothing\b",
        r"\bnone\b",
    ),
    "medical_history_denied": (
        r"history",
        r"condition",
        r"asthma",
        r"diabetes",
        r"illness",
        r"previously",
        r"\bpast\b",
        r"history of",
    ),
}

#: Minimum length for a substantial overlap between severity_note and a symptom
#: before it counts as duplication (avoids flagging short common words).
_DUP_MIN_LEN = 12

_SENTENCE_TERMINATORS = ".!?;\n"


def _sentence_around(text: str, pos: int) -> str:
    """Return the substring of ``text`` representing the sentence around pos."""
    starts = [text.rfind(t, 0, pos) for t in _SENTENCE_TERMINATORS]
    start = max(starts) + 1 if max(starts) != -1 else 0
    ends = [text.find(t, pos) for t in _SENTENCE_TERMINATORS]
    ends = [e for e in ends if e != -1]
    end = min(ends) if ends else len(text)
    return text[start:end]


def norm(text: str) -> str:
    """Casefold and collapse all whitespace to single spaces."""
    return " ".join(text.casefold().split())


def _has_severity_word(source_norm: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", source_norm) for w in SEVERITY_WORDS)


def complaint_verbatim_problems(complaint: Any, source_norm: str) -> list[str]:
    """Flag a ``complaint`` that is not a contiguous excerpt of the source."""
    if not isinstance(complaint, str) or not complaint.strip():
        return []
    if norm(complaint) not in source_norm:
        return [
            "complaint must be a verbatim, contiguous excerpt of the patient's "
            "text, not a paraphrase or summary"
        ]
    return []


def severity_source_problems(severity: Any, source_norm: str) -> list[str]:
    """Flag a non-null ``severity`` not backed by an explicit severity word."""
    if severity is None:
        return []
    if not _has_severity_word(source_norm):
        return [
            "severity must be null unless the patient explicitly says mild, "
            "moderate, or severe; descriptive words like 'bad' or 'really bad' "
            "are not severity levels"
        ]
    return []


def severity_note_duplication_problems(severity_note: Any, symptoms: Any) -> list[str]:
    """Flag a ``severity_note`` that restates a symptom entry."""
    if not isinstance(severity_note, str) or not severity_note.strip():
        return []
    if not isinstance(symptoms, list):
        return []
    note_norm = norm(severity_note)
    for symptom in symptoms:
        if not isinstance(symptom, str) or not symptom.strip():
            continue
        sym_norm = norm(symptom)
        if note_norm == sym_norm:
            return [
                "severity_note duplicates a symptom; keep it for impact or "
                "pattern only, or leave it null"
            ]
        shorter = note_norm if len(note_norm) < len(sym_norm) else sym_norm
        if len(shorter) >= _DUP_MIN_LEN and (
            note_norm in sym_norm or sym_norm in note_norm
        ):
            return [
                "severity_note overlaps a symptom; keep it for impact or "
                "pattern only, or leave it null"
            ]
    return []


def _uncertain_denial_for(
    flag_key: str, flag_value: Any, source_norm: str
) -> str | None:
    """Return a problem string if a denied flag is true on an uncertain source.

    Uncertainty is checked within the same sentence as the topic word, so an
    unrelated "maybe" in a neighbouring sentence does not turn a clear denial
    ("I have no allergies") into an uncertain one.
    """
    if flag_value is not True:
        return None
    patterns = _DENIAL_TOPICS.get(flag_key, ())
    for pattern in patterns:
        for match in re.finditer(pattern, source_norm):
            sentence = _sentence_around(source_norm, match.start())
            if any(marker in sentence for marker in _UNCERTAINTY_MARKERS):
                return (
                    f"{flag_key} is true but the patient was uncertain about "
                    "that topic; an uncertain statement is not an explicit "
                    "denial, so leave the flag null"
                )
    return None


def uncertain_denial_problems(
    data: dict, source_norm: str, *, only_keys: tuple[str, ...] | None = None
) -> list[str]:
    """Flag any ``*_denied`` flag set to true on a hedged/uncertain source.

    ``only_keys`` restricts the check to specific flag keys (used by the merge
    step to check only flags that just became true). When omitted, all three
    denial flags are checked.
    """
    keys = only_keys or tuple(_DENIAL_TOPICS.keys())
    problems: list[str] = []
    for key in keys:
        problem = _uncertain_denial_for(key, data.get(key), source_norm)
        if problem:
            problems.append(problem)
    return problems
