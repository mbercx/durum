import pytest
from pydantic import BaseModel

from dough.inputs import BaseInput, InputMapping


class _Deep(InputMapping):
    value: int
    """Deepest leaf."""


class _Mid(InputMapping):
    deep: _Deep
    """Mid-level sub-mapping."""
    flag: bool
    """Mid-level leaf."""


class _Top(InputMapping):
    mid: _Mid
    """Nested sub-mapping."""
    name: str
    """Top-level leaf."""
    count: int
    """Top-level leaf."""


class _MockInput(BaseInput):
    inputs: _Top


def test_inputs_is_mapping_instance():
    inp = _MockInput()
    assert isinstance(inp.inputs, _Top)


def test_top_level_leaf_read():
    inp = _MockInput()
    inp.base = {"name": "alice", "count": 3}
    assert inp.inputs.name == "alice"
    assert inp.inputs.count == 3


def test_unset_field_raises_attribute_error():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="name not set"):
        inp.inputs.name


def test_undeclared_name_raises_attribute_error():
    inp = _MockInput()
    with pytest.raises(AttributeError):
        inp.inputs.bogus


def test_dir_exposes_fields_for_tab_completion():
    inp = _MockInput()
    d = dir(inp.inputs)
    assert "name" in d
    assert "count" in d
    assert "mid" in d


def test_sub_mapping_read():
    inp = _MockInput()
    inp.base = {"mid": {"flag": True}}
    assert inp.inputs.mid.flag is True


def test_sub_mapping_dir():
    inp = _MockInput()
    assert "flag" in dir(inp.inputs.mid)


def test_sub_mapping_unset_raises():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="flag not set"):
        inp.inputs.mid.flag


def test_three_level_recursion():
    inp = _MockInput()
    inp.base = {"mid": {"deep": {"value": 42}}}
    assert inp.inputs.mid.deep.value == 42
    assert "value" in dir(inp.inputs.mid.deep)


def test_top_level_leaf_write():
    inp = _MockInput()
    inp.inputs.name = "alice"
    inp.inputs.count = 3
    assert inp.base == {"name": "alice", "count": 3}


def test_nested_leaf_write_creates_parent_dict():
    inp = _MockInput()
    inp.inputs.mid.flag = True
    assert inp.base == {"mid": {"flag": True}}


def test_three_level_leaf_write():
    inp = _MockInput()
    inp.inputs.mid.deep.value = 42
    assert inp.base == {"mid": {"deep": {"value": 42}}}


def test_write_then_read_round_trip():
    inp = _MockInput()
    inp.inputs.mid.deep.value = 7
    assert inp.inputs.mid.deep.value == 7


def test_overwrite_existing_value():
    inp = _MockInput()
    inp.inputs.name = "alice"
    inp.inputs.name = "bob"
    assert inp.base == {"name": "bob"}


def test_write_undeclared_raises():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="has no field 'bogus'"):
        inp.inputs.bogus = 1


def test_write_to_sub_mapping_raises():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="is a sub-mapping"):
        inp.inputs.mid = {"flag": True}


# --- `base` constructor behaviour -------------------------------------------


def test_base_kwarg_seeds_state():
    """Passing `base=` to the constructor uses that object as state."""
    seed = {"name": "alice", "count": 3}
    inp = _MockInput(base=seed)
    assert inp.base is seed
    assert inp.inputs.name == "alice"


def test_base_kwarg_does_not_validate_type():
    """`base=` is pass-through; dough does not check it matches the annotation.

    Pathological: declare `base: dict` but pass a list. Construction
    succeeds; reads/writes break later when glom navigates the wrong shape.
    """
    inp = _MockInput(base=[1, 2, 3])
    assert inp.base == [1, 2, 3]
    with pytest.raises(Exception):
        inp.inputs.name


# --- pydantic backend -------------------------------------------------------


class _TopModel(BaseModel):
    name: str = ""
    count: int = 0


class _PydanticInput(BaseInput):
    base: _TopModel
    inputs: _Top


def test_pydantic_base_read_write_round_trip():
    """Mapping routes reads and writes through a pydantic BaseModel `base`."""
    inp = _PydanticInput()
    inp.inputs.name = "alice"
    assert inp.base.name == "alice"
    assert inp.inputs.name == "alice"


def test_explicit_dict_base_annotation_works():
    """Author can declare `base: dict` explicitly; behaviour matches default."""

    class _ExplicitDict(BaseInput):
        base: dict
        inputs: _Top

    inp = _ExplicitDict()
    inp.inputs.name = "alice"
    assert inp.base == {"name": "alice"}
