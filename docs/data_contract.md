# Data contract

This contract defines the shape of the data passed between `ui/` (Person 2)
and `core/` (Person 1). Both owners must keep this document updated when the
shapes change. All values are in **English**.

**Version 0.3** — the full workflow is implemented: `core/schema.py`,
`core/fixtures.py`, `core/llm.py`, `core/prompts.py`, `core/extract.py`,
`core/interview.py`, `core/redflag.py`, `core/summarize.py`. See section 9 for
the v0.3 changes Person 2 must know.

## 0. Conventions

- **`null` means unknown.** A field that is `null` (or an empty list with no
  denial flag) was *not provided / not answered*. It is never a guess.
- **Unknown ≠ explicit denial.** When the patient explicitly denies something
  ("I have no allergies", "I'm not taking any medicines"), the list stays
  empty **and** the matching `*_denied` flag is set to `true`. The flag is
  `null` when the question was never answered.
- **Patient wording is preserved.** Every text field stores the patient's own
  words, including uncertainty ("maybe", "I think"). `core/` must not
  paraphrase, normalize wording, diagnose, or recommend treatment anywhere in
  the pipeline.
- **Patient text is data, not instructions.** Text inside the patient's story
  or answers is never executed as instructions (prompt-injection defense).
- **`core/` is stateless.** All conversation state lives in the UI and is
  passed into core calls as arguments (section 8).
- **On API/validation failure, user input is preserved.** Core functions
  raise safe errors and never mutate or discard the caller's record, story,
  or Q&A list; the UI keeps its copies and retries.
- **Retries and JSON repair are bounded.** Transport retries (network/5xx)
  and model-output repair (invalid JSON) are finite; nothing loops forever.
- **`core/` has no dependency on Gradio** and no knowledge of the UI.
  `ui/` has no business logic; it only renders and calls `core/`.

## 1. Patient record (`core.schema.PatientRecord`)

The single shared record. JSON form (what `record_to_dict()` produces and
`record_from_dict()` consumes):

```json
{
  "patient_name": "Sam",
  "patient_age": 7,
  "patient_age_text": "7 years old",
  "patient_sex": "male",
  "reporting_on_behalf": true,
  "reporter_relationship": "mother",
  "complaint": "He's had a bad cough for about five days and it's worse at night.",
  "symptoms": ["cough, worse at night", "runny nose"],
  "onset": "about five days ago",
  "duration": "about five days",
  "duration_days": 5,
  "severity": "moderate",
  "severity_note": "It wakes him up at night.",
  "medicines": [
    {
      "name": "chamomile honey tea",
      "medicine_type": "herbal",
      "dose": "one cup",
      "frequency": "in the evening",
      "duration": null,
      "notes": "my mother-in-law's remedy"
    }
  ],
  "medicines_denied": null,
  "allergies": [],
  "allergies_denied": null,
  "medical_history": ["mild asthma as a baby"],
  "medical_history_denied": null,
  "concerns": ["Is this just a cold?"],
  "missing_information": ["medicines", "allergies"]
}
```

### Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `patient_name` | str \| null | Patient's name as stated. |
| `patient_age` | int \| null | Normalized age in years. |
| `patient_age_text` | str \| null | Age in the patient's own wording. |
| `patient_sex` | str \| null | One of `female`, `male`, `other`, `not-specified`. |
| `reporting_on_behalf` | bool \| null | `true` when the reporter is not the patient (e.g. a parent). |
| `reporter_relationship` | str \| null | Reporter's relationship, their wording (`mother`, `caregiver`). |
| `complaint` | str \| null | Chief complaint, patient's own words. |
| `symptoms` | list[str] | Individual symptoms, each in the patient's own words. |
| `onset` | str \| null | When it started, patient's wording (`yesterday afternoon`). |
| `duration` | str \| null | How long, patient's wording (`about a week`). |
| `duration_days` | int \| null | Normalized best estimate in days; `null` if unknown. |
| `severity` | str \| null | One of `mild`, `moderate`, `severe`; `null` if not stated. |
| `severity_note` | str \| null | Patient's own words about impact (`it stops me from sleeping`). |
| `medicines` | list[Medicine] | Current medicines **including herbal remedies** (see below). |
| `medicines_denied` | bool \| null | `true` = patient explicitly takes nothing; `null` = unknown. |
| `allergies` | list[str] | Allergens, patient's wording. |
| `allergies_denied` | bool \| null | `true` = explicit "no allergies"; `null` = unknown. |
| `medical_history` | list[str] | Past conditions, patient's wording. |
| `medical_history_denied` | bool \| null | `true` = explicit "no known history"; `null` = unknown. |
| `concerns` | list[str] | Patient's own questions/worries for the doctor. |
| `missing_information` | list[str] | Labels of fields still unknown; values from `MISSING_FIELD_KEYS`: `age`, `sex`, `onset`, `duration`, `severity`, `medicines`, `allergies`, `medical_history`, `concerns`. Maintained by `core/` (recomputed on every merge). |

Validation (`core.schema.validate_record`) enforces: allowed enum values,
non-empty strings, sane integer ranges (age 0–130), and that a `*_denied`
flag of `true` contradicts a non-empty list.

### Medicine (`core.schema.Medicine`)

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | str | Medicine/remedy name as stated. |
| `medicine_type` | str | One of `prescription`, `over-the-counter`, `herbal`, `supplement`, `unknown`. Herbal remedies and supplements must be captured here, not dropped. |
| `dose` | str \| null | Dose, patient's wording (`one tablet`, `25 mg`). |
| `frequency` | str \| null | How often, patient's wording (`twice a day`). |
| `duration` | str \| null | How long taken, patient's wording (`for 3 days`). |
| `notes` | str \| null | Anything else the patient said about it. |

### Question/answer pair (`core.schema.QuestionAnswer`)

```json
{ "question": "Have you had a fever?", "answer": "A little, last night" }
```

The UI keeps the ordered list of previously asked pairs **and** the list of
questions the patient skipped, and passes them back on every core call.

## 2. Alert (`core.schema.Alert`)

```json
{ "code": "chest_pain", "message": "You reported chest pain. This may need urgent medical attention. In Indonesia, emergency medical services can be reached on 119. Please seek medical care now or tell the doctor immediately.", "level": "urgent" }
```

- `code`: stable machine key (see section 6 for the trigger list).
- `message`: safe English for display; no diagnosis, no treatment advice.
- `level`: `urgent` or `attention`.
- **A missing alert is not safety.** No message, panel, or screen may imply
  "no alerts = you are safe".

## 3. Summary output (`core.schema.SummaryOutput`)

```json
{
  "doctor_card": "Patient: ... Complaint: ... Symptoms: ... Medicines: ... Patient's concerns (patient's own words): \"...\" Not provided: ...",
  "patient_script": "I would like to tell you... (about 140-160 words)",
  "priority_questions": ["Could this be related to his asthma as a baby?", "Do we need to see a doctor today?", "What should we watch for at night?"]
}
```

- `doctor_card` (str): concise structured card for the doctor with labeled
  sections (Patient, Complaint, Symptoms, Onset & duration, Severity,
  Medicines including herbal remedies, Allergies, Medical history,
  Patient's concerns, Not provided). Unknown fields are written as
  "not provided", never guessed. Confirmed denials (`*_denied` true) use clear
  wording (e.g. "none — patient confirms no allergies"); unknown (`*_denied`
  null, empty list) is "Not provided", never "none". The card must not invent
  negatives or claim completeness ("no other symptoms", "only symptom"). The
  patient's concerns are quoted verbatim and labeled as the patient's own
  words, kept separate from the app's organization.
- `patient_script` (str): first-person script for **up to about a 60-second
  read (roughly 140–160 words when there is enough to report)**, plain spoken
  English, reported facts only, with **no filler added to reach a length** — a
  short record yields a short script. Validated only against a loose word
  window (rejects degenerate output; does not enforce a minimum target).
- `priority_questions` (list[str]): 1 to 3 questions the patient should ask
  the doctor, based on reported facts and concerns (not app conclusions).
- The summary contains **no alerts**: alerts come only from `core.redflag`
  (section 6), so the model can never remove a rule-generated alert.

> **Change from v0.1 (scaffold):** the summary no longer returns
> `doctor_summary`/`pdf_bytes`. PDF generation (if kept) will be a separate
> core interface — the PDF step should await that interface.

## 4. Callable interfaces

| # | Function | Signature | Returns |
| --- | --- | --- | --- |
| 4.1 | Extraction | `core.extract.extract_record(symptom_text: str, patient_details: dict \| None = None, *, config=None, max_tokens=4000, timeout=120.0, max_retries=2, max_repairs=1) -> PatientRecord` | Validated record from free text. |
| 4.2 | Choose follow-up | `core.interview.choose_follow_up_question(record: PatientRecord, asked: list[QuestionAnswer], skipped: list[str] \| None = None, max_questions: int = 5) -> str \| None` | Next question text, or `None` when done. |
| 4.3 | Merge answer | `core.interview.merge_answer(record: PatientRecord, question: str, answer: str, *, config=None, max_tokens=4000, timeout=120.0, max_retries=2, max_repairs=1) -> PatientRecord` | New record with the answer merged. |
| 4.4 | Rule-based alerts | `core.redflag.check_alerts(record: PatientRecord) -> list[Alert]` and `core.redflag.scan_text(*texts: str) -> list[Alert]` | Deterministic precautionary flags. |
| 4.5 | Generate summary | `core.summarize.generate_summary(record: PatientRecord, asked: list[QuestionAnswer], *, config=None, max_tokens=4000, timeout=120.0, max_retries=2, max_repairs=1) -> SummaryOutput` | `doctor_card`, `patient_script`, `priority_questions`. |

`core/prompts.py` holds the actual runtime prompts (extraction, merge,
summary, repair note). LLM-backed calls accept an optional pre-resolved
`config` (`core.llm.LLMConfig`); otherwise config is resolved from server
env / local `.env` (section 5).

### 4.1 `extract_record`

Parses the patient's raw description (optionally with `patient_details`
carrying `patient_name`/`patient_age`/`patient_sex` entered by the UI, which
override the extracted values) into a validated record. Preserves wording,
uncertainty, and negation; uses `null` for anything not stated; never invents
facts; recomputes `missing_information`. The patient text is sent to the
model inside `<patient_report>` tags and is treated strictly as data.
Failure modes: `ValueError` (empty input), `SchemaError` (bad
`patient_details`), safe `LLMError` subclasses (API/output failures) — the
raw story is never modified or lost.

### 4.2 `choose_follow_up_question`

**Rule-based — no API call** (deterministic, instant, works when the ModelScope
API is unavailable). Returns one short English question targeting the most
important still-missing field, in this order: `severity`, `onset`, `duration`,
`medicines`, `allergies`, `medical_history`, `age`, `sex`, `concerns`
(`core.interview.PRIORITY_FIELDS`). Wording adapts for on-behalf reports
("the patient's..." instead of "your..."). Returns `None` when the
**displayed-question budget** is exhausted — `len(asked) + len(skipped) >=
max_questions` (default 5, matching `MAX_FOLLOW_UP_QUESTIONS` in
`.env.example`) — or when nothing useful remains. Never repeats a question
already in `asked` or `skipped` (compared after stripping/case-folding).

### 4.3 `merge_answer`

LLM-backed, conservative. Returns a **new** record; never mutates the input.
Rules: keep every previously known fact and the patient's original wording
unless the answer explicitly corrects that fact; an explicit denial sets the
matching `*_denied` flag to `true`; unclear answers leave the field `null`;
recompute `missing_information`. A deterministic **fact-loss guard** rejects
any update that drops a known fact (scalar → null, list → empty without the
matching `*_denied=true`, denial flag → not true). Invalid output gets one
bounded repair attempt, then a safe `LLMResponseError`. On any failure the
input record is unchanged; the UI must still append
`QuestionAnswer(question, answer)` to its `asked` list so the patient's input
survives into the summary (section 8).

### 4.4 `check_alerts` / `scan_text`

Pure, deterministic, **no LLM and no network** (see section 6).
`check_alerts(record)` uses the structured record (including age/pregnancy
context); `scan_text(*texts)` runs the text triggers over raw strings — call
it on the patient's raw story **before** the slow extraction API call.
Order: urgent first, then by `code`.

### 4.5 `generate_summary`

Produces `SummaryOutput` (section 3) from the reviewed record and the full
`asked` list. The model output is validated (types, non-empty, script length
window) with one bounded repair. On failure the record and `asked` are
untouched; the UI keeps them and retries.

## 5. LLM client (`core/llm.py`)

OpenAI-compatible client for `https://api-inference.modelscope.ai/v1`.

- Config: `MODELSCOPE_API_KEY` and `MODELSCOPE_MODEL` are read from server
  environment variables first, then from the local `.env` file (project
  root). The default model is `zai-org/GLM-5.2`. Only the four approved
  models are accepted (`ALLOWED_MODELS`); any other value raises
  `ConfigError` with a safe English message.
- Only those two variables are ever read. No other environment or credential
  files (e.g. OpenCode credentials) are accessed.
- Finite timeouts (`0 < timeout <= 600`s) and bounded transport retries
  (network/5xx only, default 2, capped exponential backoff; auth and quota
  errors fail fast).
- Safe English errors: `LLMAuthError`, `LLMQuotaError`, `LLMNetworkError`,
  `LLMServerError`, `LLMResponseError`, `ConfigError`. Messages never contain
  the API key or patient text; nothing sensitive is logged.
- Calls: `chat(system, user, ...) -> str`; `chat_json(system, user,
  validate=...) -> dict`; `chat_json_repairable(system, user, validate=...,
  repair_note=..., max_repairs=1, ...) -> dict` — bounded JSON repair used by
  the workflow (at most `max_repairs + 1` model calls).
- `zai-org/GLM-5.2` is a reasoning model: it spends hidden
  `reasoning_content` tokens, so JSON tasks need a generous `max_tokens`
  (the workflow defaults above already account for this).

## 6. Red-flag alerts (`core/redflag.py`)

Limited precautionary alerts, **rule-based, no AI**. Triggers are a
conservative subset of authoritative Indonesian guidance:

- Kemenkes RI (Ministry of Health), danger-sign ("tanda bahaya") public
  health education and maternal danger signs: <https://www.kemkes.go.id/>
- Kemenkes PSC 119, national emergency medical call center (number 119):
  <https://psc119.kemkes.go.id/>
- IDAI (Indonesian Pediatric Society), child danger signs and referral
  guidance: <https://www.idai.or.id/>
- WHO IMCI danger signs for immediate referral (fast breathing/chest
  indrawing, stridor at rest, unable to drink or breastfeed, convulsions,
  lethargy/unconsciousness): <https://www.who.int/>

Trigger codes (all messages in English):

| Code | Level | Fires on (English patient wording) |
| --- | --- | --- |
| `breathing_difficulty` | urgent | difficulty/trouble breathing, shortness of breath, breathless, can't/cannot breathe, chest indrawing, stridor |
| `chest_pain` | urgent | chest pain, pain/tightness/pressure in the chest |
| `heavy_bleeding` | urgent | heavy/severe/uncontrolled bleeding, vomiting/coughing up blood, blood in stool/vomit/urine |
| `allergic_reaction` | urgent | swelling of face/lips/tongue/throat/eyes/mouth, throat tight/closing, difficulty swallowing |
| `seizure` | urgent | seizure, convulsion |
| `altered_consciousness` | urgent | unconscious, fainted/fainting, passed out, blacked out, confusion, lethargic, hard to wake |
| `cannot_drink` | urgent | can't/won't/refuses to drink or breastfeed (IMCI/IDAI danger sign) |
| `neck_stiffness` | urgent | stiff neck, can't touch chin to chest |
| `high_fever` | attention | high fever, fever/temperature of 39–40 |
| `persistent_vomiting` | attention | vomiting all day/multiple times, can't keep food or water down |
| `infant_fever` (record) | urgent | `patient_age == 0` (under 1 year) **and** reported fever |
| `pregnancy_danger` (record) | urgent | pregnancy reported **plus** bleeding, severe headache, severe abdominal pain, difficulty breathing, convulsions, or high fever (Kemenkes maternal danger signs) |

Rules:

- **Negations are suppressed**: "no chest pain", "I do not have trouble
  breathing" do not fire (negation words checked in the few preceding words).
- **Historical mentions are suppressed**: "had a seizure as a child",
  "convulsions last year" do not fire (past-tense markers checked in the same
  sentence).
- **No safety claims**: the absence of an alert is never presented as proof
  of safety; no alert message contains such wording.
- **The model cannot remove alerts**: alerts are not part of any LLM payload
  or output; the UI renders them solely from `core.redflag` results.
- Urgent messages reference the Indonesian emergency number **119** (PSC
  119).

### How Person 2 runs alert checks before slow API calls

`check_alerts`/`scan_text` are pure Python: no network, no API key,
millisecond-scale. Reference flow:

1. Patient types the story → immediately `alerts = scan_text(story)` → show
   the alert panel (this works even if the API is down).
2. Call `extract_record(story, details)` (slow API). On failure: keep the raw
   story and the step-1 alerts, show a safe error, let the patient retry.
3. After each `merge_answer` (and after any manual edit) →
   `alerts = check_alerts(record)` → refresh the panel.
4. If the API is unavailable at any point, the last computed alerts stay
   valid for the last known record state; the UI must not clear them.
5. Alerts are rendered from `core.redflag` output only — never from summary
   text, and never "filtered" by the model.

## 7. Fixtures (fictional)

`core/fixtures.py` provides pure-data fixtures for UI development and tests.
**All names and details are fictional.** No network, LLM, or Gradio needed.

```python
from core.fixtures import (
    FIXTURE_EMPTY_RECORD,                 # everything unknown
    FIXTURE_FEVER_ADULT,                  # explicit "no allergies", herbal remedy
    FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER,  # on-behalf report, unknowns stay null
    FIXTURE_RASH_WITH_ALLERGY,            # complete record, explicit allergy list
    all_fixtures,                         # dict of the above
)
```

- `FIXTURE_FEVER_ADULT` shows an **explicit denial** (`allergies_denied: true`,
  `allergies: []`) and a **herbal remedy** (`medicine_type: "herbal"`).
- `FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER` shows **unknown** values
  (`allergies_denied: null`, `medicines_denied: null`) and
  `reporting_on_behalf: true`.
- `FIXTURE_RASH_WITH_ALLERGY` is fully populated (empty
  `missing_information`) with a prescription medicine and an explicit allergy
  list.

## 8. How the UI supplies state

The UI owns the state:

- `record` — the current `PatientRecord` (or its dict form),
- `asked` — the ordered list of previously asked `QuestionAnswer` pairs,
- `skipped` — question texts the patient skipped (optional).

All core calls receive them **explicitly as arguments**; core keeps no session
state and never stores patient data.

Reference loop (pseudocode for Person 2):

```python
from core.extract import extract_record
from core.interview import choose_follow_up_question, merge_answer
from core.redflag import check_alerts, scan_text
from core.summarize import generate_summary
from core.schema import QuestionAnswer

alerts = scan_text(story)                    # instant, offline — show first
record = extract_record(story, details)      # slow API; on LLMError: keep story + alerts, retry
asked: list[QuestionAnswer] = []
skipped: list[str] = []

while (question := choose_follow_up_question(record, asked, skipped)) is not None:
    answer_or_skip = ask_patient_in_ui(question)   # Person 2's UI code
    if answer_or_skip is None:                     # patient skipped it
        skipped.append(question)
        continue
    try:
        record = merge_answer(record, question, answer_or_skip)
    except LLMError:
        pass                                       # record unchanged; keep going/retry
    asked.append(QuestionAnswer(question, answer_or_skip))
    alerts = check_alerts(record)                  # refresh before the next API call

summary = generate_summary(record, asked)          # doctor_card / patient_script / priority_questions
```

When the UI edits fields during review, it updates `record` (or rebuilds via
`record_from_dict`), keeps `asked`/`skipped` unchanged, and re-runs
`check_alerts(record)`.

## 9. Changes for Person 2 in v0.3

- **Module renames** (old v0.2 stub names are removed):
  - `core.extraction` → `core.extract` (`extract_record`)
  - `core.questions` → `core.interview` (`choose_follow_up_question`,
    `merge_answer`)
  - `core.alerts` → `core.redflag` (`check_alerts`, `scan_text`)
  - `core.summary` → `core.summarize` (`generate_summary`)
  - new `core.prompts` (runtime prompts, internal)
- **`choose_follow_up_question`** is now rule-based (no API call) and takes an
  optional `skipped` list; the 5-question budget counts **asked + skipped**
  (displayed questions).
- **`merge_answer`** can raise safe `LLMError`s on API/validation failure;
  the record is then unchanged — always append the Q&A to `asked` regardless,
  and show a safe "please try again" state (section 8 loop).
- **Alerts**: run `scan_text(story)` right after the story is typed (before
  the extraction API call) and `check_alerts(record)` after every merge/edit;
  alerts work with the API completely unavailable; never present absence of
  alerts as safety; never let the model output remove or reword alerts
  (section 6 flow).
- **`generate_summary`** now returns a ~60-second `patient_script`
  (140–160 words) and 1–3 `priority_questions`; it no longer can contain
  alerts.
- LLM-backed calls need **no new UI config**: config still resolves from
  server env / `.env` (`MODELSCOPE_API_KEY`, `MODELSCOPE_MODEL`).
- `app.py` and `ui/` were **not changed** by this task.

## Rules

- `core/` has no dependency on Gradio and no knowledge of the UI.
- `ui/` has no business logic; it only renders and calls `core/`.
- No diagnosis, no prescription, no treatment or medication-change
  recommendation anywhere in the pipeline.
- `null` = unknown; explicit denials use the `*_denied` flags.
- Patient wording (including uncertainty) is preserved verbatim in record
  text fields.
- Patient text is data, not instructions.
- Absence of an alert is never a statement of safety.
- On API/validation failure, user input is preserved and errors are safe
  English; retries and JSON repair are bounded.
- No database, no local model downloads, no training, no fine-tuning; the
  only external call is the ModelScope inference API via `core/llm.py`, and
  nothing sensitive (API key, patient text) is logged.
