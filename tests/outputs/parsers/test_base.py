"""Unit tests for the parser ABCs in `dough.outputs.parsers.base`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dough.outputs.parsers.base import BaseBinaryFileParser


# =============================================================================
# BaseBinaryFileParser
# =============================================================================


class ByteCountParser(BaseBinaryFileParser):
    """Trivial concrete subclass: report the file's byte count.

    Exercises the ABC's contract without pulling in netCDF / HDF5 deps.
    """

    @staticmethod
    def parse(path: Path) -> dict[str, Any]:
        return {"size": path.stat().st_size}


def test_binary_parser_parse_path(tmp_path: Path) -> None:
    """`parse(path)` is invoked directly and receives a `Path`."""
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\x00\x01\x02\x03")

    assert ByteCountParser.parse(blob) == {"size": 4}


def test_binary_parser_parse_from_file_accepts_str_and_path(tmp_path: Path) -> None:
    """`parse_from_file` normalises `str` to `Path` and produces the same result."""
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"hello")

    from_str = ByteCountParser.parse_from_file(str(blob))
    from_path = ByteCountParser.parse_from_file(blob)

    assert from_str == {"size": 5}
    assert from_str == from_path
