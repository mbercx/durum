"""Bare-minimum BaseInput + InputView."""

import abc
import typing

from glom import Assign, PathAccessError, glom

from dough.inputs.adapter import Adapter, PathAdapter


class InputView:
    """Typed namespace over an owner's `_data` state.

    Subclasses declare annotated fields. Sub-view fields (annotation
    pointing to another `InputView` subclass) compose nested namespaces.
    Adapter-backed fields (annotation carrying an `Adapter` in its
    `Annotated` metadata) dispatch through the adapter's `from_data` /
    `to_data`. Any other annotated field falls back to a `PathAdapter`
    keyed on `_path + (name,)`.
    """

    def __init__(self, owner: "BaseInput", path: tuple[str, ...] = ()) -> None:
        sub_fields: dict[str, type[InputView]] = {}
        adapters: dict[str, Adapter] = {}

        for name, hint in typing.get_type_hints(
            type(self), include_extras=True
        ).items():
            if isinstance(hint, type) and issubclass(hint, InputView):
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

        # Bypass our custom __setattr__ which only allows declared field writes.
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_adapters", adapters)
        object.__setattr__(self, "_sub_fields", sub_fields)

        for name, sub_cls in sub_fields.items():
            object.__setattr__(self, name, sub_cls(owner, path + (name,)))

    def __getattr__(self, name: str) -> typing.Any:
        if name in self._adapters:
            return self._adapters[name].from_data(self._owner._data)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: typing.Any) -> None:
        if name in self._sub_fields:
            raise AttributeError(
                f"{type(self).__name__}.{name} is a sub-view; assign its leaf fields instead"
            )
        if name not in self._adapters:
            raise AttributeError(f"{type(self).__name__} has no field {name!r}")

        self._adapters[name].to_data(self._owner._data, value)

    def __dir__(self) -> list[str]:
        return sorted(set(object.__dir__(self)) | set(self._adapters))


class BaseInput(abc.ABC):
    """Bare-minimum input base.

    `_data` is always a `dict`. Subclasses declare one or more `InputView`
    subclasses as typed namespaces; view attribute names are the package
    author's choice.
    """

    def __init__(self, data: dict[str, typing.Any] | None = None) -> None:
        self._data = {} if data is None else data

        for name, hint in typing.get_type_hints(type(self)).items():
            if isinstance(hint, type) and issubclass(hint, InputView):
                setattr(self, name, hint(self))
            elif not hasattr(type(self), name):
                raise TypeError(
                    f"{type(self).__name__}.{name}: annotations on a `BaseInput` "
                    f"subclass must be `InputView` subclasses or have a default "
                    f"value (got {hint!r})"
                )

    def set_input(self, path: str, value: typing.Any) -> None:
        """Write `value` into `_data` at the dotted `path`.

        Creates missing intermediate dicts.
        """
        glom(self._data, Assign(path, value, missing=dict))

    def get_input(self, path: str) -> typing.Any:
        """Read the value at the dotted `path` from `_data`.

        Raises `AttributeError` if the path is not set.
        """
        try:
            return glom(self._data, path)
        except PathAccessError:
            leaf = path.rsplit(".", 1)[-1]
            raise AttributeError(f"{leaf} not set") from None
