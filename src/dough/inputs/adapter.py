"""Input-side adapters.

`Adapter` is the per-field two-way bridge between user values and `_data`.
`PathAdapter` shuttles a value to/from a single dotted path on `_data`.
"""

import typing

from glom import Assign, PathAccessError, glom

__all__ = ["Adapter", "PathAdapter"]


class Adapter:
    """Per-field two-way bridge between user values and `_data`.

    Subclasses override `to_data` and/or `from_data`. `from_data(data)`
    reads the user-facing value out of `data`. `to_data(data, value)`
    writes `value` into `data` (in place).

    A direction left unoverridden raises `AttributeError` when called:
    write-only fields have no `from_data`, read-only fields have no
    `to_data`.
    """

    def to_data(self, data: dict[str, typing.Any], value: typing.Any) -> None:
        raise AttributeError(f"{type(self).__name__} is read-only (no to_data)")

    def from_data(self, data: dict[str, typing.Any]) -> typing.Any:
        raise AttributeError(f"{type(self).__name__} is write-only (no from_data)")


class PathAdapter(Adapter):
    """Passthrough adapter targeting a single dotted path on `_data`.

    Reads via `glom`; writes via `glom.Assign(..., missing=dict)`.
    """

    def __init__(self, path: str):
        self.path = path

    def from_data(self, data: dict[str, typing.Any]) -> typing.Any:
        try:
            return glom(data, self.path)
        except PathAccessError:
            leaf = self.path.rsplit(".", 1)[-1]
            raise AttributeError(f"{leaf} not set") from None

    def to_data(self, data: dict[str, typing.Any], value: typing.Any) -> None:
        glom(data, Assign(self.path, value, missing=dict))
