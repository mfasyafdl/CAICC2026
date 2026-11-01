# Data contract

This contract defines the shape of the data passed between `ui/` (Person 2)
and `core/` (Person 1). Both owners must keep this document updated when the
shapes change. All values are in **English**.

The names below are provisional until each stage is implemented. Update this
file as part of the task that introduces a stage.

## 1. Symptom description

Free text, typed by the patient.

```json
{ "symptoms": "I have had a sore throat and a dry cough for about a week." }
```

## 2. Follow-up questions (up to five)

A list of question/answer pairs. `core/` owns generating the questions; `ui/`
owns presenting them and collecting answers.

```json
{
  "follow_ups": [
    { "question": "When did your symptoms start?", "answer": "About a week ago" },
    { "question": "Have you had a fever?", "answer": "No" }
  ]
}
```

## 3. Reviewable details

The merged, structured record after the patient reviews and edits. `ui/` shows
editable fields; `core/` validates and stores.

```json
{
  "symptoms": "sore throat and dry cough",
  "duration": "about a week",
  "severity": "mild",
  "follow_ups": [
    { "question": "Have you had a fever?", "answer": "No" }
  ]
}
```

## 4. Outputs

`core/` produces these from the reviewable details:

- `doctor_summary` (str): a concise summary for the doctor.
- `patient_script` (str): a short script the patient can read aloud.
- `pdf_bytes` (bytes): the generated PDF containing both of the above.

```json
{
  "doctor_summary": "Patient reports a sore throat and dry cough...",
  "patient_script": "I've had a sore throat and dry cough for about a week...",
  "pdf_bytes": "..."
}
```

## Rules

- `core/` has no dependency on Gradio and no knowledge of the UI.
- `ui/` has no business logic; it only renders and calls `core/`.
- No diagnosis or treatment recommendation anywhere in the pipeline.