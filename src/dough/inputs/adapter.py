"""Input-side adapters.

`Adapter` is the per-field two-way bridge between user values and `base`.
`PathAdapter` shuttles a value to/from a single dotted path on `base`.
"""

import typing

from glom import Assign, PathAccessError, glom

__all__ = ["Adapter", "PathAdapter"]


class Adapter:
    """Per-field two-way bridge between user values and `base`.

    Subclasses override `to_base` and/or `from_base`. `from_base(base)`
    reads the user-facing value out of `base`. `to_base(base, value)`
    writes `value` into `base` (in place).

    A direction left unoverridden raises `AttributeError` when called:
    write-only fields have no `from_base`, read-only fields have no
    `to_base`.
    """

    def to_base(self, base: dict[str, typing.Any], value: typing.Any) -> None:
        raise AttributeError(f"{type(self).__name__} is read-only (no to_base)")

    def from_base(self, base: dict[str, typing.Any]) -> typing.Any:
        raise AttributeError(f"{type(self).__name__} is write-only (no from_base)")


class PathAdapter(Adapter):
    """Passthrough adapter targeting a single dotted path on `base`.

    Reads via `glom`; writes via `glom.Assign(..., missing=dict)`.
    """

    def __init__(self, path: str):
        self.path = path

    def from_base(self, base: dict[str, typing.Any]) -> typing.Any:
        try:
            return glom(base, self.path)
        except PathAccessError:
            leaf = self.path.rsplit(".", 1)[-1]
            raise AttributeError(f"{leaf} not set") from None

    def to_base(self, base: dict[str, typing.Any], value: typing.Any) -> None:
        glom(base, Assign(self.path, value, missing=dict))
