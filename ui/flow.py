"""The four-step VisitPrep interface (Gradio Blocks).

Owned by Person 2. This module renders the interface and wires the glue that
calls core/ (through ``ui.backend``). Per-session state (the current record,
the asked questions, and the skipped questions) is held in a ``gr.State`` dict
and passed to core calls as arguments; core stays stateless.

The flow:

1. Describe symptoms (plus optional age and sex).
2. Answer follow-up questions one at a time (progress out of five, Skip,
   Finish early).
3. Review & edit symptoms, medicines, allergies/history, and concerns, then
   confirm the record.
4. View the doctor card, patient script, priority questions, and the PDF
   download control.
"""

from __future__ import annotations

import copy
from dataclasses import asdict

import gradio as gr

from core.fixtures import all_fixtures
from core.llm import LLMError
from core.schema import (
    MEDICINE_TYPES,
    SEX_VALUES,
    Medicine,
    QuestionAnswer,
    SchemaError,
    empty_record,
    recompute_missing_information,
    record_from_dict,
    record_to_dict,
)
from ui import backend
from ui.components import (
    FIXTURE_BANNER,
    PRIVACY_NOTE,
    alerts_error_html,
    alerts_html,
    esc,
    priority_list_html,
    question_box_html,
    summary_box_html,
)
from ui.state import commit_if_current, new_state, touch

SEX_CHOICES = ["", *SEX_VALUES]
SEVERITY_CHOICES = ["", "mild", "moderate", "severe"]
REPORTING_CHOICES = ["Not answered", "Myself", "Someone else"]

MEDICINE_FIELD_HELP = (
    "One medicine per line, as: Name | type | dose | frequency | duration | "
    "notes. Type is one of: prescription, over-the-counter, herbal, supplement, "
    "unknown. Only the name is required."
)


def _dict_to_record(data):
    if not data:
        return None
    return record_from_dict(data)


def _reporting_to_label(value) -> str:
    if value is True:
        return "Someone else"
    if value is False:
        return "Myself"
    return "Not answered"


def _label_to_reporting(label) -> bool | None:
    if label == "Someone else":
        return True
    if label == "Myself":
        return False
    return None


def list_to_text(items) -> str:
    return "\n".join(items or [])


def list_from_text(text) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def medicines_to_text(medicines) -> str:
    lines = []
    for medicine in medicines:
        fields = [
            medicine.name or "",
            medicine.medicine_type or "",
            medicine.dose or "",
            medicine.frequency or "",
            medicine.duration or "",
            medicine.notes or "",
        ]
        while fields and fields[-1] == "":
            fields.pop()
        lines.append(" | ".join(fields))
    return "\n".join(lines)


def medicines_from_text(text) -> list[Medicine]:
    medicines: list[Medicine] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        parts += [""] * (6 - len(parts))
        name = parts[0]
        if not name:
            continue
        medicine_type = parts[1] if parts[1] in MEDICINE_TYPES else "unknown"
        medicines.append(
            Medicine(
                name=name,
                medicine_type=medicine_type,
                dose=parts[2] or None,
                frequency=parts[3] or None,
                duration=parts[4] or None,
                notes=parts[5] or None,
            )
        )
    return medicines


def _safe_llm_message(exc: Exception) -> str:
    if isinstance(exc, LLMError):
        return str(exc)
    if isinstance(exc, SchemaError):
        return "The submitted information could not be processed. Please try again."
    if isinstance(exc, ValueError):
        return "The submitted information could not be processed. Please try again."
    return "Something went wrong. Please try again."


def build_interface() -> None:
    """Render the full interface into the current Blocks context."""
    components: dict[str, object] = {}
    order: list[str] = []

    def register(name: str, component):
        components[name] = component
        order.append(name)
        return component

    def _coerce_age(value):
        if value is None:
            return None
        try:
            age = int(value)
        except (TypeError, ValueError):
            return None
        return age if 0 <= age <= 130 else None

    def _refresh_alerts_from_record(state: dict, record) -> None:
        try:
            state["alerts"] = backend.check_alerts(record)
            state["alerts_error"] = False
        except Exception:
            state["alerts"] = []
            state["alerts_error"] = True

    def _refresh_alerts_from_text(state: dict, *texts: str) -> None:
        try:
            state["alerts"] = backend.scan_text(*texts)
            state["alerts_error"] = False
        except Exception:
            state["alerts"] = []
            state["alerts_error"] = True

    with gr.Column(elem_id="visitprep-root"):
        register("title", gr.Markdown("# VisitPrep"))
        register(
            "alerts",
            gr.HTML(value=alerts_html([]), elem_id="alerts-area"),
        )
        register(
            "subtitle",
            gr.Markdown(
                "Turn what you report into a clear summary and a short script "
                "to read to your doctor. VisitPrep does not diagnose or advise."
            ),
        )

        register("privacy", gr.Markdown(PRIVACY_NOTE, elem_id="privacy-note"))

        register(
            "fixture_banner",
            gr.HTML(
                value='<div class="fixture-box">%s</div>' % esc(FIXTURE_BANNER)
                if backend.preview_mode()
                else "",
                visible=backend.preview_mode(),
                elem_id="fixture-banner",
            ),
        )

        with gr.Row(visible=backend.preview_mode()) as fixture_row:
            fixture_names = sorted(all_fixtures().keys())
            fixture_dropdown = gr.Dropdown(
                choices=fixture_names,
                label="Fictional sample (for testing)",
                value=None,
            )
            load_button = gr.Button("Load sample", size="sm")
        register("fixture_row", fixture_row)
        register("fixture_dropdown", fixture_dropdown)
        register("load_button", load_button)

        reset = gr.Button("Start over", variant="secondary", size="sm")
        register("reset", reset)

        # ----------------------------------------------------------------
        # Step 1 — describe symptoms
        # ----------------------------------------------------------------
        with gr.Column(elem_id="step-1") as s1:
            gr.Markdown("### Step 1 of 4 — Describe your symptoms")
            gr.Markdown(
                "Write your symptoms in your own words. Age and sex are "
                "optional."
            )
            symptom_text = gr.Textbox(
                label="Symptoms",
                lines=4,
                placeholder="Example: I've had a dry cough and a sore throat since Tuesday.",
            )
            with gr.Row():
                patient_age = gr.Number(label="Age (optional)", precision=0)
                patient_sex = gr.Dropdown(choices=SEX_CHOICES, label="Sex (optional)", value="")
            s1_error = gr.Markdown("", visible=False, elem_id="s1-error")
            continue_button = gr.Button("Continue", variant="primary")
        register("s1", s1)

        # ----------------------------------------------------------------
        # Step 2 — follow-up questions
        # ----------------------------------------------------------------
        with gr.Column(elem_id="step-2", visible=False) as s2:
            gr.Markdown("### Step 2 of 4 — A few clarifying questions")
            q_progress = gr.Markdown("")
            q_box = gr.HTML("")
            answer_input = gr.Textbox(label="Your answer", lines=2)
            s2_error = gr.Markdown("", visible=False, elem_id="s2-error")
            s2_notice = gr.Markdown("", visible=False, elem_id="s2-notice")
            with gr.Row():
                answer_button = gr.Button("Answer", variant="primary")
                skip_button = gr.Button("Skip")
                finish_button = gr.Button("Finish early")
            back2_button = gr.Button("Back", variant="secondary", size="sm")
        register("s2", s2)

        # ----------------------------------------------------------------
        # Step 3 — review & edit
        # ----------------------------------------------------------------
        with gr.Column(elem_id="step-3", visible=False) as s3:
            gr.Markdown("### Step 3 of 4 — Review & edit")
            gr.Markdown(
                "Check the details below and correct anything that is wrong. "
                "Your own wording is kept wherever possible."
            )
            review_complaint = gr.Textbox(label="Chief complaint", lines=2)
            with gr.Row():
                review_onset = gr.Textbox(label="Onset")
                review_duration = gr.Textbox(label="Duration")
            with gr.Row():
                review_severity = gr.Dropdown(choices=SEVERITY_CHOICES, label="Severity")
                review_severity_note = gr.Textbox(label="Severity note")
            review_symptoms = gr.Textbox(label="Symptoms (one per line)", lines=3)

            gr.Markdown("#### Medicines")
            gr.Markdown(MEDICINE_FIELD_HELP, elem_classes="field-help")
            review_medicines = gr.Textbox(label="Medicines", lines=3)
            review_medicines_none = gr.Checkbox(label="I take no medicines")
            gr.Markdown("#### Allergies & history")
            with gr.Row():
                review_allergies = gr.Textbox(label="Allergies (one per line)", lines=2)
                review_history = gr.Textbox(label="Medical history (one per line)", lines=2)
            with gr.Row():
                review_allergies_none = gr.Checkbox(label="No allergies")
                review_history_none = gr.Checkbox(label="No known medical history")
            review_concerns = gr.Textbox(label="Questions or concerns for the doctor (one per line)", lines=2)

            with gr.Accordion(label="Patient / reporter details", open=False):
                with gr.Row():
                    review_age = gr.Number(label="Age", precision=0)
                    review_sex = gr.Dropdown(choices=SEX_CHOICES, label="Sex")
                review_reporting = gr.Radio(
                    choices=REPORTING_CHOICES,
                    value="Not answered",
                    label="Who are these symptoms about?",
                )
                review_rel = gr.Textbox(label="Reporter relationship")
            s3_error = gr.Markdown("", visible=False, elem_id="s3-error")
            confirm_button = gr.Button("Confirm record", variant="primary")
            back3_button = gr.Button("Back to questions", variant="secondary", size="sm")
        register("s3", s3)

        # ----------------------------------------------------------------
        # Step 4 — output
        # ----------------------------------------------------------------
        with gr.Column(elem_id="step-4", visible=False) as s4:
            gr.Markdown("### Step 4 of 4 — Your visit summary")
            step4_alerts = gr.HTML("")
            gr.Markdown("#### For the doctor")
            doctor_card = gr.HTML("")
            gr.Markdown("#### What to say (patient script)")
            patient_script = gr.HTML("")
            gr.Markdown("#### Questions to ask")
            priority_questions = gr.HTML("")
            gr.Markdown("#### Download")
            pdf_button = gr.Button("Download PDF", interactive=False)
            pdf_note = gr.HTML(
                "<div class='field-help'>PDF export will be available once the "
                "PDF interface lands in core/. Nothing to download yet.</div>"
            )
            back4_button = gr.Button("Edit details", variant="secondary", size="sm")
        register("s4", s4)

    # Register the remaining managed components in display order so every event
    # returns updates in a stable, consistent sequence.
    for name in [
        "symptom_text", "patient_age", "patient_sex", "s1_error",
        "q_progress", "q_box", "answer_input", "s2_error", "s2_notice",
        "review_complaint", "review_symptoms", "review_onset", "review_duration",
        "review_severity", "review_severity_note", "review_medicines",
        "review_medicines_none", "review_allergies", "review_allergies_none",
        "review_history", "review_history_none", "review_concerns",
        "review_age", "review_sex", "review_reporting", "review_rel", "s3_error",
        "step4_alerts", "doctor_card", "patient_script", "priority_questions",
        "pdf_note",
    ]:
        components[name] = locals()[name]
        order.append(name)

    max_questions = backend.max_follow_up_questions

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def _render(state: dict) -> dict:
        step = state.get("step", 1)
        record = _dict_to_record(state.get("record"))
        update: dict[str, object] = {name: gr.update() for name in order}

        update["s1"] = gr.update(visible=step == 1)
        update["s2"] = gr.update(visible=step == 2)
        update["s3"] = gr.update(visible=step == 3)
        update["s4"] = gr.update(visible=step == 4)
        update["fixture_banner"] = gr.update(
            value='<div class="fixture-box">%s</div>' % esc(FIXTURE_BANNER)
            if backend.preview_mode()
            else "",
            visible=backend.preview_mode(),
        )
        update["fixture_row"] = gr.update(visible=backend.preview_mode())

        # Persistent rule-based alert area (directly under the title).
        if state.get("alerts_error"):
            update["alerts"] = gr.update(value=alerts_error_html())
        else:
            update["alerts"] = gr.update(value=alerts_html(state.get("alerts") or []))

        if step == 2:
            question = state.get("question")
            asked = state.get("asked") or []
            skipped = state.get("skipped") or []
            display_count = len(asked) + len(skipped)
            progress_number = min(display_count + 1, max_questions)
            update["q_progress"] = gr.update(
                value=f"Question **{progress_number} of {max_questions}**"
            )
            update["q_box"] = gr.update(value=question_box_html(question or ""))
            update["answer_input"] = gr.update(value="")

        if step == 3 and record is not None:
            update["review_complaint"] = gr.update(value=record.complaint or "")
            update["review_symptoms"] = gr.update(value=list_to_text(record.symptoms))
            update["review_onset"] = gr.update(value=record.onset or "")
            update["review_duration"] = gr.update(value=record.duration or "")
            update["review_severity"] = gr.update(value=record.severity or "")
            update["review_severity_note"] = gr.update(value=record.severity_note or "")
            update["review_medicines"] = gr.update(value=medicines_to_text(record.medicines))
            update["review_medicines_none"] = gr.update(value=record.medicines_denied is True)
            update["review_allergies"] = gr.update(value=list_to_text(record.allergies))
            update["review_allergies_none"] = gr.update(value=record.allergies_denied is True)
            update["review_history"] = gr.update(value=list_to_text(record.medical_history))
            update["review_history_none"] = gr.update(value=record.medical_history_denied is True)
            update["review_concerns"] = gr.update(value=list_to_text(record.concerns))
            update["review_age"] = gr.update(value=record.patient_age)
            update["review_sex"] = gr.update(value=record.patient_sex or "")
            update["review_reporting"] = gr.update(
                value=_reporting_to_label(record.reporting_on_behalf)
            )
            update["review_rel"] = gr.update(
                value=record.reporter_relationship or "",
                visible=record.reporting_on_behalf is True,
            )

        if step == 4:
            alerts = state.get("alerts") or []
            update["step4_alerts"] = gr.update(
                value=alerts_html(alerts) if alerts else ""
            )
            summary = state.get("summary")
            current = summary if state.get("summary_rev") == state.get("rev") else None
            if current:
                update["doctor_card"] = gr.update(
                    value=summary_box_html(current["doctor_card"])
                )
                update["patient_script"] = gr.update(
                    value=summary_box_html(current["patient_script"])
                )
                update["priority_questions"] = gr.update(
                    value=priority_list_html(current.get("priority_questions", []))
                )
                update["pdf_note"] = gr.update(
                    value="<div class='field-help'>PDF export will be available once "
                    "the PDF interface lands in core/. Nothing to download yet.</div>"
                )
            else:
                update["doctor_card"] = gr.update(
                    value=summary_box_html("Review and confirm your record to see the summary.")
                )
                update["patient_script"] = gr.update(value="")
                update["priority_questions"] = gr.update(value="")
                update["pdf_note"] = gr.update(value="")

        return update

    def _out(state: dict, overrides: dict | None = None) -> list:
        update = _render(state)
        for key, value in (overrides or {}).items():
            update[key] = value
        return [state] + [update[name] for name in order]

    def _error(state: dict, which: str, message: str) -> list:
        if not message:
            return _out(state, {which: gr.update(value="", visible=False)})
        return _out(
            state,
            {which: gr.update(value="**" + esc(message) + "**", visible=True)},
        )

    def _minimal_error(state: dict, which: str, message: str, step: int) -> list:
        update = {name: gr.update() for name in order}
        update["s1"] = gr.update(visible=step == 1)
        update["s2"] = gr.update(visible=step == 2)
        update["s3"] = gr.update(visible=step == 3)
        update["s4"] = gr.update(visible=step == 4)
        update[which] = gr.update(value="**" + esc(message) + "**", visible=True)
        return [state] + [update[name] for name in order]

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #
    def on_toggle_reporting(value):
        return gr.update(visible=(value == "Someone else"))

    def on_start(state, symptoms, age, sex):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 1:
            return _out(state)
        symptoms = (symptoms or "").strip()
        if not symptoms:
            return _error(state, "s1_error", "Please describe your symptoms first.")

        _refresh_alerts_from_text(state, symptoms)

        details = {}
        age_value = _coerce_age(age)
        if age_value is not None:
            details["patient_age"] = age_value
        if sex in SEX_VALUES:
            details["patient_sex"] = sex

        captured = state["token"]
        try:
            record = backend.extract_record(symptoms, details)
        except Exception as exc:
            return _error(state, "s1_error", _safe_llm_message(exc))

        state = commit_if_current(state, captured, state)
        touch(state)
        state["rev"] += 1
        state["record"] = record_to_dict(record)
        state["asked"] = []
        state["skipped"] = []
        state["summary"] = None
        state["summary_rev"] = -1
        _refresh_alerts_from_record(state, record)
        state["question"] = backend.choose_follow_up_question(
            record, state["asked"], state["skipped"]
        )
        state["step"] = 2 if state["question"] is not None else 3
        return _out(state, {"s1_error": gr.update(value="", visible=False)})

    def on_answer(state, answer):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 2 or not state.get("question"):
            return _out(state)
        reply = (answer or "").strip()
        if not reply:
            return _error(state, "s2_error", "Type an answer, or choose Skip.")

        captured = state["token"]
        record = _dict_to_record(state["record"])
        merge_failed = False
        try:
            record = backend.merge_answer(record, state["question"], reply)
        except Exception:
            merge_failed = True
            record = record if record is not None else empty_record()

        state = commit_if_current(state, captured, state)
        touch(state)
        state["rev"] += 1
        state["asked"].append(QuestionAnswer(state["question"], reply))
        state["record"] = record_to_dict(record)
        state["summary"] = None
        state["summary_rev"] = -1
        _refresh_alerts_from_record(state, record)
        state["question"] = backend.choose_follow_up_question(
            record, state["asked"], state["skipped"]
        )
        if state["question"] is None:
            state["step"] = 3

        notice = (
            "Your answer was saved, but VisitPrep could not process it right "
            "now. You can continue."
            if merge_failed
            else ""
        )
        return _out(state, {
            "s2_error": gr.update(value="", visible=False),
            "s2_notice": gr.update(
                value="**" + esc(notice) + "**" if notice else "",
                visible=bool(notice),
            ),
        })

    def on_skip(state):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 2 or not state.get("question"):
            return _out(state)
        touch(state)
        state["rev"] += 1
        state["skipped"].append(state["question"])
        record = _dict_to_record(state["record"])
        state["question"] = backend.choose_follow_up_question(
            record, state["asked"], state["skipped"]
        )
        if state["question"] is None:
            state["step"] = 3
        return _out(state, {
            "s2_error": gr.update(value="", visible=False),
            "s2_notice": gr.update(value="", visible=False),
        })

    def on_finish(state):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 2:
            return _out(state)
        touch(state)
        state["rev"] += 1
        state["step"] = 3
        return _out(state)

    def on_back_from_questions(state):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 2:
            return _out(state)
        touch(state)
        state["rev"] += 1
        state["step"] = 1
        record = _dict_to_record(state.get("record"))
        overrides = {
            "symptom_text": gr.update(value=(record.complaint or "") if record else ""),
            "patient_age": gr.update(value=(record.patient_age if record else None)),
            "patient_sex": gr.update(value=(record.patient_sex or "") if record else ""),
            "s1_error": gr.update(value="", visible=False),
        }
        return _out(state, overrides)

    def on_back_from_review(state):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 3:
            return _out(state)
        touch(state)
        state["rev"] += 1
        record = _dict_to_record(state.get("record"))
        base = record if record is not None else empty_record()
        state["question"] = backend.choose_follow_up_question(
            base, state["asked"], state["skipped"]
        )
        state["step"] = 2 if state["question"] is not None else 3
        return _out(state)

    def on_confirm(
        state, complaint, symptoms, onset, duration, severity, severity_note,
        medicines, medicines_none, allergies, allergies_none, history,
        history_none, concerns, age, sex, reporting_val, rel,
    ):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 3:
            return _out(state)
        complaint = (complaint or "").strip()
        if not complaint and not list_from_text(symptoms):
            return _minimal_error(
                state, "s3_error",
                "Please describe the complaint or at least one symptom.", 3,
            )

        existing = _dict_to_record(state.get("record")) or empty_record()
        medicine_list = medicines_from_text(medicines) if not medicines_none else []
        allergies_list = list_from_text(allergies) if not allergies_none else []
        history_list = list_from_text(history) if not history_none else []

        age_value = _coerce_age(age)
        existing_age = existing.patient_age
        if age_value is None:
            patient_age: int | None = None
            patient_age_text: str | None = None
        elif existing is not None and age_value == existing_age:
            patient_age = age_value
            patient_age_text = existing.patient_age_text
        else:
            patient_age = age_value
            patient_age_text = str(age_value)

        record_data = record_to_dict(existing)
        record_data.update({
            "patient_age": patient_age,
            "patient_age_text": patient_age_text,
            "patient_sex": sex if sex in SEX_VALUES else None,
            "reporting_on_behalf": _label_to_reporting(reporting_val),
            "reporter_relationship": (rel or "").strip() or None,
            "complaint": complaint or None,
            "symptoms": list_from_text(symptoms),
            "onset": (onset or "").strip() or None,
            "duration": (duration or "").strip() or None,
            "severity": severity if severity in ("mild", "moderate", "severe") else None,
            "severity_note": (severity_note or "").strip() or None,
            "medicines": [asdict(m) for m in medicine_list],
            "medicines_denied": True if medicines_none else (False if medicine_list else None),
            "allergies": allergies_list,
            "allergies_denied": True if allergies_none else (False if allergies_list else None),
            "medical_history": history_list,
            "medical_history_denied": True if history_none else (False if history_list else None),
            "concerns": list_from_text(concerns),
        })

        try:
            record = record_from_dict(record_data)
        except SchemaError as exc:
            return _minimal_error(state, "s3_error", str(exc), 3)
        recompute_missing_information(record)

        captured = state["token"]
        try:
            summary = backend.generate_summary(record, state["asked"])
        except Exception as exc:
            return _minimal_error(state, "s3_error", _safe_llm_message(exc), 3)

        state = commit_if_current(state, captured, state)
        touch(state)
        state["rev"] += 1
        state["record"] = record_to_dict(record)
        _refresh_alerts_from_record(state, record)
        state["summary"] = {
            "doctor_card": summary.doctor_card,
            "patient_script": summary.patient_script,
            "priority_questions": list(summary.priority_questions),
        }
        state["summary_rev"] = state["rev"]
        state["step"] = 4
        return _out(state, {"s3_error": gr.update(value="", visible=False)})

    def on_back_from_output(state):
        state = copy.deepcopy(state) if state else new_state()
        if state.get("step") != 4:
            return _out(state)
        touch(state)
        state["rev"] += 1
        state["summary"] = None
        state["summary_rev"] = -1
        state["step"] = 3
        return _out(state)

    def on_reset(state):
        previous_token = state.get("token", 0) if state else 0
        state = new_state()
        state["token"] = previous_token + 1
        return _out(state, {
            "symptom_text": gr.update(value=""),
            "patient_age": gr.update(value=None),
            "patient_sex": gr.update(value=""),
            "s1_error": gr.update(value="", visible=False),
            "s2_error": gr.update(value="", visible=False),
            "s2_notice": gr.update(value="", visible=False),
            "s3_error": gr.update(value="", visible=False),
        })

    def on_load_fixture(state, fixture_name):
        state = copy.deepcopy(state) if state else new_state()
        fixture = all_fixtures().get(fixture_name)
        if fixture is None:
            return _out(state)
        record = copy.deepcopy(fixture)
        touch(state)
        state["rev"] += 1
        state["record"] = record_to_dict(record)
        state["asked"] = []
        state["skipped"] = []
        state["summary"] = None
        state["summary_rev"] = -1
        _refresh_alerts_from_record(state, record)
        state["question"] = backend.choose_follow_up_question(
            record, state["asked"], state["skipped"]
        )
        state["step"] = 2 if state["question"] is not None else 3
        return _out(state)

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #
    state_component = gr.State(value=new_state())

    review_reporting.change(fn=on_toggle_reporting, inputs=review_reporting, outputs=review_rel)

    continue_button.click(
        fn=on_start,
        inputs=[state_component, symptom_text, patient_age, patient_sex],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    answer_button.click(
        fn=on_answer,
        inputs=[state_component, answer_input],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    skip_button.click(
        fn=on_skip,
        inputs=[state_component],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    finish_button.click(
        fn=on_finish,
        inputs=[state_component],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    back2_button.click(
        fn=on_back_from_questions,
        inputs=[state_component],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    confirm_button.click(
        fn=on_confirm,
        inputs=[state_component, review_complaint, review_symptoms, review_onset,
                review_duration, review_severity, review_severity_note,
                review_medicines, review_medicines_none, review_allergies,
                review_allergies_none, review_history, review_history_none,
                review_concerns, review_age, review_sex, review_reporting, review_rel],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    back3_button.click(
        fn=on_back_from_review,
        inputs=[state_component],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    back4_button.click(
        fn=on_back_from_output,
        inputs=[state_component],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    reset.click(
        fn=on_reset,
        inputs=[state_component],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )
    load_button.click(
        fn=on_load_fixture,
        inputs=[state_component, fixture_dropdown],
        outputs=[state_component] + [components[n] for n in order],
        trigger_mode="once",
    )