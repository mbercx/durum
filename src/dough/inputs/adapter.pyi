"""Public type stubs for `dough.inputs.adapter`.

Only the supported public surface appears here. Private helpers exist on
the implementation but are deliberately omitted so type checkers flag
external use.
"""

import typing

from dough.inputs.base import BaseInput

__all__ = ["Adapter", "PathAdapter"]

class Adapter:
    def to_input(self, inp: BaseInput, value: typing.Any) -> None: ...
    def from_input(self, inp: BaseInput) -> typing.Any: ...

class PathAdapter(Adapter):
    path: str

    def __init__(self, path: str) -> None: ...
    def to_input(self, inp: BaseInput, value: typing.Any) -> None: ...
    def from_input(self, inp: BaseInput) -> typing.Any: ...
