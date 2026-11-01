"""Rule-based attention alerts.

Owned by Person 1. Interface defined in ``docs/data_contract.md`` (section 6).
"""

from __future__ import annotations

from core.schema import Alert, PatientRecord

__all__ = ["check_alerts"]


def check_alerts(record: PatientRecord) -> list[Alert]:
    """Return deterministic, rule-based attention flags for the record.

    Contract (docs/data_contract.md, section 6.4):
    - Pure and deterministic: same record in, same alerts out. No LLM.
    - Alerts only surface patient-reported content that may need the
      doctor's attention (e.g. breathing difficulty, chest pain, heavy
      bleeding -> ``level="urgent"``; a listed allergy together with a newly
      mentioned medicine -> ``level="attention"``).
    - Messages are safe English: no diagnosis, no treatment advice, no
      rewording that changes the patient's meaning.
    - Order is stable: urgent alerts first, then by rule code.
    """
    raise NotImplementedError(
        "core.alerts.check_alerts is not implemented yet "
        "(see docs/data_contract.md)"
    )
