"""Tests for `generate_views` against PEP 695 (Python 3.12+) syntax.

Lives in a separate file so the `type X = ...` syntax — a hard `SyntaxError`
on Python 3.10 / 3.11 — does not break collection on older interpreters.
The conftest's `collect_ignore` skips this file outside 3.12+.
"""

from typing import Annotated

from pydantic import BaseModel, Field

from dough.codegen import generate_views


def test_pep_695_type_alias_is_unwrapped(assert_compiles):
    """A PEP 695 `type X = T` alias is rendered as the underlying `T`.

    PEP 695 aliases are `TypeAliasType` instances, not classes;
    `typing.get_origin` returns `None`, so the renderer must explicitly
    recurse on `alias.__value__` to reach the wrapped type.
    """
    type Width = int

    class Cfg(BaseModel):
        w: Width = 0

    source = generate_views(Cfg)
    assert_compiles(source)

    assert "w: int" in source
    assert "Width" not in source


def test_pep_695_alias_over_annotated_is_unwrapped(assert_compiles):
    """A PEP 695 alias wrapping `Annotated[T, Field(...)]` collapses to `T`.

    Pydantic strips `Annotated` metadata from `field.annotation` on direct
    field declarations, but a `TypeAliasType` hides the inner `Annotated`
    from pydantic. After the alias unwrap recurses on `alias.__value__`,
    the renderer must then unwrap the revealed `Annotated[T, ...]` to `T`.
    """
    type PositiveInt = Annotated[int, Field(gt=0)]

    class Cfg(BaseModel):
        n: PositiveInt = 1

    source = generate_views(Cfg)
    assert_compiles(source)

    assert "n: int" in source
    assert "PositiveInt" not in source
    assert "Annotated" not in source
    assert "Field" not in source
