"""Tests for `dough.converters.base.BaseConverter`."""

import pytest

from dough.converters.base import BaseConverter


class DummyConverter(BaseConverter):
    """Converter with a simple mapping for testing dispatch."""

    @classmethod
    def get_conversion_mapping(cls):
        return {
            "energy": (lambda x: x * 2, "raw_energy"),
            "coords": (lambda **kw: kw, {"x": "x_val", "y": "y_val"}),
            "items": (lambda a, b: (a, b), "pair"),
        }


def test_get_conversion_mapping_not_implemented():
    """Base class raises `NotImplementedError`."""
    with pytest.raises(NotImplementedError):
        BaseConverter.get_conversion_mapping()


def test_convert_scalar():
    """Scalar glom result is passed as a single positional argument."""
    result = DummyConverter.convert("energy", {"raw_energy": 5})
    assert result == 10


def test_convert_dict():
    """Dict glom result is unpacked as keyword arguments."""
    result = DummyConverter.convert("coords", {"x_val": 1, "y_val": 2})
    assert result == {"x": 1, "y": 2}


def test_convert_list():
    """List glom result is unpacked as positional arguments."""
    result = DummyConverter.convert("items", {"pair": ["a", "b"]})
    assert result == ("a", "b")
