import pytest

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


class _MockInput(BaseInput[_Top]):
    pass


def test_inputs_is_mapping_instance():
    inp = _MockInput()
    assert isinstance(inp.inputs, _Top)


def test_subclass_without_generic_raises():
    class _Bare(BaseInput):
        pass

    with pytest.raises(TypeError, match="must subclass BaseInput"):
        _Bare()


def test_top_level_leaf_read():
    inp = _MockInput()
    inp.raw_inputs = {"name": "alice", "count": 3}
    assert inp.inputs.name == "alice"
    assert inp.inputs.count == 3


def test_unset_field_raises_attribute_error():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="name not set in raw_inputs"):
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
    inp.raw_inputs = {"mid": {"flag": True}}
    assert inp.inputs.mid.flag is True


def test_sub_mapping_dir():
    inp = _MockInput()
    assert "flag" in dir(inp.inputs.mid)


def test_sub_mapping_unset_raises():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="flag not set in raw_inputs"):
        inp.inputs.mid.flag


def test_three_level_recursion():
    inp = _MockInput()
    inp.raw_inputs = {"mid": {"deep": {"value": 42}}}
    assert inp.inputs.mid.deep.value == 42
    assert "value" in dir(inp.inputs.mid.deep)


def test_top_level_leaf_write():
    inp = _MockInput()
    inp.inputs.name = "alice"
    inp.inputs.count = 3
    assert inp.raw_inputs == {"name": "alice", "count": 3}


def test_nested_leaf_write_creates_parent_dict():
    inp = _MockInput()
    inp.inputs.mid.flag = True
    assert inp.raw_inputs == {"mid": {"flag": True}}


def test_three_level_leaf_write():
    inp = _MockInput()
    inp.inputs.mid.deep.value = 42
    assert inp.raw_inputs == {"mid": {"deep": {"value": 42}}}


def test_write_then_read_round_trip():
    inp = _MockInput()
    inp.inputs.mid.deep.value = 7
    assert inp.inputs.mid.deep.value == 7


def test_overwrite_existing_value():
    inp = _MockInput()
    inp.inputs.name = "alice"
    inp.inputs.name = "bob"
    assert inp.raw_inputs == {"name": "bob"}


def test_write_undeclared_raises():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="has no field 'bogus'"):
        inp.inputs.bogus = 1


def test_write_to_sub_mapping_raises():
    inp = _MockInput()
    with pytest.raises(AttributeError, match="is a sub-mapping"):
        inp.inputs.mid = {"flag": True}
