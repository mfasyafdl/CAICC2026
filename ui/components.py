"""Rendering helpers for the VisitPrep UI.

Owned by Person 2. Rendering only — no business logic. Patient text is always
HTML-escaped before it reaches the browser, so patient wording is displayed
safely and can never inject markup.
"""

from __future__ import annotations

from html import escape


def esc(value) -> str:
    """HTML-escape any value (patient text included) for safe display."""
    if value is None:
        return ""
    return escape(str(value))


def nl2br(text) -> str:
    """Replace newlines with ``<br>`` tags; the caller must HTML-escape first."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def alert_placeholder() -> str:
    """Reserve space for the persistent alerts area even when empty."""
    return '<div class="alerts"><div class="alert-empty" aria-label="no alerts"></div></div>'


def alerts_html(alerts) -> str:
    """Render a list of ``core.schema.Alert`` objects as safe HTML blocks."""
    if not alerts:
        return alert_placeholder()
    parts = []
    for alert in alerts:
        level = getattr(alert, "level", "attention")
        css = "alert-urgent" if level == "urgent" else "alert-attention"
        label = "Urgent" if level == "urgent" else "Attention"
        parts.append(
            '<div class="alert %s">'
            '<span class="alert-badge">%s</span>'
            '<span class="alert-msg">%s</span>'
            "</div>" % (css, esc(label), esc(alert.message))
        )
    return '<div class="alerts">%s</div>' % "".join(parts)


def alerts_error_html() -> str:
    """Show a visible note when alerts could not be checked."""
    return (
        '<div class="alerts"><div class="alert alert-attention">'
        '<span class="alert-badge">Warning</span>'
        '<span class="alert-msg">Alerts could not be checked.</span>'
        "</div></div>"
    )


def summary_box_html(text) -> str:
    """Safe, escaped summary card / script box."""
    return '<div class="summary-box">%s</div>' % nl2br(esc(text))


def question_box_html(text) -> str:
    """Safe, escaped follow-up question box."""
    return '<div class="question-box">%s</div>' % esc(text)


def priority_list_html(questions) -> str:
    """Safe, escaped list of priority questions."""
    items = "".join("<li>%s</li>" % esc(q) for q in (questions or []))
    return '<ol class="priority-list">%s</ol>' % items


MOBILE_CSS = """
:root {
  --vp-accent: #2563eb;
  --vp-border: #d7dbe3;
  --vp-bg: #ffffff;
  --vp-text: #1f2937;
}

#visitprep-root {
  max-width: 680px;
  margin: 0 auto;
  padding: 8px 14px 32px;
  color: var(--vp-text);
  box-sizing: border-box;
}

/* Persistent rule-based alert area (reserved even when empty). */
.alerts {
  min-height: 20px;
  margin: 10px 0;
}
.alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 0.95rem;
  line-height: 1.35;
}
.alert-urgent {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
}
.alert-attention {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  color: #92400e;
}
.alert-badge {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.alert-msg {
  min-width: 0;
}
.alert-empty {
  min-height: 20px;
}

#fixture-banner {
  margin: 10px 0;
}
.fixture-box {
  padding: 10px 12px;
  border-radius: 8px;
  background: #eef2ff;
  border: 1px dashed #818cf8;
  color: #3730a3;
  font-size: 0.9rem;
  line-height: 1.4;
}

#core-notice {
  font-size: 0.9rem;
  color: #991b1b;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fef2f2;
}

#privacy-note {
  font-size: 0.82rem;
  color: #6b7280;
  border: 1px solid var(--vp-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: #f9fafb;
}

#privacy-note p { margin: 0.25rem 0; }

.summary-box,
.question-box {
  border: 1px solid var(--vp-border);
  border-radius: 8px;
  padding: 12px 14px;
  background: #f9fafb;
  color: #1f2937;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 0.98rem;
  line-height: 1.5;
  margin: 8px 0;
}
.question-box { font-weight: 600; }
.priority-list { padding-left: 1.2rem; margin: 8px 0; }
.priority-list li { margin: 4px 0; }
.field-help { font-size: 0.78rem; color: #6b7280; margin-top: 2px; }

/* Readable at 375px mobile width. */
@media (max-width: 480px) {
  #visitprep-root {
    padding: 4px 10px 24px;
  }
  #visitprep-root .block,
  #visitprep-root .form,
  #visitprep-root .wrap,
  #visitprep-root .panel {
    width: 100% !important;
    min-width: 0 !important;
  }
  #visitprep-root textarea,
  #visitprep-root input,
  #visitprep-root select {
    font-size: 16px !important;
  }
  #visitprep-root button {
    width: 100% !important;
    min-height: 42px;
  }
  #visitprep-root .row {
    gap: 6px;
  }
}
"""

PRIVACY_NOTE = (
    "**About your information:** the notes you submit are sent to ModelScope "
    "for processing. Please do not include your name, address, phone number, "
    "or other identifying details. Submitted notes are not guaranteed to be "
    "deleted by the provider, and closing this tab does not delete them right "
    "away."
)

FIXTURE_BANNER = (
    "Preview mode — fictional sample data. The core pipeline is still being "
    "built, so this interface currently uses the fictional fixtures from "
    "core/fixtures.py. No real ModelScope call is made yet."
)