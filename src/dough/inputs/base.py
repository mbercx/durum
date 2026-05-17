"""Bare-minimum BaseInput + InputView."""

import abc
import typing

from dough.inputs.adapter import Adapter, PathAdapter


class InputView:
    """Typed namespace over an owner's `base` state.

    Subclasses declare annotated fields. Sub-view fields (annotation
    pointing to another `InputView` subclass) compose nested namespaces.
    Adapter-backed fields (annotation carrying an `Adapter` in its
    `Annotated` metadata) dispatch through the adapter's `from_base` /
    `to_base`. Any other annotated field falls back to a `PathAdapter`
    keyed on `_path + (name,)`.
    """

    def __init__(self, owner: "BaseInput", path: tuple[str, ...] = ()) -> None:
        # Bypass our custom __setattr__ which only allows declared field writes.
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_path", path)

        sub_fields: dict[str, type[InputView]] = {}
        adapters: dict[str, Adapter] = {}

        for name, hint in typing.get_type_hints(
            type(self), include_extras=True
        ).items():
            if name.startswith("_"):
                continue
            elif isinstance(hint, type) and issubclass(hint, InputView):
                sub_fields[name] = hint
            else:
                adapter = next(
                    (
                        m
                        for m in getattr(hint, "__metadata__", ())
                        if isinstance(m, Adapter)
                    ),
                    None,
                )
                adapters[name] = adapter or PathAdapter(".".join(path + (name,)))

        object.__setattr__(self, "_adapters", adapters)
        object.__setattr__(self, "_sub_fields", sub_fields)

        for name, sub_cls in sub_fields.items():
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

    `base` is always a `dict`. Subclasses declare one or more `InputView`
    subclasses as typed namespaces; view attribute names are the package
    author's choice.
    """

    def __init__(self, base: dict[str, typing.Any] | None = None) -> None:
        self.base = {} if base is None else base

        for name, hint in typing.get_type_hints(type(self)).items():
            if isinstance(hint, type) and issubclass(hint, InputView):
                setattr(self, name, hint(self))
