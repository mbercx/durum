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
    `Annotated` metadata) dispatch through the adapter's `from_input` /
    `to_input`. Any other annotated field falls back to a `PathAdapter`
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
            return self._adapters[name].from_input(self._owner)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: typing.Any) -> None:
        if name in self._sub_fields:
            raise AttributeError(
                f"{type(self).__name__}.{name} is a sub-view; assign its leaf fields instead"
            )
        if name not in self._adapters:
            raise AttributeError(f"{type(self).__name__} has no field {name!r}")

        self._adapters[name].to_input(self._owner, value)

    def __dir__(self) -> list[str]:
        return sorted(set(object.__dir__(self)) | set(self._adapters))


class BaseInput(abc.ABC):
    """Bare-minimum input base.

    `_data` is always a `dict`. Subclasses declare one or more `InputView`
    subclasses as typed namespaces; view attribute names are the package
    author's choice.

    Subclasses may attach a pydantic `BaseModel` class via the `base_model`
    class attribute. When set, `set_input` validates each leaf against the
    schema at set time, and `validate` checks the whole `_data` against
    the schema at write input time.
    """

    base_model: typing.ClassVar[typing.Any] = None

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

        Creates missing intermediate dicts. When `base_model` is set, the
        value is first validated against the schema's annotation for
        `path` and any coercion is applied before the write.
        """
        if self.base_model is not None:
            from dough.inputs.validation import validate_leaf

            value = validate_leaf(self.base_model, path, value)

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

    def set_input_dict(self, data: dict[str, typing.Any], base_path: str = "") -> None:
        """Write a nested dict into `_data`, leaf by leaf via `set_input`.

        `base_path` anchors every key in `data` under that dotted prefix,
        which lets callers write a deeper section without re-nesting the
        input dict. Keys may themselves contain dots
        (`{"some.nested.key": value}`) and are treated as paths under
        `base_path`.
        """
        for key, value in data.items():
            path = f"{base_path}.{key}" if base_path else key

            if isinstance(value, dict):
                self.set_input_dict(value, base_path=path)
            else:
                self.set_input(path, value)

    def get_input_dict(
        self,
        paths: list[str] | dict[str, typing.Any] | None = None,
        base_path: str = "",
        skip_missing: bool = False,
    ) -> dict[str, typing.Any]:
        """Build a nested dict from values at the requested paths.

        Paths can be a flat list of dotted strings (`["calc.type", "calc.spin"]`)
        or a nested dict that factors common prefixes
        (`{"calc": ["type", "spin"]}`). The two forms are equivalent.

        With `paths=None`, returns the full `_data` dict (rooted at
        `base_path` if given). The return value is the live underlying
        dict — copy with `copy.deepcopy` if isolation is needed.

        `base_path` anchors all requested paths under that dotted prefix.
        The base does not appear in the returned dict.

        When `skip_missing` is `True`, paths that are not set are omitted
        from the result instead of raising `AttributeError`.
        """
        if paths is None:
            return self.get_input(base_path) if base_path else self._data

        result: dict[str, typing.Any] = {}

        if isinstance(paths, dict):
            for key, sub in paths.items():
                sub_base = f"{base_path}.{key}" if base_path else key
                result[key] = self.get_input_dict(
                    sub, base_path=sub_base, skip_missing=skip_missing
                )
        else:
            for leaf in paths:
                if isinstance(leaf, dict):
                    result.update(
                        self.get_input_dict(
                            leaf, base_path=base_path, skip_missing=skip_missing
                        )
                    )
                    continue

                path = f"{base_path}.{leaf}" if base_path else leaf

                try:
                    value = self.get_input(path)
                except AttributeError:
                    if skip_missing:
                        continue
                    raise

                glom(result, Assign(leaf, value, missing=dict))

        return result

    def validate(self) -> typing.Any:
        """Validate the whole `_data` dict against the attached schema.

        Returns the validated pydantic model. Catches required-but-unset
        fields and cross-field rules that per-leaf validation cannot
        see.

        Raises `TypeError` when no `base_model` is attached on the
        subclass.
        """
        if self.base_model is None:
            raise TypeError(
                f"{type(self).__name__} has no `base_model` attached; "
                f"no validation is possible."
            )

        return self.base_model.model_validate(self._data)
