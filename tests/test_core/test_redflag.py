"""Tests for core.redflag (rule-based alerts: triggers, negation, history).

Owned by Person 1. No network, no LLM — pure rule code.
"""

import pathlib

from core import redflag
from core.redflag import check_alerts, scan_text
from core.schema import PatientRecord


def _record(**kwargs) -> PatientRecord:
    return PatientRecord(**kwargs)


def codes(alerts) -> set[str]:
    return {a.code for a in alerts}


# --- triggers -----------------------------------------------------------------


def test_chest_pain_triggers_urgent_with_emergency_number():
    record = _record(symptoms=["chest pain when I breathe in"])
    alerts = check_alerts(record)
    assert "chest_pain" in codes(alerts)
    alert = next(a for a in alerts if a.code == "chest_pain")
    assert alert.level == "urgent"
    assert "119" in alert.message


def test_breathing_difficulty_triggers():
    alerts = scan_text("I have trouble breathing")
    assert "breathing_difficulty" in codes(alerts)


def test_heavy_bleeding_triggers():
    alerts = scan_text("I am bleeding heavily from a cut on my arm")
    assert "heavy_bleeding" in codes(alerts)


def test_allergic_swelling_triggers():
    alerts = scan_text("my lips are swollen after eating peanuts")
    assert "allergic_reaction" in codes(alerts)


def test_seizure_triggers():
    alerts = scan_text("He had a seizure this morning")
    assert "seizure" in codes(alerts)


def test_altered_consciousness_triggers():
    alerts = scan_text("she fainted twice yesterday")
    assert "altered_consciousness" in codes(alerts)


def test_cannot_drink_triggers():
    alerts = scan_text("the baby won't drink the breast milk")
    assert "cannot_drink" in codes(alerts)


def test_high_fever_is_attention_not_urgent():
    alerts = scan_text("I have a high fever")
    alert = next(a for a in alerts if a.code == "high_fever")
    assert alert.level == "attention"
    assert "119" not in alert.message


def test_persistent_vomiting_is_attention():
    alerts = scan_text("I have been vomiting multiple times")
    alert = next(a for a in alerts if a.code == "persistent_vomiting")
    assert alert.level == "attention"


def test_infant_fever_needs_record_context():
    infant = _record(patient_age=0, symptoms=["fever since this morning"])
    assert "infant_fever" in codes(check_alerts(infant))
    adult = _record(patient_age=30, symptoms=["fever since this morning"])
    assert "infant_fever" not in codes(check_alerts(adult))
    # scan_text has no age context: it must not invent the infant alert
    assert "infant_fever" not in codes(scan_text("fever since this morning"))


def test_pregnancy_danger_signs():
    record = _record(
        medical_history=["pregnancy (32 weeks)"],
        symptoms=["bleeding heavily since this morning"],
    )
    alerts = check_alerts(record)
    assert "pregnancy_danger" in codes(alerts)
    assert "heavy_bleeding" in codes(alerts)


def test_pregnancy_alone_does_not_alert():
    record = _record(medical_history=["pregnancy (10 weeks)"], symptoms=["tired"])
    assert "pregnancy_danger" not in codes(check_alerts(record))


# --- negation & historical handling ---------------------------------------------


def test_negated_mentions_do_not_trigger():
    assert "chest_pain" not in codes(scan_text("I have no chest pain"))
    assert "chest_pain" not in codes(scan_text("I do not have chest pain."))
    assert "breathing_difficulty" not in codes(scan_text("no difficulty breathing"))
    assert "breathing_difficulty" not in codes(scan_text("I can breathe without trouble"))
    assert "seizure" not in codes(scan_text("no history of seizures"))
    assert "chest_pain" not in codes(check_alerts(_record(symptoms=["no chest pain, just sore muscles"])))


def test_historical_mentions_do_not_trigger():
    assert "seizure" not in codes(scan_text("I had a seizure as a child"))
    assert "seizure" not in codes(scan_text("She had convulsions last year"))
    assert "seizure" not in codes(scan_text("history of seizures in childhood"))
    assert "chest_pain" not in codes(scan_text("he had chest pain years ago after an operation"))


def test_present_tense_still_triggers():
    assert "seizure" in codes(scan_text("He had a seizure this morning"))
    assert "seizure" in codes(scan_text("the seizures started last night"))


# --- safety & determinism --------------------------------------------------------


def test_benign_text_produces_no_alerts():
    assert scan_text("I have a mild headache and a little tiredness") == []
    assert check_alerts(_record(symptoms=["mild headache"])) == []


def test_messages_never_claim_safety():
    for trigger in redflag._TEXT_TRIGGERS:
        assert "safe" not in trigger.message.lower()
        assert "no danger" not in trigger.message.lower()
        assert trigger.message.isascii(), trigger.code
    assert "safe" not in redflag._MSG_INFANT_FEVER.lower()
    assert "safe" not in redflag._MSG_PREGNANCY_DANGER.lower()


def test_deterministic_and_urgent_first():
    record = _record(symptoms=["high fever", "chest pain"])
    first = check_alerts(record)
    second = check_alerts(record)
    assert [a.code for a in first] == [a.code for a in second]
    levels = [a.level for a in first]
    assert levels == sorted(levels, key=lambda l: 0 if l == "urgent" else 1)
    assert first[0].level == "urgent"


def test_redflag_has_no_ai_dependency():
    source = pathlib.Path(redflag.__file__).read_text(encoding="utf-8")
    assert "core.llm" not in source
    assert "urllib" not in source
    assert "requests" not in source


def test_scan_text_empty_is_empty():
    assert scan_text("") == []
    assert scan_text() == []
