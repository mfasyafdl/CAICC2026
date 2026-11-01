"""Entry builder for the VisitPrep UI.

Owned by Person 2. ``build_welcome`` builds the full four-step interface; the
name is kept for backward compatibility with the scaffold's welcome screen and
its smoke test. See ``ui/flow.py`` for the implementation.
"""

import gradio as gr

from ui.flow import build_interface

__all__ = ["build_welcome"]


def build_welcome() -> None:
    """Render the full interface into the current Blocks context."""
    build_interface()