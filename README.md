# VisitPrep

VisitPrep helps patients prepare for a doctor visit by organizing what they
report about their symptoms. It is **not** a diagnostic tool and does **not**
give medical advice or recommend treatment.

All labels, examples, questions, errors, summaries, and PDFs are in **English**.

## Flow

1. **Describe symptoms** — the patient describes symptoms in their own words.
2. **Follow-up questions** — up to five clarifying questions are asked.
3. **Review & edit** — the patient reviews and edits the collected details.
4. **Output** — a doctor summary, a short patient script, and a downloadable PDF.

VisitPrep only organizes patient-reported information. No database, no login, no
model downloads, no training, and no fine-tuning.

## Deployment

Target: [ModelScope Studio](https://www.modelscope.cn/studios) free CPU tier.
`gradio` runs the app on CPU; `reportlab` generates the PDF.

## Project layout

```
app.py               # Gradio Blocks entry point          (Person 2)
core/                # Domain logic + PDF generation      (Person 1)
ui/                  # Gradio layouts & app glue          (Person 2)
tests/test_core/     # Core tests                         (Person 1)
tests/test_ui/       # UI checks                          (Person 2)
docs/data_contract.md# Field contract between core/ and ui/
docs/prompt_log.md   # Log of actual prompt iterations
data/                # Generated patient files (git-ignored)
```

See `AGENTS.md` for ownership rules.

## Run locally

```bash
python -m venv .venv
# activate the venv (Windows)
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open the URL printed by Gradio (default `http://0.0.0.0:7860`).

## Test

```bash
python -m pytest -q
```

## Environment

Copy `.env.example` to `.env` to change the server host, port, or follow-up
question limit. `.env` is git-ignored.

## Privacy

VisitPrep does not store patient data. Generated summaries and PDFs are written
to the local `data/` directory, which is excluded from Git.