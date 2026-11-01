"""Per-session state helpers for the VisitPrep UI.

Owned by Person 2. Session state holds the current record, the ordered list of
asked questions, the current step, any generated summary, and a request token
used to drop stale responses that arrive after Reset, Back, or a newer edit.

These are UI bookkeeping primitives only; there is no business logic here.
"""

from __future__ import annotations


def new_state() -> dict:
    """Return a fresh, empty session state."""
    return {
        "record": None,
        "asked": [],
        "step": 1,
        "summary": None,
        "summary_rev": -1,
        "rev": 0,
        "token": 0,
        "question": None,
    }


def touch(state: dict) -> int:
    """Increment the session request token and return the new value."""
    state["token"] += 1
    return state["token"]


def commit_if_current(state: dict, captured_token: int, new_state: dict) -> dict:
    """Return ``new_state`` unless a newer action already changed the token.

    If Reset, Back, or a newer edit bumped the token while a slow core call was
    in flight, ``state`` (the live session) no longer matches
    ``captured_token`` and the late result is dropped in favour of the current
    state.
    """
    if state.get("token") != captured_token:
        return state
    return new_state