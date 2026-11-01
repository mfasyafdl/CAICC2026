"""VisitPrep - doctor-visit preparation app.

Entry point for the Gradio Blocks application.

Owned by Person 2 (UI + deployment). See docs/data_contract.md for the
fields exchanged with core/.
"""

import os

import gradio as gr

from ui.welcome import build_welcome

APP_NAME = "VisitPrep"
APP_VERSION = "0.1.0"

_DISCLAIMER = (
    "**Important:** VisitPrep only organizes the information you provide. "
    "It does not diagnose conditions, give medical advice, or recommend "
    "treatment. Always consult a qualified healthcare professional."
)


def build_app() -> gr.Blocks:
    """Assemble and return the Gradio Blocks interface."""
    with gr.Blocks(title=APP_NAME) as demo:
        gr.Markdown("# VisitPrep")
        gr.Markdown(
            "Prepare for your doctor visit by describing your symptoms. "
            "VisitPrep turns what you report into a clear summary and a short "
            "script you can read to your doctor."
        )
        gr.Markdown(_DISCLAIMER)
        build_welcome()
    return demo


if __name__ == "__main__":
    build_app().queue().launch(
        server_name=os.environ.get("SERVER_NAME", "0.0.0.0"),
        server_port=int(os.environ.get("PORT", "7860")),
        theme=gr.themes.Soft(),
    )