# VisitPrep

VisitPrep helps patients prepare for a doctor visit by organizing what they
report about their symptoms. It is **not** a diagnostic tool and does **not**
give medical advice or recommend treatment.

All labels, examples, questions, errors, summaries, and PDFs are in **English**.

## Flow

1. **Describe symptoms** — the patient describes symptoms in their own words,
   plus optional age and sex. No name is collected or sent to the model.
2. **Follow-up questions** — up to five clarifying questions, one at a time,
   with progress, **Skip**, and **Finish early**.
3. **Review & edit** — symptoms, medicines, allergies/history, and concerns,
   then confirm the record.
4. **Output** — a doctor card, a short patient script, priority questions, and
   a PDF download control.

VisitPrep only organizes patient-reported information. No diagnosis, no
treatment advice, no database, no login, no model downloads, no training, and
no fine-tuning. The only external call is the ModelScope inference API.

## Preview mode (fictional fixtures)

The backend is chosen once at startup by the `VISITPREP_PREVIEW` environment
variable (default **off**):

- `VISITPREP_PREVIEW=1` — the clearly-labeled *preview backend* serves the
  fictional fixtures in `core/fixtures.py` plus fixed, clearly-fictional
  placeholder questions and summary text. No API key is required. A preview
  banner is shown on every step, and the alert area shows "Alerts unavailable
  in preview".
- unset (default) — the real core modules are used. Because
  `core/extraction.py`, `core/questions.py`, `core/alerts.py`, and
  `core/summary.py` are not implemented yet, the app shows a clear English
  error instead of fake output until they land.

```bash
# Windows PowerShell
$env:VISITPREP_PREVIEW = "1"; python app.py
# macOS / Linux
VISITPREP_PREVIEW=1 python app.py
```

The **PDF export is a separate core interface** (see `docs/data_contract.md`
section 3); the download control is shown but disabled, and the PDF library
(e.g. reportlab) will be chosen when that interface is implemented.

## Deployment

Target: [ModelScope Studio](https://www.modelscope.cn/studios) free CPU tier.
`gradio` runs the app on CPU. The PDF export library is not pinned yet and will
be chosen when the PDF interface is implemented.

## Project layout

```
app.py               # Gradio Blocks entry point          (Person 2)
core/                # Domain logic (extraction, questions, alerts, summary)
ui/                  # Gradio layouts, state glue, preview backend (VISITPREP_PREVIEW=1)
tests/test_core/     # Core tests                         (Person 1)
tests/test_ui/       # UI checks                          (Person 2)
docs/data_contract.md# Field contract between core/ and ui/
docs/prompt_log.md   # Log of actual prompt iterations
data/                # Generated patient files (git-ignored)
```

See `AGENTS.md` for ownership rules.

## Run locally

```bash
git clone <repo-url> && cd visitprep-competition
python -m venv .venv
# activate the venv (Windows PowerShell)
.venv\Scripts\Activate.ps1
# activate the venv (macOS / Linux)
# source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open the URL printed by Gradio (default `http://0.0.0.0:7860`). On its
own the app shows a clear error until the core pipeline lands; set
`VISITPREP_PREVIEW=1` (see above) to exercise the flow with fictional fixtures,
no `MODELSCOPE_API_KEY` needed.

## Test

```bash
python -m pytest -q
```

## Environment

Copy `.env.example` to `.env` to change the server host, port, or follow-up
question limit. The LLM (`MODELSCOPE_API_KEY` / `MODELSCOPE_MODEL`) is only
read by `core/llm.py` and is not needed for the fixture preview.
`VISITPREP_PREVIEW` must be set in the server environment (not `.env`), since
`ui/backend.py` reads it once at startup. `.env` is git-ignored.

## Privacy

Notes you submit are sent to ModelScope for processing; please omit identifying
details such as your name, address, or phone number. VisitPrep does not claim
that a provider deletes submitted data, and closing the browser tab does not
remove data immediately. The app itself keeps no database of patient records.