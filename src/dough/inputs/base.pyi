"""Type stubs for dough.inputs.base. Hides internal attributes from completion."""

import typing

class InputView:
    """Typed namespace over an owner's `_data` state."""

class BaseInput:
    """Bare-minimum input base."""

    def __init__(self, data: typing.Any = None) -> None: ...
    def set_input(self, path: str, value: typing.Any) -> None: ...
    def get_input(self, path: str) -> typing.Any: ...
