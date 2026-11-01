# AGENTS.md — VisitPrep working agreements

## Ownership

- **Person 1** owns `core/` and the core tests (`tests/test_core/`).
- **Person 2** owns `app.py`, `ui/`, the UI checks (`tests/test_ui/`), and
  deployment.

## Process

- Read `AGENTS.md` and `docs/data_contract.md` (when present) before starting
  any subsequent task.
- Preserve the other person's files. If a change requires modifying the other
  person's code, do not edit it directly — report the required cross-owner
  change instead.
- Generate implementation code through this approved coding session.
  Keep `docs/prompt_log.md` updated with the actual prompt iterations.
- Run the relevant checks and report their actual results after each task.
- Always ask for clarification if any part of a prompt is unclear or ambiguous.