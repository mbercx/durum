"""Bare-minimum BaseInput + InputView."""

import abc
import typing

from dough.inputs.adapter import Adapter


class InputView:
    """Typed namespace over an owner's `base` state.

    Subclasses declare annotated fields, each carrying an `Adapter` in
    its `Annotated` metadata. Reads/writes route through the adapter's
    `from_base` / `to_base`. Sub-view fields (annotation pointing to
    another `InputView` subclass) are instantiated with the appropriate
    path prefix.
    """

    _sub_fields: typing.ClassVar[dict[str, type["InputView"]]] = {}
    _adapters: typing.ClassVar[dict[str, Adapter]] = {}

    def __init_subclass__(cls) -> None:
        hints = typing.get_type_hints(cls, include_extras=True)
        cls._sub_fields = {
            name: hint
            for name, hint in hints.items()
            if isinstance(hint, type) and issubclass(hint, InputView)
        }
        cls._adapters = {}
        for name, hint in hints.items():
            adapter = next(
                (
                    m
                    for m in getattr(hint, "__metadata__", ())
                    if isinstance(m, Adapter)
                ),
                None,
            )
            if adapter is not None:
                cls._adapters[name] = adapter

    def __init__(self, owner: "BaseInput", path: tuple[str, ...] = ()) -> None:
        # Bypass our custom __setattr__ which only allows declared field writes.
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_path", path)

        for name, sub_cls in self._sub_fields.items():
            object.__setattr__(self, name, sub_cls(owner, path + (name,)))

    def __getattr__(self, name: str) -> typing.Any:
        if name in self._adapters:
            return self._adapters[name].from_base(self._owner.base)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: typing.Any) -> None:
        if name in self._sub_fields:
            raise AttributeError(
                f"{type(self).__name__}.{name} is a sub-view; assign its leaf fields instead"
            )
        if name not in self._adapters:
            raise AttributeError(f"{type(self).__name__} has no field {name!r}")

        self._adapters[name].to_base(self._owner.base, value)

    def __dir__(self) -> list[str]:
        return sorted(set(object.__dir__(self)) | set(self._adapters))


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

        if base is not None:
            self.base = base
        elif base_cls is dict:
            self.base = {}
        else:
            # Otherwise: assume pydantic BaseModel
            self.base = base_cls.model_construct()

        for name, hint in hints.items():
            if isinstance(hint, type) and issubclass(hint, InputView):
                setattr(self, name, hint(self))
