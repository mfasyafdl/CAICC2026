# Data contract

This contract defines the shape of the data passed between `ui/` (Person 2)
and `core/` (Person 1). Both owners must keep this document updated when the
shapes change. All values are in **English**.

**Version 0.2** — the patient record, module interfaces, and fixtures below
are implemented in `core/schema.py` and `core/fixtures.py`. The LLM client is
`core/llm.py`. Extraction, questions, alerts, and summary modules currently
exist as importable stubs (signatures fixed, bodies raise
`NotImplementedError`) until their implementation tasks.

## 0. Conventions

- **`null` means unknown.** A field that is `null` (or an empty list with no
  denial flag) was *not provided / not answered*. It is never a guess.
- **Unknown ≠ explicit denial.** When the patient explicitly denies something
  ("I have no allergies", "I'm not taking any medicines"), the list stays
  empty **and** the matching `*_denied` flag is set to `true`. The flag is
  `null` when the question was never answered.
- **Patient wording is preserved.** Every text field stores the patient's own
  words. `core/` must not paraphrase, normalize wording, diagnose, or
  recommend treatment anywhere in the pipeline.
- **`core/` is stateless.** All conversation state lives in the UI and is
  passed into core calls as arguments (section 7).
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

The UI keeps the ordered list of previously asked pairs and passes it back on
every core call.

## 2. Alert (`core.schema.Alert`)

```json
{ "code": "breathing_difficulty", "message": "You reported trouble breathing. Please tell your doctor this first.", "level": "urgent" }
```

- `code`: stable machine key.
- `message`: safe English for display; no diagnosis, no advice beyond
  "tell your doctor / this may need attention".
- `level`: `attention` or `urgent`.

## 3. Summary output (`core.schema.SummaryOutput`)

```json
{
  "doctor_card": "7-year-old boy (reported by mother). Cough worse at night for about five days, plus runny nose... Medicines: not reported. Allergies: not reported. Known history: mild asthma as a baby.",
  "patient_script": "My son has had a bad cough for about five days, worse at night...",
  "priority_questions": ["Could this be related to his asthma as a baby?", "Do we need to see a doctor today?", "What should we watch for at night?"]
}
```

- `doctor_card` (str): concise structured card for the doctor. Unknown fields
  are written as "not provided", never guessed.
- `patient_script` (str): short first-person script the patient can read
  aloud.
- `priority_questions` (list[str]): up to three questions the patient should
  ask the doctor.

> **Change from v0.1 (scaffold):** the summary no longer returns
> `doctor_summary`/`pdf_bytes`. It returns `doctor_card`, `patient_script`,
> `priority_questions`. PDF generation (if kept) will be a separate core
> interface — **note for Person 2**: the PDF step in `ui/welcome.py` should
> await that interface, not expect PDF bytes from the summary.

## 4. Callable interfaces

| # | Function | Signature | Returns |
| --- | --- | --- | --- |
| 6.1 | Extraction | `core.extraction.extract_record(symptom_text: str, patient_details: dict \| None = None) -> PatientRecord` | Structured record from free text. |
| 6.2 | Choose follow-up | `core.questions.choose_follow_up_question(record: PatientRecord, asked: list[QuestionAnswer], max_questions: int = 5) -> str \| None` | Next question text, or `None` when done. |
| 6.3 | Merge answer | `core.questions.merge_answer(record: PatientRecord, question: str, answer: str) -> PatientRecord` | New record with the answer merged. |
| 6.4 | Rule-based alerts | `core.alerts.check_alerts(record: PatientRecord) -> list[Alert]` | Deterministic attention flags. |
| 6.5 | Generate summary | `core.summary.generate_summary(record: PatientRecord, asked: list[QuestionAnswer]) -> SummaryOutput` | `doctor_card`, `patient_script`, `priority_questions`. |

### 6.1 `extract_record`

Parses the patient's raw description (optionally with `patient_details`
carrying name/age/sex entered by the UI) into a record. Preserves wording;
uses `null` for anything not stated; recomputes `missing_information`.

### 6.2 `choose_follow_up_question`

Picks at most one next question in plain English. Targets
`record.missing_information` first, then clarification of ambiguous fields.
Returns `None` when `len(asked) >= max_questions` (default 5, matching
`MAX_FOLLOW_UP_QUESTIONS` in `.env.example`) or nothing useful remains. Never
repeats a question already in `asked` (compared after stripping/case-folding).

### 6.3 `merge_answer`

Pure: returns a **new** record, never mutates the input. Stores the answer in
the patient's own wording. An explicit denial sets the matching `*_denied`
flag to `true`; an unclear answer leaves the field `null`. Recomputes
`missing_information`. The UI appends `QuestionAnswer(question, answer)` to
its own `asked` list.

### 6.4 `check_alerts`

Pure, deterministic, no LLM. Flags patient-reported content that may need
attention (e.g. breathing difficulty, chest pain, heavy bleeding → `urgent`;
a listed allergy mentioned next to a new medicine → `attention`). Stable
order: urgent first, then by `code`.

### 6.5 `generate_summary`

Produces `SummaryOutput` (section 3) from the reviewed record and the full
`asked` list.

## 5. LLM client (`core/llm.py`)

OpenAI-compatible client for `https://api-inference.modelscope.ai/v1`.

- Config: `MODELSCOPE_API_KEY` and `MODELSCOPE_MODEL` are read from server
  environment variables first, then from the local `.env` file. The default
  model is `zai-org/GLM-5.2`. Only the four approved models are accepted; any
  other value raises a `ConfigError` with a safe English message.
- Only the two variables above are ever read. No other environment or
  credential files (e.g. OpenCode credentials) are accessed.
- Finite timeouts and bounded retries (network/5xx only; auth and quota
  errors fail fast).
- Safe English errors: `LLMAuthError` (auth failure), `LLMQuotaError` (quota/
  rate limit), `LLMNetworkError` (network failure), `LLMServerError` (HTTP
  5xx), `LLMResponseError` (invalid/unparseable model output), `ConfigError`
  (bad configuration). Error messages never contain the API key or patient
  text, and nothing sensitive is logged.
- `chat(system, user, ...) -> str` and `chat_json(system, user, validate=...)
  -> dict` (parses and validates JSON output against the schema).

## 6. Fixtures (fictional)

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

JSON example — `FIXTURE_CHILD_COUGH_REPORTED_BY_MOTHER`:

```json
{
  "patient_name": "Sam",
  "patient_age": 7,
  "patient_age_text": "7 years old",
  "patient_sex": "male",
  "reporting_on_behalf": true,
  "reporter_relationship": "mother",
  "complaint": "He's had a bad cough for about five days and it's worse at night.",
  "symptoms": ["cough, worse at night", "runny nose", "vomited once after a coughing fit"],
  "onset": "about five days ago",
  "duration": "about five days",
  "duration_days": 5,
  "severity": "moderate",
  "severity_note": "It wakes him up at night.",
  "medicines": [],
  "medicines_denied": null,
  "allergies": [],
  "allergies_denied": null,
  "medical_history": ["mild asthma as a baby"],
  "medical_history_denied": null,
  "concerns": ["Is this just a cold?", "Should he stay home from school?"],
  "missing_information": ["medicines", "allergies"]
}
```

## 7. How the UI supplies state

The UI owns two pieces of state:

- `record` — the current `PatientRecord` (or its dict form), and
- `asked` — the ordered list of previously asked `QuestionAnswer` pairs.

All core calls receive them **explicitly as arguments**; core keeps no session
state and never stores patient data.

Reference loop (pseudocode for Person 2):

```python
from core.extraction import extract_record
from core.questions import choose_follow_up_question, merge_answer
from core.alerts import check_alerts
from core.summary import generate_summary
from core.schema import QuestionAnswer

record = extract_record(symptom_text, patient_details)
asked: list[QuestionAnswer] = []

while (question := choose_follow_up_question(record, asked)) is not None:
    answer = ask_patient_in_ui(question)        # Person 2's UI code
    record = merge_answer(record, question, answer)
    asked.append(QuestionAnswer(question, answer))

alerts = check_alerts(record)                   # show as attention flags
summary = generate_summary(record, asked)       # doctor_card / patient_script / priority_questions
```

When the UI edits fields during review, it updates `record` in place (or
rebuilds it via `record_from_dict`) and keeps `asked` unchanged.

## Rules

- `core/` has no dependency on Gradio and no knowledge of the UI.
- `ui/` has no business logic; it only renders and calls `core/`.
- No diagnosis or treatment recommendation anywhere in the pipeline.
- `null` = unknown; explicit denials use the `*_denied` flags.
- Patient wording is preserved verbatim in record text fields.
- No database, no local model downloads, no training, no fine-tuning; the only
  external call is the ModelScope inference API via `core/llm.py`, and nothing
  sensitive (API key, patient text) is logged.
