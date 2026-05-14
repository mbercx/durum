"""Tests for `dough.outputs.parsers.base.BaseOutputFileParser`."""

from io import StringIO

import pytest

from dough.outputs.parsers.base import BaseOutputFileParser


class DummyParser(BaseOutputFileParser):
    @staticmethod
    def parse(content: str) -> dict:
        return {"length": len(content)}


def test_parse_from_file_with_path(tmp_path):
    """Accepts a `str` or `Path` file path."""
    f = tmp_path / "out.txt"
    f.write_text("hello")
    assert DummyParser.parse_from_file(str(f)) == {"length": 5}
    assert DummyParser.parse_from_file(f) == {"length": 5}


def test_parse_from_file_with_text_stream():
    """Accepts a `TextIOBase` stream."""
    stream = StringIO("abc")
    assert DummyParser.parse_from_file(stream) == {"length": 3}


def test_parse_from_file_rejects_unsupported_type():
    """Raises `TypeError` for non-path, non-stream input."""
    with pytest.raises(TypeError, match="Unsupported type"):
        DummyParser.parse_from_file(42)  # type: ignore[arg-type]
