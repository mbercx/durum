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
def test_annotation_shapes(annotation, expected, make_module, assert_compiles):
    """Cross-shape regression net for the renderer (builtins, unions, generics, `Literal`, `Optional`)."""
    cfg = type(
        "Cfg",
        (BaseModel,),
        {"__annotations__": {"x": annotation}, "x": None},
    )

    source = generate_views(make_module("demo", cfg))
    assert_compiles(source)
    assert expected in source


def test_user_type_is_imported(make_module, assert_compiles):
    """Non-builtin field types get added to `user_types` and emitted as `from <module> import ...`."""

    class Color:
        pass

    class Cfg(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        color: Color = Field(default_factory=Color)

    module = make_module("demo", Cfg)
    setattr(module, "Color", Color)
    Color.__module__ = "demo"

    source = generate_views(module)
    assert_compiles(source)

    assert "from demo import Color" in source
    assert "color: Color" in source


def test_user_type_from_other_module_imports_correctly(make_module, assert_compiles):
    """Non-builtin types imported from outside the target module are
    grouped by their own `__module__`, not the codegen target module.

    For example a schema that uses `pathlib.Path` must emit
    `from pathlib import Path`, not
    `from <target_module> import Path`.
    """
    from pathlib import Path

    class Cfg(BaseModel):
        path: Path = Path(".")

    source = generate_views(make_module("demo", Cfg))
    assert_compiles(source)

    assert "from demo import Path" not in source
    assert "import Path" in source
    assert "path: Path" in source


def test_private_submodule_resolves_to_public_parent(make_module, assert_compiles):
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

        source = generate_views(make_module("demo", Cfg))
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


def test_nested_class_is_imported_via_outer_name(make_module, assert_compiles):
    """A nested user type (qualname `Outer.Inner`) is referenced via its
    dotted qualname, and only the outer class is imported.

    The bare nested name is not importable from the source module, so the
    renderer must walk up to the outermost enclosing class for the import
    and emit `Outer.Inner` at every use site.
    """

    class Cfg(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        item: NestedOuter.NestedInner = Field(default_factory=NestedOuter.NestedInner)

    module = make_module("demo", Cfg)
    module.NestedOuter = NestedOuter
    NestedOuter.__module__ = "demo"
    NestedOuter.NestedInner.__module__ = "demo"
    sys.modules["demo"] = module
    try:
        source = generate_views(module)
    finally:
        del sys.modules["demo"]
    assert_compiles(source)

    assert "from demo import NestedOuter" in source
    assert "from demo import NestedInner" not in source
    assert "item: NestedOuter.NestedInner" in source


def test_field_description_becomes_attribute_docstring(make_module, assert_compiles):
    """`Field(description=...)` → attribute docstring on the next line; missing description → none."""

    class Calc(BaseModel):
        kind: str = Field(default="scf", description="Calculation type")
        spin: bool = False

    source = generate_views(make_module("demo", Calc))
    assert_compiles(source)

    assert '    kind: str\n    """Calculation type"""' in source
    assert '"""' not in source.split("spin: bool", 1)[1].split("\n", 2)[1]


def test_field_default_is_not_emitted(make_module, assert_compiles):
    """Defaults belong on the schema (`BaseModel`), not on the view — view is a typed accessor over `_data`."""

    class Calc(BaseModel):
        kind: str = "scf"
        count: int = 42

    source = generate_views(make_module("demo", Calc))
    assert_compiles(source)

    assert "scf" not in source
    assert "42" not in source
    assert "kind: str" in source
    assert "count: int" in source


def test_header_contains_required_imports(make_module):
    """Generated docstring + the three unconditional imports are always present."""

    class Cfg(BaseModel):
        x: int = 0

    source = generate_views(make_module("demo", Cfg))

    assert source.startswith('"""Generated by `dough generate-views` from `demo`.')
    assert "from __future__ import annotations" in source
    assert "from typing import Literal" in source
    assert "from dough.inputs import InputView" in source


def test_empty_module(make_module, assert_compiles):
    """Module with no `BaseModel`s → valid empty output, no crash."""
    source = generate_views(make_module("demo"))
    assert_compiles(source)

    assert "class " not in source
    assert "from dough.inputs import InputView" in source


def test_imported_basemodel_is_skipped(assert_compiles):
    """Only `BaseModel`s defined in the target module get views; re-exported ones are skipped."""

    class Defined(BaseModel):
        x: int = 0

    class Imported(BaseModel):
        y: int = 0

    Imported.__module__ = "elsewhere"

    module = types.ModuleType("demo")
    Defined.__module__ = "demo"
    module.Defined = Defined
    module.Imported = Imported

    source = generate_views(module)
    assert_compiles(source)

    assert "class DefinedView(InputView):" in source
    assert "class ImportedView(InputView):" not in source


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="pydantic on Python 3.10/3.11 strips the generic argument from "
    "`list[Model]` annotations, defeating the rendered-annotation assertion.",
)
def test_list_element_model_gets_no_view(make_module, assert_compiles):
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

    source = generate_views(make_module("demo", Row, Card))
    assert_compiles(source)

    assert "class CardView(InputView):" in source
    assert "class RowView" not in source
    assert "rows: list[Row]" in source
    assert "from demo import Row" in source


def test_multi_member_union_assigns_base_path_to_all_variants(
    make_module, assert_compiles
):
    """A discriminated union of submodels at one field assigns `_base_path`
    to every variant.

    A field annotated `A | B | C` accepts any of the three; all three need
    to know the same dotted path in `_data` so the user can mount whichever
    variant matches their schema instance. The renderer should also fall
    back from a sub-view reference (which can only point at one class) to
    rendering the raw union.
    """

    class A(BaseModel):
        a: int = 0

    class B(BaseModel):
        b: int = 0

    class C(BaseModel):
        c: int = 0

    class Root(BaseModel):
        choice: A | B | C = Field(default_factory=A)

    source = generate_views(make_module("demo", A, B, C, Root))
    assert_compiles(source)

    assert 'class AView(InputView):\n    _base_path = "choice"' in source
    assert 'class BView(InputView):\n    _base_path = "choice"' in source
    assert 'class CView(InputView):\n    _base_path = "choice"' in source
    assert "choice: A | B | C" in source


def test_optional_submodel_is_not_treated_as_container(make_module, assert_compiles):
    """A `Foo | None` field must still get a sub-view, not be dropped as a container element.

    Regression guard: the container-element pass only fires on real
    container origins (`list`, `tuple`, ...); unions of `Foo | None`
    must continue to produce a typed sub-view for `Foo`.
    """

    class Inner(BaseModel):
        x: int = 0

    class Outer(BaseModel):
        inner: Inner | None = None

    source = generate_views(make_module("demo", Inner, Outer))
    assert_compiles(source)

    assert "class InnerView(InputView):" in source
    assert "inner: InnerView" in source


def test_subclasses_of_container_element_are_also_dropped(make_module, assert_compiles):
    """Polymorphic list elements: subclasses of a container-element type
    are themselves treated as elements.

    A `list[Base]` field accepts any subclass of `Base`; none of those
    subclasses can anchor a static view either, so they must also be dropped.
    """

    class Param(BaseModel):
        value: float

    class SubParam(Param):
        u: float = 0.0

    class Card(BaseModel):
        params: list[Param]

    source = generate_views(make_module("demo", Param, SubParam, Card))
    assert_compiles(source)

    assert "class CardView(InputView):" in source
    assert "class ParamView" not in source
    assert "class SubParamView" not in source


def test_field_less_model_is_dropped(make_module, assert_compiles):
    """A model that declares no fields gets no view.

    An empty view has nothing to read or write and would surface as an
    unreferenced root candidate, breaking `_base_path` resolution for
    everything else in the module.
    """

    class Empty(BaseModel):
        pass

    class Real(BaseModel):
        x: int = 0

    source = generate_views(make_module("demo", Empty, Real))
    assert_compiles(source)

    assert "class EmptyView" not in source
    assert "class RealView(InputView):" in source


def test_parent_only_base_class_is_dropped(make_module, assert_compiles):
    """A `BaseModel` subclass used only as a base for other module classes
    gets no view of its own.

    Schema authors commonly declare field-less marker bases that contribute
    only inheritance scaffolding. Without dropping them, codegen would emit
    empty views and the walker would see multiple unreferenced "roots",
    breaking `_base_path` resolution.
    """

    class Marker(BaseModel):
        """Field-less base — used only as scaffolding."""

    class Real(Marker):
        x: int = 0

    source = generate_views(make_module("demo", Marker, Real))
    assert_compiles(source)

    assert "class RealView(InputView):" in source
    assert "class MarkerView" not in source


def test_aliased_class_emits_one_view(make_module, assert_compiles):
    """A class bound to multiple names in the module is rendered once.

    Module-level aliases (`Card = BaseModel`) are a common re-export idiom;
    the codegen must dedupe by class identity rather than emit one view per
    name, otherwise the second definition shadows the first and root
    resolution gets confused.
    """

    class Cfg(BaseModel):
        x: int = 0

    module = make_module("demo", Cfg)
    module.Alias = Cfg  # second name pointing at the same class

    source = generate_views(module)
    assert_compiles(source)

    assert source.count("class CfgView(InputView):") == 1
    assert "class AliasView" not in source


def test_single_root_nested_tree(make_module, assert_compiles):
    """Schema tree with one root → each model gets the correct dotted `_base_path`."""

    class Leaf(BaseModel):
        value: int = 0

    class Mid(BaseModel):
        leaf: Leaf = Leaf()

    class Root(BaseModel):
        mid: Mid = Mid()

    source = generate_views(make_module("demo", Leaf, Mid, Root))
    assert_compiles(source)

    assert "class RootView(InputView):" in source
    assert 'class MidView(InputView):\n    _base_path = "mid"' in source
    assert 'class LeafView(InputView):\n    _base_path = "mid.leaf"' in source
    assert (
        '_base_path = "' not in source.split("class RootView", 1)[1].split("\n\n", 1)[0]
    )

    assert "mid: MidView" in source
    assert "leaf: LeafView" in source
    assert "value: int" in source


def test_ambiguous_root_leaves_paths_empty(make_module, assert_compiles):
    """Two unrelated top-level models → no single root, so no `_base_path` is emitted."""

    class A(BaseModel):
        x: int = 0

    class B(BaseModel):
        y: int = 0

    source = generate_views(make_module("demo", A, B))
    assert_compiles(source)

    assert "_base_path" not in source


def test_mutual_reference_falls_back_to_empty_paths(make_module, assert_compiles):
    """Mutual reference → both models in `referenced`, no single root, fallback to empty paths."""

    class A(BaseModel):
        b: "B | None" = None

    class B(BaseModel):
        a: "A | None" = None

    # Resolve forward-refs now that both classes exist in scope.
    A.model_rebuild()
    B.model_rebuild()

    source = generate_views(make_module("demo", A, B))
    assert_compiles(source)

    assert "_base_path" not in source
    assert "b: BView" in source
    assert "a: AView" in source


def test_self_reference_raises(make_module):
    """Self-referential input schema → `TypeError` (recursive inputs make no sense)."""

    class Node(BaseModel):
        child: "Node | None" = None

    # Resolve the forward-ref string `"Node | None"` to the actual `Node` class
    # now that `Node` exists in scope. Without this, `field.annotation` stays a
    # ForwardRef and `submodel_of` returns None, hiding the cycle.
    Node.model_rebuild()

    with pytest.raises(TypeError, match="cyclic schema"):
        generate_views(make_module("demo", Node))


def test_generated_module_is_executable(make_module):
    """End-to-end: generate, `exec()` against real `InputView`, check classes + `_base_path` survive."""

    class Leaf(BaseModel):
        value: int = 0

    class Root(BaseModel):
        leaf: Leaf = Leaf()

    source = generate_views(make_module("demo", Leaf, Root))

    namespace: dict[str, typing.Any] = {}
    exec(source, namespace)

    assert "RootView" in namespace
    assert "LeafView" in namespace
    assert namespace["LeafView"]._base_path == "leaf"
