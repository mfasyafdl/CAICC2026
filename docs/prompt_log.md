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