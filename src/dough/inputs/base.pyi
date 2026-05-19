"""Type stubs for dough.inputs.base. Hides internal attributes from completion."""

import typing

from pydantic import BaseModel

class InputView:
    """Typed namespace over an owner's `_data` state."""

class BaseInput:
    """Bare-minimum input base."""

    base_model: typing.ClassVar[type[BaseModel] | None]

    def __init__(self, data: typing.Any = None) -> None: ...
    def set_input(self, path: str, value: typing.Any) -> None: ...
    def get_input(self, path: str) -> typing.Any: ...
    def set_input_dict(
        self, data: dict[str, typing.Any], base_path: str = ...
    ) -> None: ...
    def get_input_dict(
        self,
        paths: list[str] | dict[str, typing.Any] | None = ...,
        base_path: str = ...,
        skip_missing: bool = ...,
    ) -> dict[str, typing.Any]: ...
    def validate(self) -> BaseModel: ...
