# Prompt log

Record of actual prompts issued in this approved coding session, with their
outcomes. Append one entry per task / iteration.

## 1. Scaffold + welcome screen (initial)

**Prompt:** Create the scaffold for VisitPrep, an English-language doctor-visit
preparation app using Python and Gradio Blocks. Flow: describe symptoms → up to
five follow-up questions → review/edit details → doctor summary, short patient
script, and PDF download. All output in English; organize patient-reported
information only (no diagnosis or treatment). No database, login, training,
fine-tuning, or local model downloads. Deploy to ModelScope Studio free CPU.
Create `app.py`, `core/`, `ui/`, `tests/`, `data/`, `docs/`, `requirements.txt`,
`.env.example`, `.gitignore`, and `README.md`. Exclude secrets, `.env`, virtual
environments, caches, and generated patient files from Git. Create `AGENTS.md`
with Person 1 / Person 2 ownership and the listed process rules. Create only the
scaffold and a minimal runnable welcome screen in this step.

**Outcome:** Created the full scaffold and a minimal runnable Gradio welcome
screen. Core and UI logic remain unimplemented (stubs only), as directed.