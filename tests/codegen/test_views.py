"""Tests for `dough.codegen.views.generate_views`.

Tests build a synthetic Python module of pydantic models, run `generate_views`
on it, and check the resulting source string both structurally (substring /
regex checks) and syntactically (`compile()` on the output).
"""

import sys
import types
import typing

import pytest
from pydantic import BaseModel, Field

from dough.codegen import generate_views


@pytest.mark.parametrize(
    "annotation, expected",
    [
        (int, "x: int"),
        (bool, "x: bool"),
        (str | None, "x: str | None"),
        (typing.Optional[int], "x: int | None"),
        (typing.List[str], "x: list[str]"),
        (typing.List[int], "x: list[int]"),
        (typing.Dict[str, int], "x: dict[str, int]"),
        (typing.Literal["scf", "relax", "md"], "x: Literal['scf', 'relax', 'md']"),
    ],
)
def test_annotation_shapes(annotation, expected, assert_compiles):
    """Cross-shape regression net for the renderer (builtins, unions, generics, `Literal`, `Optional`)."""
    cfg = type(
        "Cfg",
        (BaseModel,),
        {"__annotations__": {"x": annotation}, "x": None},
    )

    source = generate_views(cfg)
    assert_compiles(source)
    assert expected in source


def test_user_type_is_imported(assert_compiles):
    """Non-builtin field types get added to `user_types` and emitted as `from <module> import ...`."""

    class Color:
        pass

    class Cfg(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        color: Color = Field(default_factory=Color)

    Color.__module__ = "demo"

    source = generate_views(Cfg)
    assert_compiles(source)

    assert "from demo import Color" in source
    assert "color: Color" in source


def test_user_type_from_other_module_imports_correctly(assert_compiles):
    """Non-builtin types imported from outside the target module are
    grouped by their own `__module__`, not the codegen target module.

    For example a schema that uses `pathlib.Path` must emit
    `from pathlib import Path`, not
    `from <target_module> import Path`.
    """
    from pathlib import Path

    class Cfg(BaseModel):
        path: Path = Path(".")

    Cfg.__module__ = "demo"

    source = generate_views(Cfg)
    assert_compiles(source)

    assert "from demo import Path" not in source
    assert "from pathlib import Path" in source
    assert "path: Path" in source


def test_private_submodule_resolves_to_public_parent(assert_compiles):
    """A user type whose `__module__` points at a private `_submodule`
    that the parent package re-exports gets imported from the parent.

    Mirrors the real-world case on Python 3.13 where
    `Path.__module__ == "pathlib._local"`. The renderer must walk up
    `__module__` and pick the shallowest ancestor that still exposes the
    class by name.
    """
    parent = types.ModuleType("public_pkg")
    private = types.ModuleType("public_pkg._impl")

    class Widget:
        pass

    Widget.__module__ = "public_pkg._impl"
    private.Widget = Widget
    parent.Widget = Widget  # public re-export

    sys.modules["public_pkg"] = parent
    sys.modules["public_pkg._impl"] = private
    try:

        class Cfg(BaseModel):
            model_config = {"arbitrary_types_allowed": True}
            w: Widget = Field(default_factory=Widget)

        source = generate_views(Cfg)
    finally:
        del sys.modules["public_pkg._impl"]
        del sys.modules["public_pkg"]

    assert_compiles(source)
    assert "from public_pkg import Widget" in source
    assert "public_pkg._impl" not in source


class NestedOuter:
    """Fixture for `test_nested_class_is_imported_via_outer_name`.

    Defined at module scope so the inner class's `__qualname__` is the clean
    `NestedOuter.NestedInner` form. A function-local nested class would
    carry a `<test_name>.<locals>.` prefix that defeats the outermost-name
    lookup in the codegen.
    """

    class NestedInner:
        pass


def test_nested_class_is_imported_via_outer_name(assert_compiles):
    """A nested user type (qualname `Outer.Inner`) is referenced via its
    dotted qualname, and only the outer class is imported.

    The bare nested name is not importable from the source module, so the
    renderer must walk up to the outermost enclosing class for the import
    and emit `Outer.Inner` at every use site.
    """

    class Cfg(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        item: NestedOuter.NestedInner = Field(default_factory=NestedOuter.NestedInner)

    NestedOuter.__module__ = "demo"
    NestedOuter.NestedInner.__module__ = "demo"

    demo = types.ModuleType("demo")
    demo.NestedOuter = NestedOuter
    sys.modules["demo"] = demo
    try:
        source = generate_views(Cfg)
    finally:
        del sys.modules["demo"]
    assert_compiles(source)

    assert "from demo import NestedOuter" in source
    assert "from demo import NestedInner" not in source
    assert "item: NestedOuter.NestedInner" in source


def test_field_description_becomes_attribute_docstring(assert_compiles):
    """`Field(description=...)` → attribute docstring on the next line; missing description → none."""

    class Calc(BaseModel):
        kind: str = Field(default="scf", description="Calculation type")
        spin: bool = False

    source = generate_views(Calc)
    assert_compiles(source)

    assert '    kind: str\n    """Calculation type"""' in source
    assert '"""' not in source.split("spin: bool", 1)[1].split("\n", 2)[1]


def test_field_default_is_not_emitted(assert_compiles):
    """Defaults belong on the schema (`BaseModel`), not on the view — view is a typed accessor over `_data`."""

    class Calc(BaseModel):
        kind: str = "scf"
        count: int = 42

    source = generate_views(Calc)
    assert_compiles(source)

    assert "scf" not in source
    assert "42" not in source
    assert "kind: str" in source
    assert "count: int" in source


def test_header_contains_required_imports():
    """Generated docstring + the three unconditional imports are always present."""

    class Cfg(BaseModel):
        x: int = 0

    Cfg.__module__ = "demo"

    source = generate_views(Cfg)

    assert source.startswith('"""Generated by `dough generate-views` from `demo.Cfg`.')
    assert "from __future__ import annotations" in source
    assert "from typing import Literal" in source
    assert "from dough.inputs import InputView" in source


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="pydantic on Python 3.10/3.11 strips the generic argument from "
    "`list[Model]` annotations, defeating the rendered-annotation assertion.",
)
def test_list_element_model_gets_no_view(assert_compiles):
    """A model that only appears as the element type of `list[X]` gets no view.

    List elements have dynamic indices, so they cannot anchor a static
    typed sub-view. They live as raw dicts in `_data`; pydantic validates
    them at write time. The container model still gets a view, while the
    element type is imported as a raw class and rendered as `list[Element]`.
    """

    class Row(BaseModel):
        species: str
        position: tuple[float, float, float]

    class Card(BaseModel):
        units: str
        rows: list[Row]

    Row.__module__ = "demo"

    source = generate_views(Card)
    assert_compiles(source)

    assert "class CardView(InputView):" in source
    assert "class RowView" not in source
    assert "rows: list[Row]" in source
    assert "from demo import Row" in source


def test_multi_member_union_emits_one_view_per_variant(assert_compiles):
    """A discriminated union of submodels at one field emits one view per variant,
    each anchored at the union's mount path, with the parent field annotated as
    a union of those per-variant view names.

    A field annotated `A | B | C` accepts any of the three. Each variant gets
    its own view class so the user can name-disambiguate the variant they
    actually want. All variants share the same `_base_path` (the mount), but
    have distinct class names — derived from the path with the class name
    appended when the path-only name collides.
    """

    class A(BaseModel):
        a: int = 0

    class B(BaseModel):
        b: int = 0

    class C(BaseModel):
        c: int = 0

    class Root(BaseModel):
        choice: A | B | C = Field(default_factory=A)

    source = generate_views(Root)
    assert_compiles(source)

    assert 'class ChoiceAView(InputView):\n    _base_path = "choice"' in source
    assert 'class ChoiceBView(InputView):\n    _base_path = "choice"' in source
    assert 'class ChoiceCView(InputView):\n    _base_path = "choice"' in source
    assert "choice: ChoiceAView | ChoiceBView | ChoiceCView" in source


def test_collision_name_collapses_shared_prefix(assert_compiles):
    """When path-pascal and class name share a prefix, the duplicate is stripped.

    Mirrors the real-world pydantic-espresso shape: `k_points: KPointsListCard
    | KPointsGammaCard` where path-pascal `KPoints` overlaps the class names'
    leading `KPoints`. Without collapse the names would be
    `KPointsKPointsListCardView` / `KPointsKPointsGammaCardView`; the
    `collision_name` helper strips the overlap so they read as
    `KPointsListCardView` / `KPointsGammaCardView`.
    """

    class KPointsListCard(BaseModel):
        kind: typing.Literal["list"] = "list"

    class KPointsGammaCard(BaseModel):
        kind: typing.Literal["gamma"] = "gamma"

    class Root(BaseModel):
        k_points: KPointsListCard | KPointsGammaCard = Field(
            default_factory=KPointsListCard, discriminator="kind"
        )

    source = generate_views(Root)
    assert_compiles(source)

    assert (
        'class KPointsListCardView(InputView):\n    _base_path = "k_points"' in source
    )
    assert (
        'class KPointsGammaCardView(InputView):\n    _base_path = "k_points"' in source
    )
    assert "k_points: KPointsListCardView | KPointsGammaCardView" in source
    assert "KPointsKPoints" not in source


def test_optional_submodel_is_descended_into(assert_compiles):
    """A `Foo | None` field must still get a sub-view, not skipped as a container.

    `submodels_of` returns `[Foo]` for `Foo | None`, so the walker descends
    through optional submodel fields and emits a typed sub-view for them.
    """

    class Inner(BaseModel):
        x: int = 0

    class Outer(BaseModel):
        inner: Inner | None = None

    source = generate_views(Outer)
    assert_compiles(source)

    assert "class InnerView(InputView):" in source
    assert "inner: InnerView" in source


def test_field_less_sub_mount_emits_valid_empty_view(assert_compiles):
    """A field-less submodel mounted under a root still emits a valid view.

    The view has no leaf fields, but the `_base_path` line makes its class
    body non-empty so the rendered file still compiles. Users assigning
    fields under that path go via the `_data` dict; the empty view is just
    a typed anchor for the path.
    """

    class Empty(BaseModel):
        pass

    class Root(BaseModel):
        x: int = 0
        empty: Empty = Empty()

    source = generate_views(Root)
    assert_compiles(source)

    assert "class RootView(InputView):" in source
    assert 'class EmptyView(InputView):\n    _base_path = "empty"' in source
    assert "empty: EmptyView" in source


def test_same_class_at_two_paths_emits_two_views(assert_compiles):
    """The same submodel mounted at two different paths emits two distinct
    views, one per `(model, path)` pair.

    This is the core motivation for per-field naming: each mount gets its
    own `_base_path`, and the view names are derived from the path rather
    than the class so the two views never collide.
    """

    class Foo(BaseModel):
        x: int = 0

    class Root(BaseModel):
        a: Foo = Foo()
        b: Foo = Foo()

    source = generate_views(Root)
    assert_compiles(source)

    assert 'class AView(InputView):\n    _base_path = "a"' in source
    assert 'class BView(InputView):\n    _base_path = "b"' in source
    assert "a: AView" in source
    assert "b: BView" in source


def test_single_root_nested_tree(assert_compiles):
    """Schema tree with one root → each model gets the correct dotted `_base_path`."""

    class Leaf(BaseModel):
        value: int = 0

    class Mid(BaseModel):
        leaf: Leaf = Leaf()

    class Root(BaseModel):
        mid: Mid = Mid()

    source = generate_views(Root)
    assert_compiles(source)

    assert "class RootView(InputView):" in source
    assert 'class MidView(InputView):\n    _base_path = "mid"' in source
    assert 'class MidLeafView(InputView):\n    _base_path = "mid.leaf"' in source
    assert (
        '_base_path = "' not in source.split("class RootView", 1)[1].split("\n\n", 1)[0]
    )

    assert "mid: MidView" in source
    assert "leaf: MidLeafView" in source
    assert "value: int" in source


def test_mutual_reference_raises():
    """Mutually-referencing schemas raise `TypeError`.

    `A` references `B` which references `A`. The walker descends into both
    and detects the cycle the second time it visits `A`. Like self-reference,
    mutual reference makes no sense as a `_data` schema — there is no static
    dotted path that anchors a model reachable from itself.
    """

    class A(BaseModel):
        b: "B | None" = None

    class B(BaseModel):
        a: "A | None" = None

    A.model_rebuild()
    B.model_rebuild()

    with pytest.raises(TypeError, match="cyclic schemas are not supported"):
        generate_views(A)


def test_self_reference_raises():
    """Self-referential input schema → `TypeError` (recursive inputs make no sense)."""

    class Node(BaseModel):
        child: "Node | None" = None

    # Resolve the forward-ref string `"Node | None"` to the actual `Node` class
    # now that `Node` exists in scope. Without this, `field.annotation` stays a
    # ForwardRef and `submodels_of` returns an empty list, hiding the cycle.
    Node.model_rebuild()

    with pytest.raises(TypeError, match="cyclic schemas are not supported"):
        generate_views(Node)


def test_generated_module_is_executable():
    """End-to-end: generate, `exec()` against real `InputView`, check classes + `_base_path` survive."""

    class Leaf(BaseModel):
        value: int = 0

    class Root(BaseModel):
        leaf: Leaf = Leaf()

    source = generate_views(Root)

    namespace: dict[str, typing.Any] = {}
    exec(source, namespace)

    assert "RootView" in namespace
    assert "LeafView" in namespace
    assert namespace["LeafView"]._base_path == "leaf"
