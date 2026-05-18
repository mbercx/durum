import pytest

from dough.inputs import BaseInput, InputView


class Deep(InputView):
    value: int
    """Deepest leaf."""


class Mid(InputView):
    deep: Deep
    """Mid-level sub-view."""
    flag: bool
    """Mid-level leaf."""


class Top(InputView):
    mid: Mid
    """Nested sub-view."""
    name: str
    """Top-level leaf."""
    count: int
    """Top-level leaf."""


class MockInput(BaseInput):
    inputs: Top


def test_inputs_is_view_instance():
    inp = MockInput()
    assert isinstance(inp.inputs, Top)


def test_top_level_leaf_read():
    inp = MockInput()
    inp._data = {"name": "alice", "count": 3}
    assert inp.inputs.name == "alice"
    assert inp.inputs.count == 3


def test_unset_field_raises_attribute_error():
    inp = MockInput()
    with pytest.raises(AttributeError, match="name not set"):
        inp.inputs.name


def test_undeclared_name_raises_attribute_error():
    inp = MockInput()
    with pytest.raises(AttributeError):
        inp.inputs.bogus


def test_dir_exposes_fields_for_tab_completion():
    inp = MockInput()
    d = dir(inp.inputs)
    assert "name" in d
    assert "count" in d
    assert "mid" in d


def test_sub_mapping_read():
    inp = MockInput()
    inp._data = {"mid": {"flag": True}}
    assert inp.inputs.mid.flag is True


def test_sub_mapping_dir():
    inp = MockInput()
    assert "flag" in dir(inp.inputs.mid)


def test_sub_mapping_unset_raises():
    inp = MockInput()
    with pytest.raises(AttributeError, match="flag not set"):
        inp.inputs.mid.flag


def test_three_level_recursion():
    inp = MockInput()
    inp._data = {"mid": {"deep": {"value": 42}}}
    assert inp.inputs.mid.deep.value == 42
    assert "value" in dir(inp.inputs.mid.deep)


def test_top_level_leaf_write():
    inp = MockInput()
    inp.inputs.name = "alice"
    inp.inputs.count = 3
    assert inp._data == {"name": "alice", "count": 3}


def test_nested_leaf_write_creates_parent_dict():
    inp = MockInput()
    inp.inputs.mid.flag = True
    assert inp._data == {"mid": {"flag": True}}


def test_three_level_leaf_write():
    inp = MockInput()
    inp.inputs.mid.deep.value = 42
    assert inp._data == {"mid": {"deep": {"value": 42}}}


def test_write_then_read_round_trip():
    inp = MockInput()
    inp.inputs.mid.deep.value = 7
    assert inp.inputs.mid.deep.value == 7


def test_overwrite_existing_value():
    inp = MockInput()
    inp.inputs.name = "alice"
    inp.inputs.name = "bob"
    assert inp._data == {"name": "bob"}


def test_write_undeclared_raises():
    inp = MockInput()
    with pytest.raises(AttributeError, match="has no field 'bogus'"):
        inp.inputs.bogus = 1


def test_write_to_sub_mapping_raises():
    inp = MockInput()
    with pytest.raises(AttributeError, match="is a sub-view"):
        inp.inputs.mid = {"flag": True}


# --- `data` constructor behaviour -------------------------------------------


def test_data_kwarg_seeds_state():
    """Passing `data=` to the constructor uses that object as state."""
    seed = {"name": "alice", "count": 3}
    inp = MockInput(data=seed)
    assert inp._data is seed
    assert inp.inputs.name == "alice"


def test_data_kwarg_does_not_validate_type():
    """`data=` is pass-through; dough does not check it matches the annotation.

    Pathological: declare a `dict` shape but pass a list. Construction
    succeeds; reads/writes break later when glom navigates the wrong shape.
    """
    inp = MockInput(data=[1, 2, 3])
    assert inp._data == [1, 2, 3]
    with pytest.raises(Exception):
        inp.inputs.name


def test_empty_construction():
    """`BaseInput()` starts with an empty `_data` dict."""
    inp = MockInput()
    assert inp._data == {}


def test_non_view_annotation_without_default_raises():
    """Annotated non-View fields without a default are a typo / mistake."""

    class Inp(BaseInput):
        inputs: Top
        unrelated: str

    with pytest.raises(TypeError, match="must be `InputView` subclasses"):
        Inp()


def test_non_view_annotation_with_default_is_allowed():
    """Annotated non-View fields with a default are a normal class attribute."""

    class Inp(BaseInput):
        inputs: Top
        counter: int = 0

    inp = Inp()
    assert inp.counter == 0
    assert isinstance(inp.inputs, Top)


# --- `set_input` / `get_input` programmatic API -----------------------------


def test_set_input_writes_leaf():
    inp = MockInput()
    inp.set_input("name", "alice")
    assert inp._data == {"name": "alice"}


def test_set_input_creates_intermediate_dicts():
    inp = MockInput()
    inp.set_input("mid.deep.value", 42)
    assert inp._data == {"mid": {"deep": {"value": 42}}}


def test_set_input_overwrites_existing_value():
    inp = MockInput()
    inp.set_input("name", "alice")
    inp.set_input("name", "bob")
    assert inp._data == {"name": "bob"}


def test_get_input_reads_leaf():
    inp = MockInput(data={"mid": {"deep": {"value": 7}}})
    assert inp.get_input("mid.deep.value") == 7


def test_get_input_unset_raises_attribute_error():
    inp = MockInput()
    with pytest.raises(AttributeError, match="value not set"):
        inp.get_input("mid.deep.value")


def test_set_then_get_round_trip():
    inp = MockInput()
    inp.set_input("mid.flag", True)
    assert inp.get_input("mid.flag") is True
