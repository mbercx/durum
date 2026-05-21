"""Tests for `generate_views` against PEP 695 (Python 3.12+) syntax.

Lives in a separate file so the `type X = ...` syntax — a hard `SyntaxError`
on Python 3.10 / 3.11 — does not break collection on older interpreters.
The conftest's `collect_ignore` skips this file outside 3.12+.
"""

from pydantic import BaseModel

from dough.codegen import generate_views


def test_pep_695_type_alias_is_unwrapped(make_module, assert_compiles):
    """A PEP 695 `type X = T` alias is rendered as the underlying `T`.

    PEP 695 aliases are `TypeAliasType` instances, not classes;
    `typing.get_origin` returns `None`, so the renderer must explicitly
    recurse on `alias.__value__` to reach the wrapped type.
    """
    type Width = int

    class Cfg(BaseModel):
        w: Width = 0

    source = generate_views(make_module("demo", Cfg))
    assert_compiles(source)

    assert "w: int" in source
    assert "Width" not in source
