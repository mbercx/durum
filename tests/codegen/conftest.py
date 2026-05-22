"""Shared fixtures for `generate_views` tests."""

import sys

import pytest

# PEP 695 syntax (`type X = ...`) is a hard `SyntaxError` on Python 3.10/3.11,
# so the dedicated test module cannot even be imported there.
collect_ignore = []
if sys.version_info < (3, 12):
    collect_ignore.append("test_views_pep695.py")


@pytest.fixture
def assert_compiles():
    """Assert that the given source string is syntactically valid Python."""

    def _assert(source: str) -> None:
        compile(source, "<generated>", "exec")

    return _assert
