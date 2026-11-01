"""Core package for VisitPrep.

Owned by Person 1.

Holds all non-UI logic: symptom parsing, follow-up question handling, detail
assembly, summary/script generation, and PDF generation. This package must not
depend on Gradio or any UI code so it stays unit-testable in isolation.
"""

__version__ = "0.1.0"