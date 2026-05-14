"""Generic file-parsing base classes."""

from __future__ import annotations

import abc
from io import TextIOBase
from pathlib import Path
from typing import Any, TextIO


class BaseOutputFileParser(abc.ABC):
    """
    Abstract class for parsing a single output file.
    A computation with multiple output files should therefore define multiple parsers.
    """

    @staticmethod
    @abc.abstractmethod
    def parse(content: str) -> dict[str, Any]:
        """Parse the file content and return a dictionary of parsed data."""

    @classmethod
    def parse_from_file(cls, file: str | Path | TextIO) -> dict[str, Any]:
        """
        Helper function to generate a BaseOutputFileParser object
        from a file instead of its string.
        """
        if isinstance(file, (str, Path)):
            with Path(file).open("r") as handle:
                content = handle.read()
        elif isinstance(file, TextIOBase):
            content = file.read()
        else:
            raise TypeError(f"Unsupported type: {type(file)}")

        return cls.parse(content)


class BaseBinaryFileParser(abc.ABC):
    """Abstract class for parsing a single binary output file.

    Counterpart to `BaseOutputFileParser` for files that are not UTF-8-decodable
    strings — netCDF, HDF5, Fortran-unformatted, etc. Subclasses do their own
    opening with the appropriate library (`netCDF4.Dataset`, `h5py.File`,
    `scipy.io.FortranFile`); `dough` adds no I/O of its own.
    """

    @staticmethod
    @abc.abstractmethod
    def parse(path: Path) -> dict[str, Any]:
        """Parse the file at `path` and return a dictionary of parsed data."""

    @classmethod
    def parse_from_file(cls, file: str | Path) -> dict[str, Any]:
        """Helper that normalises `str` to `Path` and dispatches to `parse`."""
        return cls.parse(Path(file))
