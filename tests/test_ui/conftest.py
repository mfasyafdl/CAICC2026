"""Test configuration for the UI checks.

Forces the preview backend (``VISITPREP_PREVIEW=1``) so the interface is fully
exercisable without a real LLM or a core implementation. This is set before any
test module imports ``ui.*`` (imports are resolved lazily inside the fixtures).
"""

import os

os.environ["VISITPREP_PREVIEW"] = "1"

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def demo():
    import app

    return app.build_app()


@pytest.fixture(scope="session")
def handlers(demo):
    """Map each event-handler ``api_name`` to its underlying function."""
    return {bf.api_name: bf.fn for bf in demo.fns.values()}