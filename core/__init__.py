"""Core package for VisitPrep.

Owned by Person 1.

Holds all non-UI logic: the shared schema (``schema``), fictional fixtures
(``fixtures``), the ModelScope LLM client (``llm``), runtime prompts
(``prompts``), and the workflow: extraction (``extract``), follow-up
interview (``interview``), precautionary alerts (``redflag``), and summary
generation (``summarize``). This package must not depend on Gradio or any UI
code so it stays unit-testable in isolation.
"""

__version__ = "0.1.0"