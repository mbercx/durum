"""Bare-minimum BaseInput + InputMapping."""

import abc
import typing

from glom import glom

T = typing.TypeVar("T")


class InputMapping:
    """Base class for input-mapping schemas.

    Subclasses declare annotated fields; reads route to
    `self._owner.raw_inputs` at the instance's `_path` prefix.
    Sub-mapping fields (annotation pointing to another `InputMapping`
    subclass) are instantiated in `__init__` with the appropriate
    path prefix.
    """

    _fields: typing.ClassVar[frozenset[str]] = frozenset()
    _sub_fields: typing.ClassVar[dict[str, type["InputMapping"]]] = {}

    _owner: "BaseInput[typing.Any]"
    _path: tuple[str, ...]

    def __init_subclass__(cls) -> None:
        hints = typing.get_type_hints(cls)

        cls._fields = frozenset(name for name in hints if not name.startswith("_"))
        cls._sub_fields = {
            name: hint
            for name, hint in hints.items()
            if isinstance(hint, type) and issubclass(hint, InputMapping)
        }

    def __init__(
        self,
        _owner: "BaseInput[typing.Any] | None" = None,
        _path: tuple[str, ...] = (),
    ) -> None:
        self._owner = typing.cast("BaseInput[typing.Any]", _owner)
        self._path = _path

        for name, sub_cls in self._sub_fields.items():
            setattr(self, name, sub_cls(_owner=_owner, _path=_path + (name,)))

    def __getattr__(self, name: str) -> typing.Any:
        if name in self._fields:
            try:
                return glom(self._owner.raw_inputs, ".".join(self._path + (name,)))
            except Exception:
                raise AttributeError(
                    f"{type(self).__name__}.{name} not set in raw_inputs"
                ) from None

        raise AttributeError(name)

    def __dir__(self) -> list[str]:
        return sorted(set(object.__dir__(self)) | self._fields)


class BaseInput(abc.ABC, typing.Generic[T]):
    """Bare-minimum input base."""

    raw_inputs: dict[str, typing.Any]

    def __init__(self) -> None:
        mapping_cls = self._get_mapping_class()
        self.raw_inputs = {}
        self.inputs: T = mapping_cls(_owner=self)

    @classmethod
    def _get_mapping_class(cls) -> type[typing.Any]:
        for base in getattr(cls, "__orig_bases__", []):
            if typing.get_origin(base) is BaseInput and (args := typing.get_args(base)):
                return typing.cast(type[typing.Any], args[0])
        raise TypeError(f"{cls.__name__} must subclass BaseInput[T]")
