"""Tests for `Adapter` and adapter-aware routing on `InputView`."""

from typing import Annotated

import pytest

from dough.inputs import Adapter, BaseInput, InputView


class Bidir(Adapter):
    def to_input(self, inp, value):
        inp.set_input("system.nat", value["n"])
        inp.set_input("cell.vectors", value["cell"])

    def from_input(self, inp):
        return {"n": inp.get_input("system.nat"), "cell": inp.get_input("cell.vectors")}


class Innie(Adapter):
    def to_input(self, inp, value):
        inp.set_input("control.flag", value)


class Outie(Adapter):
    def from_input(self, inp):
        return inp.get_input("system.nat") * 2


class Inner(InputView):
    x: int


class View(InputView):
    structure: Annotated[dict, Bidir()]
    """Bidirectional, many-to-one adapter."""

    flag: Annotated[bool, Innie()]
    """Write-only adapter (innie)."""

    derived: Annotated[int, Outie()]
    """Read-only adapter (outie)."""

    label: str
    """Identity leaf."""

    inner: Inner
    """Sub-view."""


class Input(BaseInput):
    inputs: View


def test_bidirectional_adapter_writes_all_paths():
    inp = Input()
    inp.inputs.structure = {"n": 4, "cell": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    assert inp._data["system"]["nat"] == 4
    assert inp._data["cell"]["vectors"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def test_bidirectional_adapter_round_trip():
    inp = Input()
    inp.inputs.structure = {"n": 4, "cell": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    assert inp.inputs.structure == {
        "n": 4,
        "cell": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    }


def test_innie_only_read_raises():
    inp = Input()
    inp.inputs.flag = True
    with pytest.raises(AttributeError, match="write-only"):
        inp.inputs.flag


def test_outie_only_write_raises():
    inp = Input()
    inp._data = {"system": {"nat": 3}}
    with pytest.raises(AttributeError, match="read-only"):
        inp.inputs.derived = 5


def test_outie_only_read_works():
    inp = Input()
    inp._data = {"system": {"nat": 3}}
    assert inp.inputs.derived == 6


def test_identity_and_adapter_coexist():
    inp = Input()
    inp.inputs.structure = {"n": 2, "cell": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    inp.inputs.label = "demo"
    assert inp._data["system"]["nat"] == 2
    assert inp._data["label"] == "demo"
    assert inp.inputs.label == "demo"


def test_sub_view_assignment_still_guarded():
    inp = Input()
    with pytest.raises(AttributeError, match="is a sub-view"):
        inp.inputs.inner = {"x": 1}


def test_undeclared_adapter_field_raises():
    inp = Input()
    with pytest.raises(AttributeError, match="has no field 'bogus'"):
        inp.inputs.bogus = 1
