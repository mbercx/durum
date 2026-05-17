import pytest
from pydantic import BaseModel

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
    inp.base = {"name": "alice", "count": 3}
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
    inp.base = {"mid": {"flag": True}}
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
    inp.base = {"mid": {"deep": {"value": 42}}}
    assert inp.inputs.mid.deep.value == 42
    assert "value" in dir(inp.inputs.mid.deep)


def test_top_level_leaf_write():
    inp = MockInput()
    inp.inputs.name = "alice"
    inp.inputs.count = 3
    assert inp.base == {"name": "alice", "count": 3}


def test_nested_leaf_write_creates_parent_dict():
    inp = MockInput()
    inp.inputs.mid.flag = True
    assert inp.base == {"mid": {"flag": True}}


def test_three_level_leaf_write():
    inp = MockInput()
    inp.inputs.mid.deep.value = 42
    assert inp.base == {"mid": {"deep": {"value": 42}}}


def test_write_then_read_round_trip():
    inp = MockInput()
    inp.inputs.mid.deep.value = 7
    assert inp.inputs.mid.deep.value == 7


def test_overwrite_existing_value():
    inp = MockInput()
    inp.inputs.name = "alice"
    inp.inputs.name = "bob"
    assert inp.base == {"name": "bob"}


def test_write_undeclared_raises():
    inp = MockInput()
    with pytest.raises(AttributeError, match="has no field 'bogus'"):
        inp.inputs.bogus = 1


def test_write_to_sub_mapping_raises():
    inp = MockInput()
    with pytest.raises(AttributeError, match="is a sub-view"):
        inp.inputs.mid = {"flag": True}


# --- `base` constructor behaviour -------------------------------------------


def test_base_kwarg_seeds_state():
    """Passing `base=` to the constructor uses that object as state."""
    seed = {"name": "alice", "count": 3}
    inp = MockInput(base=seed)
    assert inp.base is seed
    assert inp.inputs.name == "alice"


def test_base_kwarg_does_not_validate_type():
    """`base=` is pass-through; dough does not check it matches the annotation.

    Pathological: declare `base: dict` but pass a list. Construction
    succeeds; reads/writes break later when glom navigates the wrong shape.
    """
    inp = MockInput(base=[1, 2, 3])
    assert inp.base == [1, 2, 3]
    with pytest.raises(Exception):
        inp.inputs.name


# --- pydantic backend -------------------------------------------------------


class TopModel(BaseModel):
    name: str
    count: int


class PydanticInput(BaseInput):
    base: TopModel
    inputs: Top


def test_pydantic_base_read_write_round_trip():
    """Mapping routes reads and writes through a pydantic BaseModel `base`."""
    inp = PydanticInput()
    inp.inputs.name = "alice"
    assert inp.base.name == "alice"
    assert inp.inputs.name == "alice"


def test_explicit_dict_base_annotation_works():
    """Author can declare `base: dict` explicitly; behaviour matches default."""

    class ExplicitDict(BaseInput):
        base: dict
        inputs: Top

    inp = ExplicitDict()
    inp.inputs.name = "alice"
    assert inp.base == {"name": "alice"}


@pytest.mark.parametrize(
    "input_cls, expected_type",
    [
        (MockInput, dict),
        (PydanticInput, TopModel),
    ],
    ids=["dict", "pydantic"],
)
def test_empty_construction_skips_validation(input_cls, expected_type):
    """`BaseInput()` constructs an empty `base` for both backends, even when
    the pydantic schema has required fields that plain `()` would reject."""
    inp = input_cls()
    assert isinstance(inp.base, expected_type)
