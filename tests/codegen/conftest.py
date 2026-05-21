"""Shared fixtures for `generate_views` tests."""

import sys
import types

import pytest
from pydantic import BaseModel

# PEP 695 syntax (`type X = ...`) is a hard `SyntaxError` on Python 3.10/3.11,
# so the dedicated test module cannot even be imported there.
collect_ignore = []
if sys.version_info < (3, 12):
    collect_ignore.append("test_views_pep695.py")


@pytest.fixture
def make_module():
    """Build a fake module so each model's `__module__` matches the given name."""

    def _make(name: str, *models: type[BaseModel]) -> types.ModuleType:
        module = types.ModuleType(name)
        for model in models:
            model.__module__ = name
            setattr(module, model.__name__, model)
        return module

    return _make


@pytest.fixture
def assert_compiles():
    """Assert that the given source string is syntactically valid Python."""

    def _assert(source: str) -> None:
        compile(source, "<generated>", "exec")

    return _assert
