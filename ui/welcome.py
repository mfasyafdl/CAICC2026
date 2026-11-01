"""Welcome screen for VisitPrep.

Owned by Person 2.
"""

import gradio as gr


def build_welcome() -> None:
    """Render the welcome / start screen into the current Blocks context."""
    with gr.Column(elem_id="welcome"):
        gr.Markdown("## Welcome")
        gr.Markdown(
            "Report your symptoms in your own words, then answer a few "
            "clarifying questions so you are ready for your appointment."
        )
        gr.Markdown(
            "### How it works\n"
            "1. Describe your symptoms.\n"
            "2. Answer up to five follow-up questions.\n"
            "3. Review and edit the details.\n"
            "4. Get a summary, a short doctor script, and a PDF to download."
        )
        gr.Button("Start", variant="primary", elem_id="start-button")