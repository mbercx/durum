"""Abstract base class for code outputs."""

from __future__ import annotations

import abc
import contextlib
import typing
from typing import Annotated

from glom import glom, GlomError, Spec

from dough.converters.base import BaseConverter
from dough._units import Unit, get_ureg


class OutputView:
    """Typed namespace over an owner's `raw_outputs` state.

    Subclasses declare annotated fields. Sub-view fields (annotation
    pointing to another `OutputView` subclass) compose nested
    namespaces. Leaf fields carry a `glom.Spec` in their `Annotated`
    metadata that resolves against `_owner.raw_outputs` on read.

    Stateless: the view holds no parsed values, only a back-reference
    to its owner. `raw_outputs` is the single source of truth.
    """

    def __init__(self, owner: "BaseOutput") -> None:
        sub_fields: dict[str, type[OutputView]] = {}
        leaves: dict[str, typing.Any] = {}

        for name, hint in typing.get_type_hints(
            type(self), include_extras=True
        ).items():
            if isinstance(hint, type) and issubclass(hint, OutputView):
                sub_fields[name] = hint
            else:
                leaves[name] = hint

        self._owner = owner
        self._sub_fields = sub_fields
        self._leaves = leaves

        for name, sub_cls in sub_fields.items():
            setattr(self, name, sub_cls(owner))

    def __getattr__(self, name: str) -> typing.Any:
        if name not in self._leaves:
            raise AttributeError(name)

        spec = _spec_from_annotated(self._leaves[name])

        try:
            return glom(self._owner.raw_outputs, spec)
        except GlomError:
            raise AttributeError(
                f"'{name}' is not available in the parsed outputs "
                f"({type(self).__name__}.{name} via Spec {spec!r})."
            ) from None

    def __dir__(self) -> list[str]:
        return sorted(set(object.__dir__(self)) | set(self._leaves))


def _spec_from_annotated(hint: typing.Any) -> Spec | None:
    """Return the `Spec` embedded in an `Annotated[...]` type hint, or `None`.

    Raises `TypeError` if multiple `Spec` entries are present.
    """
    if typing.get_origin(hint) is not Annotated:
        return None
    specs = [arg for arg in typing.get_args(hint)[1:] if isinstance(arg, Spec)]
    if not specs:
        return None
    if len(specs) > 1:
        raise TypeError(f"Annotated type has multiple Spec entries: {hint!r}")
    return specs[0]


def _unit_from_annotated(hint: typing.Any) -> Unit | None:
    """Return the first `Unit` embedded in an `Annotated[...]` hint, or `None`.

    Multiple `Unit` entries are not rejected at runtime — `dough` relies on an
    out-of-band lint to catch that labeling bug, and skips the runtime check on
    every decoration.
    """
    if typing.get_origin(hint) is not Annotated:
        return None

    for arg in typing.get_args(hint)[1:]:
        if isinstance(arg, Unit):
            return arg

    return None


def _build_field_mapping(view: OutputView) -> dict[str, typing.Any]:
    """Walk a view (and its sub-views) into a nested `(spec, unit)` dict.

    Each leaf becomes a `(spec, unit)` 2-tuple; each sub-view becomes a nested
    dict of the same shape. Matches the structure that `BaseOutput.get_output`
    and `BaseOutput.list_outputs` consume.
    """
    result: dict[str, typing.Any] = {}
    for name, hint in view._leaves.items():
        spec = _spec_from_annotated(hint)
        unit = _unit_from_annotated(hint)
        result[name] = (spec, unit)
    for name, sub_view in ((n, getattr(view, n)) for n in view._sub_fields):
        result[name] = _build_field_mapping(sub_view)
    return result


class BaseOutput(abc.ABC):
    """Abstract base class for code outputs."""

    converters: typing.ClassVar[dict[str, type[BaseConverter]]] = {}
    """Mapping of target-library name to its `BaseConverter` subclass.

    Subclasses populate this with the converters they support, e.g.

        `converters = {"ase": ASEConverter, ...}`

    Each converter is responsible for importing optional dependencies lazily inside the
    `get_conversion_mapping()` classmethod, so simply listing it here does not pull it
    in at import time.
    """

    def __init__(self, raw_outputs: dict[str, typing.Any]) -> None:
        self.raw_outputs = raw_outputs

        for name, hint in typing.get_type_hints(type(self)).items():
            if isinstance(hint, type) and issubclass(hint, OutputView):
                setattr(self, name, hint(self))

        if not hasattr(self, "outputs"):
            raise TypeError(
                f"{type(self).__name__} must declare an `outputs: <OutputView subclass>` annotation."
            )

        self._field_mapping: dict[str, typing.Any] = _build_field_mapping(self.outputs)

    @classmethod
    @abc.abstractmethod
    def from_dir(cls, directory: str) -> BaseOutput:
        pass  # pragma: no cover

    def get_output_from_spec(self, spec: typing.Any) -> typing.Any:
        """Return a value from `raw_outputs` using a glom specification.

        Args:
            spec: A glom specification describing the path/transforms to apply.

        Raises:
            GlomError: If the specification is invalid or the path cannot be resolved.
        """
        return glom(self.raw_outputs, spec)

    def get_output(self, name: str, to: str | None = None) -> typing.Any:
        """Return an output by `name`.

        Args:
            name (str): Output to retrieve (e.g., "structure", "fermi_energy",
                "forces").
            to (str): Optional target library to convert the base output to. `"pint"`
                returns a `pint.Quantity` for unit-marked outputs.

                Other supported values are the keys of this subclass's `converters`
                class variable — list them with

                    `sorted(OutputClass.converters)`

                Passing an unsupported value raises `ValueError` listing the
                available options.

        Examples:
            >>> pw_out.get_output("structure")
            >>> pw_out.get_output("structure", to="pymatgen")
            >>> pw_out.get_output("total_energy", to="pint").to("Ha")
        """
        entry = self._field_mapping[name]

        if to is not None and to != "pint" and to not in self.converters:
            available = sorted(self.converters)
            raise ValueError(f"Library '{to}' is not supported. Available: {available}")

        def convert_to(
            qname: str, leaf: tuple[Spec, Unit | None], to: str | None
        ) -> typing.Any:
            spec, unit = leaf
            value = glom(self.raw_outputs, spec)

            if to == "pint" and unit is not None:
                value = get_ureg().Quantity(value, unit.value)

            if to is None or to == "pint":
                return value

            Converter = self.converters[to]

            if qname in Converter.get_conversion_mapping():
                return Converter().convert(qname, value)

            return value

        if isinstance(entry, dict):
            result: dict[str, typing.Any] = {}
            for sub_name, leaf in entry.items():
                with contextlib.suppress(GlomError):
                    result[sub_name] = convert_to(f"{name}.{sub_name}", leaf, to)
            return result

        return convert_to(name, entry, to)

    def get_output_dict(
        self,
        names: None | list[str] = None,
        to: str | None = None,
    ) -> dict[str, typing.Any]:
        """Return a dictionary of outputs.

        Args:
            names (list[str]): Output names to include. Defaults to all
                available outputs.
            to (str): Optional target library to convert the base output to. `"pint"`
                returns a `pint.Quantity` for unit-marked outputs.

                Other supported values are the keys of this subclass's `converters`
                class variable — list them with

                    `sorted(OutputClass.converters)`

                Passing an unsupported value raises `ValueError` listing the
                available options.

        Returns:
            dict: Mapping from output name to value.
        """
        names = names or self.list_outputs()
        return {name: self.get_output(name, to=to) for name in names}

    def list_outputs(self, only_available: bool = True) -> list[str]:
        """List the output names.

        Args:
            only_available (bool, default True): Include only outputs that are
                available, i.e. produced by the calculation and successfully parsed. If
                False, list all outputs that this parser supports.

        Returns:
            list[str]: A list of output names.
        """
        if not only_available:
            return list(self._field_mapping.keys())

        output_names = []

        for name in self._field_mapping.keys():
            try:
                self.get_output(name)
            except GlomError:
                continue
            else:
                output_names.append(name)

        return output_names
