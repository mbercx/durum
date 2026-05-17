"""Bare-minimum BaseInput + InputView."""

import abc
import typing

from glom import Assign, glom


class Adapter:
    """Per-field two-way transform between user values and `base` paths.

    Subclasses override `to_base` and/or `from_base`. `to_base(value)`
    returns a sparse `{absolute_path: value}` map; dough writes each
    entry via `glom.Assign`. `from_base(base)` receives the full `base`
    and returns the user-facing value.

    A direction left unoverridden raises `AttributeError` when accessed:
    write-only fields have no `from_base`, read-only fields have no
    `to_base`.
    """

    def to_base(self, value: typing.Any) -> dict[str, typing.Any]:
        raise AttributeError(f"{type(self).__name__} is read-only (no to_base)")

    def from_base(self, base: typing.Any) -> typing.Any:
        raise AttributeError(f"{type(self).__name__} is write-only (no from_base)")


class InputView:
    """Typed namespace over an owner's `base` state.

    Subclasses declare annotated fields. Reads/writes route through
    `glom` to `self._owner.base`, at this view's `_path`. Sub-view
    fields (annotation pointing to another `InputView` subclass) are
    instantiated with the appropriate path prefix. Adapter-backed
    fields (annotation carrying an `Adapter` in its `Annotated`
    metadata) dispatch through the adapter's `to_base` / `from_base`.
    """

    _fields: typing.ClassVar[frozenset[str]] = frozenset()
    _sub_fields: typing.ClassVar[dict[str, type["InputView"]]] = {}
    _adapters: typing.ClassVar[dict[str, Adapter]] = {}

    def __init_subclass__(cls) -> None:
        hints = typing.get_type_hints(cls, include_extras=True)
        cls._fields = frozenset(name for name in hints if not name.startswith("_"))
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

        if name in self._adapters:
            for path, val in self._adapters[name].to_base(value).items():
                glom(self._owner.base, Assign(path, val, missing=dict))
            return

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
