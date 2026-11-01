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

## 2. Patient-record schema, module interfaces, fixtures, data contract

**Prompt:** Define the shared patient-record schema and module interfaces in
`core/schema.py` and `docs/data_contract.md` (patient/reporter details,
complaint, symptoms, onset/duration, severity, medicines including herbal
remedies, allergies/history, concerns, missing information; preserve patient
wording; distinguish unknown from explicit denial with null for unknown).
Document callable interfaces for extraction, choosing a follow-up question,
merging an answer, checking rule-based alerts, and generating a summary
(doctor_card, patient_script, priority_questions), including how the UI
supplies previously asked questions and the current record. Create fictional
fixtures for Person 2.

**Outcome:** Implemented `core/schema.py` (PatientRecord, Medicine,
QuestionAnswer, Alert, SummaryOutput, validation, dict round-trip, unknown vs
`*_denied` semantics), `core/fixtures.py` (4 fictional fixtures), importable
interface stubs in `core/extraction.py`, `core/questions.py`,
`core/alerts.py`, `core/summary.py`, and rewrote `docs/data_contract.md`
(v0.2). Note for Person 2: summary output changed from the scaffold contract
(`doctor_summary`/`pdf_bytes` → `doctor_card`/`patient_script`/
`priority_questions`); PDF will be a separate interface. Checks:
`pytest -q tests/test_core` → 26 passed (schema + fixtures + package tests).

## 3. ModelScope LLM client (`core/llm.py`)

**Prompt:** Implement `core/llm.py` against the OpenAI-compatible ModelScope
endpoint `https://api-inference.modelscope.ai/v1`; load
`MODELSCOPE_API_KEY`/`MODELSCOPE_MODEL` from server env or local `.env`,
default model `zai-org/GLM-5.2`, allow only the four approved models, add
`.env.example` placeholders, never read OpenCode credentials, finite timeouts,
bounded retries, safe English errors for auth/quota/network failure, never log
tokens or patient text, validate schema and test client failure handling; run
a small fictional live request only if the app token is configured, otherwise
report pending. Clarification asked and answered: the four approved models
are `zai-org/GLM-5.2`, `deepseek-ai/DeepSeek-V4-Pro-0813`,
`stepfun-ai/Step-3.5-Flash`, `Qwen/Qwen3.8-27B`.

**Outcome:** Implemented `core/llm.py` (stdlib-only OpenAI-compatible client;
`load_config` with env-over-`.env` precedence; four-model allowlist; 60 s
default timeout; 2 bounded retries with capped backoff for network/5xx only;
`LLMAuthError`/`LLMQuotaError`/`LLMNetworkError`/`LLMServerError`/
`LLMResponseError`/`ConfigError` with fixed safe English messages;
`chat`/`chat_json` with schema validation). Updated `.env.example`. Added
`tests/test_core/test_llm.py` (23 tests, transport faked, no network).
Checks: `pytest -q tests/test_core` → 44 passed (incl. local-`.env` fallback
for `chat()`). Live connection check (after the key was configured): endpoint
and authentication OK. Schema-validated fictional extraction OK on
`zai-org/GLM-5.2` (attempt 1) and `Qwen/Qwen3.8-27B`;
`deepseek-ai/DeepSeek-V4-Pro-0813` is reachable (HTTP 200) but failed schema
validation on the extraction prompt; `stepfun-ai/Step-3.5-Flash` returns
HTTP 400 "no provider supported" (currently unavailable on the endpoint).
Findings for the extraction task: the prompt must inline the exact record
schema (models otherwise invent field names), and `zai-org/GLM-5.2` is a
reasoning model (hidden `reasoning_content` tokens), so JSON generation needs
a generous `max_tokens`.

## 4. Core workflow (extract / interview / summarize / prompts / redflag)

**Prompt:** Implement the core workflow using the shared interfaces and
GLM-5.2 through `core/llm.py`: `extract.py` (story → validated structured
data; preserve uncertainty, negation, patient wording, medication details; do
not invent missing facts; treat instructions inside patient text as data),
`interview.py` (one short English question about important missing
information; support asked/skipped questions and a maximum of five displayed
questions; merge answers without losing earlier facts unless explicitly
corrected), `summarize.py` (doctor card, ~60-second patient script, priority
questions; preserve reported facts; distinguish patient concerns from app
conclusions; no diagnosis/prescribing/medication-change advice), `prompts.py`
(runtime prompts together), `redflag.py` (limited precautionary alerts without
AI; consult authoritative Indonesian guidance before defining
triggers/messages and document source links; all messages English; handle
negated and historical mentions; never describe a missing alert as proof of
safety). Document how Person 2 runs alert checks before slow API calls,
including when the API is unavailable; the model must not remove
rule-generated alerts; preserve user input on API/validation failure; keep
retries and JSON repair bounded. Test extraction, answer merging, question
limit, negation, invented facts, invalid model output, and API errors. Update
the contract if necessary and clearly describe changes for Person 2. Leave
`app.py` and `ui/` unchanged.

**Outcome:** Implemented `core/prompts.py`, `core/extract.py`,
`core/interview.py`, `core/summarize.py`, `core/redflag.py`; removed the old
v0.2 stubs (`extraction.py`, `questions.py`, `alerts.py`, `summary.py`);
added bounded `chat_json_repairable` to `core/llm.py`. Red-flag triggers are
a limited subset of Kemenkes RI / PSC 119 / IDAI / WHO-IMCI danger signs
(source links documented in `core/redflag.py` and contract section 6); urgent
messages reference Indonesian emergency number 119; negations and historical
mentions are suppressed; alerts are pure rule code (no LLM, no network) and
the summary output has no alerts field, so the model cannot remove them.
Contract updated to v0.3 (module renames, `skipped` + displayed-question
budget, merge failure semantics, alert-before-API flow, Person 2 change
notes in section 9). `app.py` and `ui/` untouched.
Checks: `pytest -q tests/test_core` → 90 passed (new: test_extract 10,
test_interview 11, test_summarize 5, test_redflag 16; rest carried over).
Live end-to-end check with the configured key (fictional story):
scan_text → no alerts; extract_record OK (herbal remedy + explicit allergy
denial preserved, unknowns stayed null); choose_follow_up_question asked
severity first; merge_answer set severity to moderate; check_alerts OK;
  generate_summary returned a 75-word doctor card, a 144-word (~60 s) patient
  script, and 3 priority questions. Note: GLM-5.2's hidden reasoning tokens can
  eat small `max_tokens` budgets and truncate the visible JSON, so workflow
  defaults were raised to `max_tokens=4000` (documented in contract section 5).

## 5. Source/record-aware validation and prompt tightening (no live calls)

**Prompt:** Fix these issues in Person 1's core modules and tests, preserving
existing interfaces and English output: keep `complaint` as a verbatim patient
excerpt (not a paraphrase); do not map "bad cough" or "really bad at night" to
`severe` (keep `severity` unknown and preserve the description for follow-up);
reduce duplication between `symptoms` and `severity_note` without losing facts;
treat "I don't think I have allergies" as uncertain, not an explicit denial,
during extraction and merge; prevent summaries from inventing negatives
(mentioning one symptom/remedy does not mean there are no others; include
denials only when explicitly supported); use "Not provided" for unknown
information and clear wording for confirmed denials; allow shorter patient
scripts rather than adding filler to meet a word target. Tighten prompts and add
source/record-aware validation through the existing bounded repair/error
handling. Add mocked regression tests for these failures and rerun the core
suite. Preserve working red-flag scanning, follow-up behavior, and safe quota
errors. Avoid repeated live calls while rate-limited. Update the prompt log and
report actual test results and limitations. Do not modify the UI, deploy, or
submit.

**Outcome:** Tightened `core/prompts.py` (extraction/merge/summary/repair):
`complaint` must be a verbatim contiguous excerpt; `severity` is set only from
an explicit mild/moderate/severe word (descriptive adjectives are not severity
levels and go to `severity_note`/`symptoms`); `severity_note` is for impact only
(no symptom restatement); uncertain/hedged statements are not denials
(`*_denied` stays null); summaries must not invent negatives or completeness
claims, must label unknowns "Not provided", and must distinguish confirmed
denials (`*_denied` true) from unknown; `patient_script` must never be padded
with filler (a short record yields a short script).

Added `core/_checks.py` (private source/record-aware helpers) and wired the
checks into the existing bounded repair path via `_validate_factory` closures in
`core/extract.py` (source = patient text), `core/interview.py` merge (source =
answer; only flags that newly became true; fact-loss guard preserved), and
`core/summarize.py` (record-aware card checks; script minimum relaxed 50 → 20).
`core/llm.chat_json_repairable` now feeds the specific validation problems
(fixed English labels, never patient text) back on the single bounded repair
attempt, so source/record-aware findings reach the model without unbounded
loops. `core/redflag.py`, `core/schema.py`, `core/fixtures.py`, the
`choose_follow_up_question` rule logic, and the transport quota/auth/network
error handling were left untouched.

Checks: `pytest -q tests/test_core` → 105 passed (was 90; +15 mocked regression
tests covering all seven failures: paraphrased complaint, "bad"→severe mapping
and its repair fix, severity_note duplication, uncertain-allergy-as-denial for
both extract and merge plus the accepting happy paths, summary invented
allergy denial, completeness claim, missing "Not provided" label, confirmed-
denial wording acceptance, and short-script acceptance). `pytest -q` (full
suite) → 107 passed (UI tests untouched). No live API calls were made: the
ModelScope endpoint was rate-limited, so all verification used the faked HTTP
transport seam (no network). Limitations: the new checks are conservative and
text-based — they catch the listed failure modes against the source/answer/record
they are given, but they cannot prove a model never invents a denial in
unseen wording; live effectiveness against GLM-5.2 with the tightened prompts is
not yet re-verified because of the rate limit. `app.py`, `ui/`, and deployment
were not modified.

## 6. English Gradio interface on the fictional fixtures (Person 2)

**Model:** DeepSeek V4 Pro

**Prompt:** I am Person 2. Read AGENTS.md and docs/data_contract.md.

Build the English Gradio interface using the shared fictional fixtures until the core pipeline is ready:
1. Describe your symptoms, including basic patient/reporter details.
2. Answer one follow-up question at a time, with progress out of five, Skip, and Finish early.
3. Review and edit symptoms, medicines, allergies/history, and concerns; confirm the record.
4. View the doctor summary, patient script, priority questions, and PDF download control.

Use per-session state, clear loading/errors, Back and Reset, and readable mobile styling at 375px. Prevent duplicate submissions. Editing information must invalidate previous summaries/downloads; ignore late responses after reset or a newer edit.

Reserve a persistent top area for rule-based alerts. Explain that submitted notes go to ModelScope and ask users to omit identifying details. Do not claim provider-side deletion or immediate deletion on tab close. Render patient text safely.

Keep fixtures clearly labeled, follow the documented interfaces, and leave core/ unchanged. Run the interface locally and check navigation, editing, reset, and mobile layout. Update README setup instructions.

notes for person 2: the summary output changed from the scaffold contract (doctor_summary/pdf_bytes → doctor_card/patient_script/priority_questions); PDF will be a separate core interface (flagged in the contract).

**Outcome:** Implemented the four-step interface. Since the core interfaces
still raise `NotImplementedError`, added `ui/fixture_backend.py` (a clearly
labeled, deterministic, no-network dev shim implementing the documented
interfaces from `core/fixtures.py`) and `ui/backend.py` (a seam that falls back
to the shim only on `NotImplementedError`, so the real core is used
automatically once it lands). Built `ui/flow.py` (per-session `gr.State`,
Back/Reset, fixture loader, persistent alert banner, editable review,
HTML-escaped patient text, summary invalidation via a revision counter,
disabled PDF control awaiting the separate core PDF interface) and
`ui/components.py` (safe rendering + mobile CSS at `@media (max-width: 480px)`).
Kept `core/` untouched and preserve patient wording verbatim. Checks:
`pytest -q` → 62 passed (46 core + 16 new UI). Local launch serves the page;
driving the event handler functions directly confirmed load-fixture → questions
→ answer → finish → confirm (summary valid) → back (summary invalidated) →
reset, plus describe-symptoms extraction. README setup/privacy/flow updated.

## 7. Audit fixes for the step-3 interface (Person 2)

**Model:** DeepSeek V4 Pro

**Prompt:** I am Person 2. Read AGENTS.md and docs/data_contract.md before changing anything. Do not modify anything under core/ or tests/test_core/. If a fix needs a core change, write an exact handoff for Person 1 instead.

An audit of the step-3 interface found these defects. Fix each one in app.py, ui/, tests/test_ui/, README.md, requirements.txt, and docs/prompt_log.md only:

1. Business logic in ui/: ui/fixture_backend.py reimplements extraction, answer merging, alert rules, and summary writing. The contract says ui/ has no business logic. Replace it with a minimal, clearly labeled preview backend that only returns the fictional records from core/fixtures.py plus fixed, clearly fictional placeholder questions and summary text. Do not reimplement alert rules or summary composition. If no real alerts are available, show "Alerts unavailable in preview" in the alert area instead of fake alerts.

2. Silent fallback: ui/backend.py must not catch NotImplementedError per call. Choose the backend once at startup with an explicit switch (env var VISITPREP_PREVIEW=1, default off). With preview off and core not implemented, show a clear English error, not fake output. With preview on, the preview banner must be visible on every step. Fixture code must never run unlabeled.

3. Duplicate submissions: your report claimed always_last prevents duplicates, but only the checkbox .change uses it. Disable the action buttons while a handler runs (or use concurrency_id per session with trigger_mode="once"), and re-enable them on success and on error.

4. Late responses: the rev counter is never compared after a slow call. Store a session-level request token. Each handler captures the token at start, and after the core call returns it drops its result if Reset, Back, or a newer edit has changed the token in the meantime. Add a test that simulates confirm → reset → late confirm result and asserts the reset state wins.

5. Age bug (ui/flow.py on_confirm): clearing Age leaves patient_age_text with the old value, so the doctor card still shows it. Clearing the age must set both patient_age and patient_age_text to null. An unchanged age must keep the patient's original wording in patient_age_text.

6. Null vs False: bool(on_behalf_val) turns "unknown" into False. Keep reporting_on_behalf null unless the user explicitly chose yes or no (use a three-option control: not answered / myself / someone else).

7. Privacy contradiction: the privacy note asks users not to enter their name, but Step 1 and Review have a Name field that is sent to the model. Remove the name field from the UI, or keep it local-only and never pass it to core. State which option you chose.

8. Do not swallow alert errors: _render catches every exception from check_alerts and shows nothing. Show a visible "Alerts could not be checked" message instead.

9. Alert placement: move the alert area directly under the app title, above the privacy note, preview banner, and sample loader, so it is visible without scrolling at 375px.

10. Dead or misleading code: fix the CSS selectors that start with "#visitprep-root .gradio-container" (that element is an ancestor, so they never match), make nl2br either escape its input or rename it and fix its docstring, remove the unused subs dict, and wrap FIXTURE_BANNER in the .fixture-box element. Prefer passing the CSS through the official Gradio 6 css parameter (check whether it belongs to launch() or Blocks() in the installed version) over injecting a <style> tag through gr.HTML.

11. Real UI tests: add tests in tests/test_ui/ that call the actual event handlers (extract them so they can be imported, or reach them through demo.fns) and cover: start → answer → skip → finish → confirm; the five-question cap including skips; Back from the summary invalidates it; Reset clears state; the age-clearing bug; reporting_on_behalf stays null; patient text with <script> and <img onerror> is escaped in every HTML output; step guards ignore clicks from the wrong step; the late-response test from item 4.

12. requirements.txt: pin gradio to the version you actually tested (currently 6.31.0), because launch(theme=...) does not exist in Gradio 5. Leave the PDF library choice for step 5 and note it in README as pending.

13. docs/prompt_log.md: append a new entry 5 for this fix round, containing the exact prompt text I pasted (verbatim, not a summary) and the model actually used. Correct entry 4 so it states the model used (DeepSeek V4 Pro), and replace the paraphrased prompt with the exact step-3 prompt text. Keep entries 1–3 byte-for-byte unchanged and keep the file's existing line endings, so git does not show Person 1's entries as modified.

After the fixes, run `python -m pytest -q`, launch the app locally, and check navigation, editing, reset, and 375px layout. Report the actual results: the test count split into core and UI, which items you fixed, and anything you could not verify. Do not claim a check you did not run. Do not commit; I will review first. If any item is ambiguous, ask me before implementing it.

**Outcome:** Replaced the preview backend with a no-business-logic stub that
only returns fictional fixtures plus fixed placeholder questions/summary text;
made ui/backend.py switch once on VISITPREP_PREVIEW (default off) with a clear
error when core is unavailable; disabled duplicate submissions via
trigger_mode="once"; added a session request token with commit_if_current (with
a confirm→reset→late-confirm test); fixed the age-clearing bug; switched
reporting_on_behalf to a three-option Radio that preserves null; removed the
name field entirely (item 7 option: remove, never pass name to core); surfaced
"Alerts unavailable in preview" / "Alerts could not be checked"; moved the alert
area under the title; cleaned CSS selectors, nl2br, and the fixture-box banner;
moved CSS into launch(css=...); pinned gradio==6.31.0 and unpinned the PDF
library; added real handler tests via demo.fns. Checks below.

## 8. Rebase reconciliation onto the v0.3 core (Person 2)

**Model:** DeepSeek V4 Pro

**Prompt:** Additional context from a review of the current repo state (HEAD cec1abb, rebased on Person 1's 6e51a08 "feat: add ai workflow"). Read the updated docs/data_contract.md first; it was largely rewritten.

Current failures you must fix first:
- Person 1 deleted core/alerts.py, core/extraction.py, core/questions.py, core/summary.py and replaced them with core/extract.py (extract_record), core/interview.py (choose_follow_up_question, merge_answer, MAX_DISPLAYED_QUESTIONS), core/redflag.py (check_alerts), core/summarize.py (generate_summary). ui/backend.py still imports the old modules, so the app crashes at import without VISITPREP_PREVIEW=1 (ModuleNotFoundError: core.alerts, ui/backend.py line 71).
- core.interview.choose_follow_up_question now has the signature (record, asked, skipped=None, max_questions=MAX_DISPLAYED_QUESTIONS). ui/backend.py passes max_questions positionally, so it lands in skipped. Pass every optional argument by keyword.
- The UI stores a skipped question as QuestionAnswer(question, "") inside asked. Follow the new contract for skips: keep a separate skipped list in session state and pass it to core. The five-question cap must still count skipped questions.
- tests/test_ui/test_backend.py::test_preview_off_with_core_stub_raises_not_implemented fails because core is no longer a stub. Replace it with a test for the real-core path (fake the LLM transport; no network in tests).

Remaining UI defects from the live audit at 375px:
- Dark mode: .question-box and .summary-box set a light background but no text color, so the text is almost invisible (rgb 243,244,246 on 249,250,251). Set both colors explicitly, or use Gradio theme variables for both.
- The alert area is at the top and does not follow scrolling, so on step 4 an urgent alert is off-screen while the user reads the summary. Repeat the current alerts at the top of step 4 (or make the alert area sticky), and keep the text escaped.
- Three error Markdown components share elem_id="error". Give each a unique id.

Rules: do not modify core/ or tests/test_core/. If the new core is missing something the UI needs, write an exact handoff for Person 1 instead. Do not touch the user's running instance on port 7860. Do not commit or push.

Report the actual results: pytest totals split into core and UI, whether app.py starts without VISITPREP_PREVIEW, one full fictional run with the real model (or say it is pending if no API key is configured), and which items you could not verify. Append this prompt verbatim as section 8 of docs/prompt_log.md, with the model actually used, and do not change sections 1 to 7.

**Outcome:** Reconciled the UI with the v0.3 core. ui/backend.py now imports
core.extract / core.interview / core.redflag / core.summarize: the rule-based
calls (choose_follow_up_question, check_alerts, scan_text) are always real, and
the three LLM calls switch on VISITPREP_PREVIEW. choose_follow_up_question is
called with keyword arguments, and skips go to a separate state["skipped"] list
(the displayed-question budget counts asked + skipped). Replaced the stub-era
subprocess test with a real-core-path test that fakes the LLM HTTP transport
(no network). UI defects: explicit text color on .question-box/.summary-box,
alerts repeated at the top of step 4, and unique error elem ids. Checks:
pytest 132 passed (105 core + 27 UI); app.py builds and serves without
VISITPREP_PREVIEW; the live-model fictional run is pending (no
MODELSCOPE_API_KEY configured).
