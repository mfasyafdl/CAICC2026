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