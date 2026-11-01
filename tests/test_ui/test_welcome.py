"""UI smoke checks.

Owned by Person 2. Requires the runtime dependencies (gradio) to be installed.
"""

import gradio as gr

from ui.welcome import build_welcome


def test_build_welcome_is_callable():
    assert callable(build_welcome)


def test_build_welcome_renders_into_blocks():
    with gr.Blocks() as demo:
        build_welcome()
    assert demo is not None