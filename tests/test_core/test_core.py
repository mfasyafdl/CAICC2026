"""Smoke tests for the core package.

Owned by Person 1.
"""

import core


def test_core_package_imports():
    assert core.__name__ == "core"


def test_core_version_is_defined():
    assert isinstance(core.__version__, str)
    assert core.__version__ == "0.1.0"