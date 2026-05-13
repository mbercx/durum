"""Bare-minimum BaseInput + InputView."""

import abc
import typing

from glom import Assign, glom


class InputView:
    """Typed namespace over an owner's `base` state.

    Subclasses declare annotated fields. Reads/writes route through
    `glom` to `self._owner.base`, at this view's `_path`. Sub-view
    fields (annotation pointing to another `InputView` subclass) are
    instantiated with the appropriate path prefix.
    """

    _fields: typing.ClassVar[frozenset[str]] = frozenset()
    _sub_fields: typing.ClassVar[dict[str, type["InputView"]]] = {}

    def __init_subclass__(cls) -> None:
        hints = typing.get_type_hints(cls)
        cls._fields = frozenset(name for name in hints if not name.startswith("_"))
        cls._sub_fields = {
            name: hint
            for name, hint in hints.items()
            if isinstance(hint, type) and issubclass(hint, InputView)
        }

    def __init__(self, owner: "BaseInput", path: tuple[str, ...] = ()) -> None:
        # Bypass our custom __setattr__ which only allows declared field writes.
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_path", path)

        for name, sub_cls in self._sub_fields.items():
            object.__setattr__(self, name, sub_cls(owner, path + (name,)))

    def __getattr__(self, name: str) -> typing.Any:
        if name in self._fields:
            try:
                return glom(self._owner.base, ".".join(self._path + (name,)))
            except Exception:
                raise AttributeError(f"{type(self).__name__}.{name} not set") from None
        raise AttributeError(name)

    def __setattr__(self, name: str, value: typing.Any) -> None:
        if name in self._sub_fields:
            raise AttributeError(
                f"{type(self).__name__}.{name} is a sub-view; assign its leaf fields instead"
            )
        if name not in self._fields:
            raise AttributeError(f"{type(self).__name__} has no field {name!r}")
        glom(
            self._owner.base,
            Assign(".".join(self._path + (name,)), value, missing=dict),
        )

    def __dir__(self) -> list[str]:
        return sorted(set(object.__dir__(self)) | self._fields)


class BaseInput(abc.ABC):
    """Bare-minimum input base.

    Subclasses may declare `base` (a `dict` or `BaseModel` subclass) as
    the state; if omitted, it defaults to `dict`. They also declare one
    or more `InputView` subclasses as typed namespaces; view attribute
    names are the package author's choice.
    """

    def __init__(self, base: typing.Any = None) -> None:
        hints = typing.get_type_hints(type(self))
        base_cls = hints.get("base", dict)
        self.base = base_cls() if base is None else base

        for name, hint in hints.items():
            if isinstance(hint, type) and issubclass(hint, InputView):
                setattr(self, name, hint(self))
