"""Input-side adapters.

`Adapter` is the per-field two-way bridge between user values and a
`BaseInput`. `PathAdapter` shuttles a value to/from a single dotted path
on the input via `set_input` / `get_input`.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from dough.inputs.base import BaseInput

__all__ = ["Adapter", "PathAdapter"]


class Adapter:
    """Per-field two-way bridge between user values and a `BaseInput`.

    Subclasses override `to_input` and/or `from_input`. `from_input(inp)`
    reads the user-facing value out of `inp`. `to_input(inp, value)`
    writes `value` into `inp` (in place).

    A direction left unoverridden raises `AttributeError` when called:
    write-only fields have no `from_input`, read-only fields have no
    `to_input`.
    """

    def to_input(self, inp: BaseInput, value: typing.Any) -> None:
        raise AttributeError(f"{type(self).__name__} is read-only (no to_input)")

    def from_input(self, inp: BaseInput) -> typing.Any:
        raise AttributeError(f"{type(self).__name__} is write-only (no from_input)")


class PathAdapter(Adapter):
    """Passthrough adapter targeting a single dotted path on the input.

    Reads via `BaseInput.get_input`; writes via `BaseInput.set_input`.
    """

    def __init__(self, path: str):
        self.path = path

    def from_input(self, inp: BaseInput) -> typing.Any:
        return inp.get_input(self.path)

    def to_input(self, inp: BaseInput, value: typing.Any) -> None:
        inp.set_input(self.path, value)
