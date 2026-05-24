import typing
from textwrap import dedent
from typing import Annotated

from glom import Spec, T

import pytest
import yaml

from dough.converters.base import BaseConverter
from dough import Unit
from dough.outputs.base import BaseOutput, OutputView


# =============================================================================
# Reused fixture classes
# =============================================================================


class DoubleConverter(BaseConverter):
    """Trivial `BaseConverter` subclass that doubles scalar values.

    `BaseOutput.get_output` checks the guard with the short key (`"c"`) but
    calls `convert()` with the dotted key (`"nested.c"`), so both must be
    registered for submapping dispatch to work.
    """

    @classmethod
    def get_conversion_mapping(cls):
        entry = (lambda x: x * 2, T)
        return {"A": entry, "c": entry, "nested.c": entry}


class NestedView(OutputView):
    c: Annotated[int, Spec("b.c"), Unit("eV")]
    d: Annotated[int, Spec("b.d")]
    missing: Annotated[int, Spec("b.nope")]


class DummyView(OutputView):
    A: Annotated[float, Spec("a"), Unit("eV")]
    unmapped: Annotated[int, Spec("b.c")]
    not_parsed: Annotated[str, Spec("e")]
    forces: Annotated[typing.Any, Spec("forces"), Unit("eV/angstrom")]
    nested: NestedView


class DummyOutput(BaseOutput):
    outputs: DummyView
    converters = {"double": DoubleConverter}

    @classmethod
    def from_dir(cls, _: str):
        pass


# =============================================================================
# Shared raw_outputs fixture
# =============================================================================


@pytest.fixture
def raw_outputs():
    """Simple `raw_outputs` for transparent testing."""
    np = pytest.importorskip("numpy")
    data = yaml.safe_load(
        dedent(
            """
            a: 1
            b:
                c: 3
                d: 4
            """
        )
    )
    data["forces"] = np.array([[0.1, 0.0, 0.0], [0.0, 0.2, 0.0]])
    return data


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.parametrize(
    ("spec", "result"),
    [
        ("a", 1),
        ("b.c", 3),
        ("b", {"c": 3, "d": 4}),
    ],
)
def test_get_output_from_spec(raw_outputs, spec, result):
    assert result == DummyOutput(raw_outputs).get_output_from_spec(spec)


def test_list_outputs(raw_outputs):
    assert DummyOutput(raw_outputs).list_outputs() == [
        "A",
        "unmapped",
        "forces",
        "nested",
    ]
    assert DummyOutput(raw_outputs).list_outputs(only_available=False) == [
        "A",
        "unmapped",
        "not_parsed",
        "forces",
        "nested",
    ]


def test_outputs_unavailable_raises(raw_outputs):
    outputs = DummyOutput(raw_outputs).outputs
    with pytest.raises(AttributeError, match="not_parsed.*not available"):
        outputs.not_parsed


def test_get_output_dict(raw_outputs):
    out = DummyOutput(raw_outputs).get_output_dict()
    forces = out.pop("forces")
    assert out == {
        "A": 1,
        "unmapped": 3,
        "nested": {"c": 3, "d": 4},
    }
    assert list(forces.shape) == [2, 3]
    assert DummyOutput(raw_outputs).get_output_dict(["A"]) == {"A": 1}
    with pytest.raises(KeyError):
        DummyOutput(raw_outputs).get_output_dict(["B"])


# --- SubMapping (nested output namespaces) ----------------------------------


def test_submapping_output_access(raw_outputs):
    """Resolved outputs on a sub-namespace are accessible via attribute."""
    outputs = DummyOutput(raw_outputs).outputs
    assert outputs.nested.c == 3
    assert outputs.nested.d == 4


def test_submapping_missing_output_raises(raw_outputs):
    outputs = DummyOutput(raw_outputs).outputs
    with pytest.raises(AttributeError, match="missing.*not available"):
        outputs.nested.missing


def test_submapping_get_output_namespace_returns_dict(raw_outputs):
    """`get_output(<sub-namespace>)` returns a partial dict of available outputs."""
    out = DummyOutput(raw_outputs)
    assert out.get_output("nested") == {"c": 3, "d": 4}
    # Users index the dict directly.
    assert out.get_output("nested")["c"] == 3


# --- Fallback defaults on Annotated fields ------------------------------------


class DefaultsView(OutputView):
    """View with an explicit fallback default on an unparsed field."""

    parsed: Annotated[int, Spec("a")]
    unparsed_default: Annotated[bool, Spec("missing.path")] = False
    unparsed_no_default: Annotated[str, Spec("other.missing")]


class DefaultsOutput(BaseOutput):
    outputs: DefaultsView

    @classmethod
    def from_dir(cls, _: str):
        pass


def test_explicit_default_is_reachable(raw_outputs):
    """Fallback default is returned when the Spec doesn't resolve."""
    outputs = DefaultsOutput(raw_outputs).outputs
    assert outputs.parsed == 1
    assert outputs.unparsed_default is False


def test_unparsed_without_default_raises(raw_outputs):
    """Unparsed field with no explicit default still raises."""
    outputs = DefaultsOutput(raw_outputs).outputs
    with pytest.raises(AttributeError, match="unparsed_no_default.*not available"):
        outputs.unparsed_no_default


def test_explicit_default_not_in_list_outputs(raw_outputs):
    """Fallback default doesn't count as 'available' — field is not listed."""
    assert DefaultsOutput(raw_outputs).list_outputs() == ["parsed"]


# --- get_output with converter (to=...) --------------------------------------


def test_get_output_with_converter(raw_outputs):
    """`get_output(name, to=...)` applies the converter when available."""
    assert DummyOutput(raw_outputs).get_output("A", to="double") == 2  # 1 * 2


def test_get_output_without_matching_converter_passes_through(raw_outputs):
    """When the converter mapping doesn't cover the name, return raw value."""
    assert DummyOutput(raw_outputs).get_output("unmapped", to="double") == 3  # raw b.c


def test_get_output_unsupported_converter_raises(raw_outputs):
    """`get_output(name, to='bad')` raises `ValueError` listing available converters."""
    with pytest.raises(ValueError, match="not supported.*double"):
        DummyOutput(raw_outputs).get_output("A", to="bad")


def test_get_output_submapping_with_converter(raw_outputs):
    """Converter applied per sub-field when the output is a submapping dict."""
    # "nested.c" is in conversion_mapping -> doubled; "nested.d" is not -> raw
    assert DummyOutput(raw_outputs).get_output("nested", to="double") == {
        "c": 6,
        "d": 4,
    }


# --- Boundary / edge-case tests ----------------------------------------------


def test_get_output_nonexistent_name_raises(raw_outputs):
    """`get_output('nonexistent')` raises `KeyError` when name is not in mapping."""
    with pytest.raises(KeyError):
        DummyOutput(raw_outputs).get_output("nonexistent")


def test_submapping_all_specs_fail():
    """Submapping where every sub-spec fails glom returns an empty dict."""
    assert DummyOutput({"x": 1}).get_output("nested") == {}


def test_get_output_to_with_empty_converters_raises(raw_outputs):
    """`get_output(name, to='x')` raises `ValueError` when `converters` is empty."""

    class MView(OutputView):
        A: Annotated[float, Spec("a")]

    class Out(BaseOutput):
        outputs: MView
        converters = {}

        @classmethod
        def from_dir(cls, _: str):
            pass

    with pytest.raises(ValueError, match="not supported"):
        Out(raw_outputs).get_output("A", to="x")


def test_get_output_dict_with_converter(raw_outputs):
    """`get_output_dict(to=...)` applies the converter per-output, passes through unmapped names."""
    out = DummyOutput(raw_outputs).get_output_dict(to="double")
    out.pop("forces")
    assert out == {
        "A": 2,
        "unmapped": 3,
        "nested": {"c": 6, "d": 4},
    }


def test_converter_exception_propagates(raw_outputs):
    """An exception raised inside `convert()` propagates to the caller."""

    def _boom(_):
        raise RuntimeError("converter exploded")

    class BrokenConverter(BaseConverter):
        @classmethod
        def get_conversion_mapping(cls):
            return {"A": (_boom, T)}

    class MView(OutputView):
        A: Annotated[float, Spec("a")]

    class Out(BaseOutput):
        outputs: MView
        converters = {"broken": BrokenConverter}

        @classmethod
        def from_dir(cls, _: str):
            pass

    with pytest.raises(RuntimeError, match="converter exploded"):
        Out(raw_outputs).get_output("A", to="broken")


# =============================================================================
# _unit_from_annotated
# =============================================================================


def test_unit_from_annotated_returns_unit_when_present():
    from dough.outputs.base import _unit_from_annotated

    hint = Annotated[float, Spec("x"), Unit("eV")]
    assert _unit_from_annotated(hint) == Unit("eV")


def test_unit_from_annotated_returns_none_when_absent():
    from dough.outputs.base import _unit_from_annotated

    hint = Annotated[float, Spec("x")]
    assert _unit_from_annotated(hint) is None


def test_unit_from_annotated_returns_none_on_bare_type():
    from dough.outputs.base import _unit_from_annotated

    assert _unit_from_annotated(int) is None
    assert _unit_from_annotated(list[int]) is None


def test_unit_from_annotated_returns_first_when_multiple():
    from dough.outputs.base import _unit_from_annotated

    hint = Annotated[float, Spec("x"), Unit("eV"), Unit("Ha")]
    assert _unit_from_annotated(hint) == Unit("eV")


# =============================================================================
# _spec_from_annotated
# =============================================================================


def test_spec_from_annotated_returns_spec_when_present():
    from dough.outputs.base import _spec_from_annotated

    spec = Spec("x")
    hint = Annotated[float, spec]
    assert _spec_from_annotated(hint) is spec


def test_spec_from_annotated_returns_none_on_bare_type():
    from dough.outputs.base import _spec_from_annotated

    assert _spec_from_annotated(int) is None


def test_spec_from_annotated_returns_none_when_absent():
    from dough.outputs.base import _spec_from_annotated

    hint = Annotated[float, Unit("eV")]
    assert _spec_from_annotated(hint) is None


def test_spec_from_annotated_raises_when_multiple():
    from dough.outputs.base import _spec_from_annotated

    hint = Annotated[float, Spec("x"), Spec("y")]
    with pytest.raises(TypeError, match="multiple Spec entries"):
        _spec_from_annotated(hint)


# =============================================================================
# BaseOutput._field_mapping units
# =============================================================================


def test_field_mapping_flat_with_unit_records_unit(raw_outputs):
    _spec, unit = DummyOutput(raw_outputs)._field_mapping["A"]
    assert unit == Unit("eV")


def test_field_mapping_flat_without_unit_records_none(raw_outputs):
    _spec, unit = DummyOutput(raw_outputs)._field_mapping["unmapped"]
    assert unit is None


def test_field_mapping_submapping_nests_tuples(raw_outputs):
    sub = DummyOutput(raw_outputs)._field_mapping["nested"]
    assert {name: unit for name, (_spec, unit) in sub.items()} == {
        "c": Unit("eV"),
        "d": None,
        "missing": None,
    }


def test_field_mapping_preserves_explicit_default_field():
    class MView(OutputView):
        flag: Annotated[bool, Spec("x"), Unit("")] = False

    class Out(BaseOutput):
        outputs: MView

        @classmethod
        def from_dir(cls, _: str):
            raise NotImplementedError

    _spec, unit = Out(raw_outputs={})._field_mapping["flag"]
    assert unit == Unit("")


# =============================================================================
# BaseOutput.get_output(to="pint")
# =============================================================================


def test_get_output_pint_numeric_with_unit_returns_quantity(raw_outputs):
    q = DummyOutput(raw_outputs).get_output("A", to="pint")
    assert q.magnitude == pytest.approx(1.0)
    assert str(q.units) == "electron_volt"


def test_get_output_pint_numeric_no_unit_returns_raw(raw_outputs):
    assert DummyOutput(raw_outputs).get_output("unmapped", to="pint") == 3


def test_get_output_pint_submapping_returns_mixed_dict(raw_outputs):
    out = DummyOutput(raw_outputs).get_output("nested", to="pint")
    assert out["d"] == 4
    assert out["c"].magnitude == pytest.approx(3)
    assert str(out["c"].units) == "electron_volt"


def test_get_output_pint_chainable(raw_outputs):
    q = DummyOutput(raw_outputs).get_output("A", to="pint")
    j = q.to("joule")
    assert j.magnitude == pytest.approx(1.0 * 1.602176634e-19)


def test_get_output_pint_ndarray_whole_array_quantity(raw_outputs):
    np = pytest.importorskip("numpy")
    q = DummyOutput(raw_outputs).get_output("forces", to="pint")
    np.testing.assert_allclose(q.magnitude, [[0.1, 0.0, 0.0], [0.0, 0.2, 0.0]])
    converted = q.to("eV/nanometer")
    np.testing.assert_allclose(converted.magnitude, [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]])


def test_get_output_dict_pint_mixed_no_raises(raw_outputs):
    out = DummyOutput(raw_outputs).get_output_dict(to="pint")

    assert out["A"].magnitude == pytest.approx(1.0)
    assert str(out["A"].units) == "electron_volt"

    assert out["unmapped"] == 3

    assert out["nested"]["d"] == 4
    assert out["nested"]["c"].magnitude == pytest.approx(3)


# =============================================================================
# OutputView (stateless typed accessor) tests
# =============================================================================


class StubOwner:
    """Minimal `BaseOutput` stand-in: holds `raw_outputs`, nothing else."""

    def __init__(self, raw_outputs):
        self.raw_outputs = raw_outputs


def test_outputview_unknown_name_raises_bare(raw_outputs):
    view = DummyView(StubOwner(raw_outputs))
    with pytest.raises(AttributeError) as exc_info:
        view.does_not_exist
    # Bare AttributeError (no "not available in parsed outputs" suffix):
    # required for `hasattr` / `getattr(..., default)` semantics.
    assert "not available in the parsed outputs" not in str(exc_info.value)


def test_outputview_subview_shares_owner(raw_outputs):
    owner = StubOwner(raw_outputs)
    view = DummyView(owner)
    assert view.nested._owner is owner


def test_outputview_dir_lists_declared_fields(raw_outputs):
    view = DummyView(StubOwner(raw_outputs))
    names = set(dir(view))
    # Leaves declared on the view:
    assert {"A", "unmapped", "not_parsed", "forces"} <= names
    # Sub-view name (set as an instance attribute in __init__):
    assert "nested" in names


def test_outputview_error_message_names_view_and_spec(raw_outputs):
    view = DummyView(StubOwner(raw_outputs))
    with pytest.raises(AttributeError) as exc_info:
        view.not_parsed
    msg = str(exc_info.value)
    assert "DummyView.not_parsed" in msg
    assert "Spec" in msg


def test_baseoutput_outputs_is_canonical_regardless_of_declaration_order(raw_outputs):
    """The `outputs` view is canonical even when other views are declared first."""

    class FirstView(OutputView):
        first: Annotated[int, Spec("a")]

    class SecondView(OutputView):
        second: Annotated[int, Spec("b.c")]

    class MultiOutput(BaseOutput):
        # `extra` declared first; `outputs` declared second.
        extra: FirstView
        outputs: SecondView

        @classmethod
        def from_dir(cls, _: str):
            pass

    out = MultiOutput(raw_outputs)
    # Both views wired as attributes:
    assert isinstance(out.outputs, SecondView)
    assert isinstance(out.extra, FirstView)
    # `_field_mapping` reflects the `outputs` view, not the first-declared one:
    assert set(out._field_mapping.keys()) == {"second"}


def test_baseoutput_missing_outputs_annotation_raises(raw_outputs):
    """Subclass without an `outputs` view annotation raises `TypeError` at init."""

    class Bare(BaseOutput):
        @classmethod
        def from_dir(cls, _: str):
            pass

    with pytest.raises(TypeError, match="must declare an `outputs:"):
        Bare(raw_outputs)
