"""Limited precautionary red-flag alerts (rule-based, no AI).

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (v0.3,
section 6).

Sources consulted before defining triggers and messages (accessed 2026-11-01):

- Ministry of Health of the Republic of Indonesia (Kemenkes RI), official
  portal and public health education on danger signs ("tanda bahaya"),
  including maternal danger signs: https://www.kemkes.go.id/
- Kemenkes PSC 119 — the national emergency medical call center (number 119):
  https://psc119.kemkes.go.id/
- Indonesian Pediatric Society (IDAI / Ikatan Dokter Anak Indonesia),
  recommendations and consensus guidelines on child danger signs and early
  referral: https://www.idai.or.id/
- WHO Integrated Management of Childhood Illness (IMCI) danger signs for
  immediate referral (fast breathing / chest indrawing, stridor at rest,
  unable to drink or breastfeed, convulsions, lethargy or unconsciousness):
  https://www.who.int/

Design rules:

- The triggers are a limited, conservative subset of the guidance above,
  expressed for English patient-reported text. They are precautionary flags,
  not diagnoses and not triage.
- Negated mentions ("no chest pain", "without difficulty breathing") and
  clearly historical mentions ("had a seizure as a child", "last year") do
  not raise alerts.
- The absence of an alert is NOT a statement of safety. No alert message (and
  no caller, including the UI) may present "no alerts" as proof that the
  patient is safe.
- All messages are in English. Urgent messages reference the Indonesian
  emergency number 119 (PSC 119).
- This module never calls the LLM or the network: it is pure rule code so it
  can run before (and independently of) any slow API call, including when the
  ModelScope API is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.schema import Alert, PatientRecord

__all__ = ["check_alerts", "scan_text"]

_EMERGENCY_TAIL = (
    " In Indonesia, emergency medical services can be reached on 119. "
    "Please seek medical care now or tell the doctor immediately."
)


@dataclass(frozen=True)
class _Trigger:
    code: str
    level: str
    patterns: tuple[str, ...]
    message: str


_TEXT_TRIGGERS: tuple[_Trigger, ...] = (
    _Trigger(
        "breathing_difficulty",
        "urgent",
        (
            r"difficult(y|ies) (to |in )?breath",
            r"trouble (to )?breath",
            r"shortness of breath",
            r"breathless",
            r"can'?t breathe",
            r"cannot breathe",
            r"hard to breathe",
            r"chest indrawing",
            r"stridor",
        ),
        "You reported difficulty breathing. This may need urgent medical "
        "attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "chest_pain",
        "urgent",
        (
            r"chest pain",
            r"pain in (my|his|her|the) chest",
            r"pain (in|over) (my|his|her|the) chest",
            r"tight(ness)? (in|of) (my|his|her|the) chest",
            r"pressure (on|in|over) (my|his|her|the) chest",
        ),
        "You reported chest pain. This may need urgent medical attention."
        + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "heavy_bleeding",
        "urgent",
        (
            r"(heavy|severe|profuse|uncontrolled).{0,25}bleed",
            r"bleed(ing)? (heavily|a lot|so much|that (won'|wouldn't|will not) stop)",
            r"vomiting blood",
            r"vomit(ed|ing)? (up )?blood",
            r"coughing (up )?blood",
            r"blood (in|from|in my|in the) (stool|vomit|urine)",
            r"passing blood",
        ),
        "You reported significant bleeding. This may need urgent medical "
        "attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "allergic_reaction",
        "urgent",
        (
            r"(swollen|swelling).{0,30}(lips?|tongue|throat|face|eyes?|mouth)",
            r"(lips?|tongue|throat|face|eyes?|mouth) .{0,20}(swollen|swelling)",
            r"throat (tight|closing)",
            r"difficulty (to )?swallow",
            r"hard to swallow",
            r"can'?t swallow",
        ),
        "You reported swelling of the face, lips, tongue, or throat, or "
        "trouble swallowing. This can be a sign of a severe allergic reaction "
        "that may need urgent medical attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "seizure",
        "urgent",
        (r"seizure", r"convulsion"),
        "You reported a seizure or convulsion. This may need urgent medical "
        "attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "altered_consciousness",
        "urgent",
        (
            r"unconscious",
            r"pass(ed|ing)? out",
            r"faint(ed|ing)?",
            r"black(ed)? out",
            r"confus",
            r"letharg",
            r"hard to wake",
            r"difficult(y|ies)? (to )?wake",
            r"not (really )?aware",
        ),
        "You reported fainting, confusion, or difficulty staying awake. This "
        "may need urgent medical attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "cannot_drink",
        "urgent",
        (
            r"can'?t drink",
            r"cannot drink",
            r"unable to drink",
            r"won'?t drink",
            r"refus(es|ed|ing) (to )?drink",
            r"not drink(ing)?",
            r"refus(es|ed|ing) (to )?breastfeed",
            r"not breastfeed(ing)?",
        ),
        "You reported that the patient cannot or is refusing to drink or "
        "breastfeed. In children this is a recognized danger sign that needs "
        "urgent medical attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "neck_stiffness",
        "urgent",
        (
            r"stiff neck",
            r"neck (is )?stiff",
            r"can'?t (touch|bend) (my |his |her )?chin",
            r"cannot (touch|bend) (my |his |her )?chin",
        ),
        "You reported a stiff neck. Especially with fever or headache, this "
        "can need urgent medical attention." + _EMERGENCY_TAIL,
    ),
    _Trigger(
        "high_fever",
        "attention",
        (
            r"fever of (39|40)",
            r"temperature (of |reaching )?(39|40)",
            r"high fever",
        ),
        "You reported a high fever. Please make sure to tell your doctor "
        "about this during the visit.",
    ),
    _Trigger(
        "persistent_vomiting",
        "attention",
        (
            r"vomit(ed|ing)? (all day|the whole day|multiple times|several "
            r"times|over and over|continuously|constantly)",
            r"(can'?t|cannot) keep (anything|food|water) down",
        ),
        "You reported repeated vomiting. Please make sure to tell your doctor "
        "about this during the visit.",
    ),
)

# Conditional triggers (need record context), not part of _TEXT_TRIGGERS.
_FEVER_PATTERNS = (
    r"fever",
    r"febrile",
    r"temperature (of |reaching )?3[89]",
    r"temperature (of |reaching )?40",
)
_MSG_INFANT_FEVER = (
    "The patient is under one year old and you reported a fever. Fever in an "
    "infant this young needs urgent medical attention." + _EMERGENCY_TAIL
)

_PREGNANCY_PATTERNS = (r"pregnan",)
_PREGNANCY_COFACTOR_CODES = {
    "heavy_bleeding",
    "breathing_difficulty",
    "seizure",
    "altered_consciousness",
    "high_fever",
}
_PREGNANCY_EXTRA_PATTERNS = (r"severe headache", r"severe abdominal pain")
_MSG_PREGNANCY_DANGER = (
    "You reported pregnancy together with bleeding, severe headache, severe "
    "abdominal pain, difficulty breathing, convulsions, or high fever. These "
    "are recognized pregnancy danger signs that need urgent medical "
    "attention." + _EMERGENCY_TAIL
)

_NEGATIONS = {
    "no",
    "not",
    "without",
    "never",
    "none",
    "denies",
    "don't",
    "dont",
    "didn't",
    "doesn't",
    "hasn't",
    "haven't",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "won't",
    "cannot",
    "cant",
}

_PAST_MARKERS = (
    "used to",
    "as a child",
    "as a baby",
    "years ago",
    "year ago",
    "last year",
    "previous",
    "previously",
    "history of",
    "in the past",
    "childhood",
    "grew up",
    "when i was",
    "when he was",
    "when she was",
    "back then",
    "long ago",
)


def _is_negated(text: str, pos: int) -> bool:
    """True when a negation word appears in the few words before the match."""
    prefix = text[max(0, pos - 40) : pos]
    words = re.findall(r"[A-Za-z']+", prefix)
    if not words:
        return False
    return any(w.lower() in _NEGATIONS for w in words[-4:])


def _is_historical(text: str, pos: int) -> bool:
    """True when the sentence around the match marks it as remote history."""
    starts = [text.rfind(p, 0, pos) for p in ".!?\n;"]
    start = max(starts) + 1  # all -1 (no terminator before) -> 0
    ends = [text.find(p, pos) for p in ".!?\n;"]
    ends = [e for e in ends if e != -1]
    end = min(ends) if ends else len(text)
    sentence = text[start:end].lower()
    return any(re.search(rf"\b{re.escape(m)}\b", sentence) for m in _PAST_MARKERS)


def _find_live(text: str, patterns: tuple[str, ...]) -> bool:
    """True when any pattern matches without being negated or historical."""
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if _is_negated(text, match.start()):
                continue
            if _is_historical(text, match.start()):
                continue
            return True
    return False


def _scan(text: str) -> set[str]:
    triggered: set[str] = set()
    for trigger in _TEXT_TRIGGERS:
        for pattern in trigger.patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if _is_negated(text, match.start()):
                    continue
                if _is_historical(text, match.start()):
                    continue
                triggered.add(trigger.code)
                break
    return triggered


def _ordered(alerts: list[Alert]) -> list[Alert]:
    alerts.sort(key=lambda a: (0 if a.level == "urgent" else 1, a.code))
    return alerts


def _record_text(record: PatientRecord) -> str:
    parts: list[str] = []
    if record.complaint:
        parts.append(record.complaint)
    parts.extend(record.symptoms)
    for attr in ("onset", "duration", "severity_note"):
        value = getattr(record, attr)
        if value:
            parts.append(value)
    for medicine in record.medicines:
        if medicine.name:
            parts.append(medicine.name)
        if medicine.notes:
            parts.append(medicine.notes)
    parts.extend(record.allergies)
    parts.extend(record.medical_history)
    parts.extend(record.concerns)
    return " . ".join(p for p in parts if p and p.strip())


def check_alerts(record: PatientRecord) -> list[Alert]:
    """Return deterministic precautionary alerts for a structured record.

    Urgent alerts first, then attention alerts, stable by code. The result
    never claims that the absence of an alert means the patient is safe.
    """
    text = _record_text(record)
    triggered = _scan(text)
    alerts = [
        Alert(code=t.code, message=t.message, level=t.level)
        for t in _TEXT_TRIGGERS
        if t.code in triggered
    ]
    if record.patient_age == 0 and _find_live(text, _FEVER_PATTERNS):
        alerts.append(Alert("infant_fever", _MSG_INFANT_FEVER, "urgent"))
    if _find_live(text, _PREGNANCY_PATTERNS) and (
        triggered & _PREGNANCY_COFACTOR_CODES
        or _find_live(text, _PREGNANCY_EXTRA_PATTERNS)
    ):
        alerts.append(Alert("pregnancy_danger", _MSG_PREGNANCY_DANGER, "urgent"))
    return _ordered(alerts)


def scan_text(*texts: str) -> list[Alert]:
    """Run the text-based triggers over raw strings (e.g. the patient's raw
    story) — useful before any API call, including when the API is
    unavailable. Record-context triggers (infant fever) need
    :func:`check_alerts` and are not covered here.
    """
    text = " . ".join(t for t in texts if t and t.strip())
    if not text:
        return []
    triggered = _scan(text)
    alerts = [
        Alert(code=t.code, message=t.message, level=t.level)
        for t in _TEXT_TRIGGERS
        if t.code in triggered
    ]
    if _find_live(text, _PREGNANCY_PATTERNS) and (
        triggered & _PREGNANCY_COFACTOR_CODES
        or _find_live(text, _PREGNANCY_EXTRA_PATTERNS)
    ):
        alerts.append(Alert("pregnancy_danger", _MSG_PREGNANCY_DANGER, "urgent"))
    return _ordered(alerts)
