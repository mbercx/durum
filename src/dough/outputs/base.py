"""Abstract base class for code outputs."""

from __future__ import annotations

import abc
import contextlib
import dataclasses
import typing
from functools import cached_property
from typing import Annotated

from glom import glom, GlomError, Spec

from dough.converters.base import BaseConverter
from dough._units import Unit, get_ureg


T = typing.TypeVar("T")
TC = typing.TypeVar("TC", bound=type)


class OutputView:
    """Typed namespace over an owner's `raw_outputs` state.

    Subclasses declare annotated fields. Sub-view fields (annotation
    pointing to another `OutputView` subclass) compose nested
    namespaces. Leaf fields carry a `glom.Spec` in their `Annotated`
    metadata that resolves against `_owner.raw_outputs` on read.

    Stateless: the view holds no parsed values, only a back-reference
    to its owner. `raw_outputs` is the single source of truth.
    """

    def __init__(self, owner: "BaseOutput[typing.Any]") -> None:
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


_NOT_PARSED = object()
"""Sentinel marking a field whose `Spec` was not resolved against `raw_outputs`.

Installed by `@output_mapping` as the dataclass default for every
`Annotated[T, Spec(...)]` field that does not declare an explicit default.
`__getattribute__` raises on this sentinel; explicit defaults (e.g. `= False`)
are left untouched and reachable normally.
"""


class SubMapping:
    """Sentinel marking a field as a nested output mapping.

    `BaseOutput` resolves these at instantiation time. Nesting is intended to
    be one level only: a sub-mapping class should only contain `Spec` fields.
    """

    def __init__(self, mapping_cls: type):
        self.mapping_cls = mapping_cls


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


def output_mapping(cls: TC) -> TC:
    """Decorator that defines a typed, frozen output mapping for a code.

    Each field on the decorated class becomes one output of the corresponding
    `BaseOutput` subclass. There are two kinds of fields:

    **Parse-target fields** — a quantity extracted from `raw_outputs` via glom.
    Declared as `Annotated[T, Spec(...)]`, with a docstring stating units:

        fermi_energy: Annotated[float, Spec("xml.output.band_structure.fermi_energy")]
        \"""Fermi energy in eV.\"""

    If the `Spec` fails to resolve, accessing the field on the `outputs`
    namespace raises `AttributeError`. Attach an explicit default to return
    that value instead when parsing fails:

        job_done: Annotated[bool, Spec("stdout.job_done")] = False
        \"""Whether the job completed. Defaults to False if not parsed.\"""

    **Sub-namespace fields** — a nested group of outputs. Declared as a bare
    annotation whose type is another `@output_mapping` class:

        parameters: _ParametersMapping
        \"""Parameters the calculation ran with.\"""

    Sub-namespace classes must be defined before the parent that references
    them, and should themselves only contain parse-target fields (one level of
    nesting).

    The decorator applies `@dataclass(frozen=True)`, so parsed outputs are
    immutable. `dir()` on a mapping instance lists only the fields that
    actually resolved, for clean tab completion. `repr()` follows the same
    rule: unresolved fields are omitted, and sub-mappings that resolved no
    fields are skipped in the parent repr.
    """

    def __getattribute__(self: typing.Any, name: str) -> typing.Any:
        value = object.__getattribute__(self, name)
        if value is _NOT_PARSED or isinstance(value, SubMapping):
            raise AttributeError(f"'{name}' is not available in the parsed outputs.")
        return value

    def __dir__(self: typing.Any) -> list[str]:
        return [
            name
            for name, value in self.__dict__.items()
            if value is not _NOT_PARSED and not isinstance(value, SubMapping)
        ]

    def __repr__(self: typing.Any) -> str:
        parts = []

        for field in dataclasses.fields(self):
            try:
                # Re-use the `__getattribute__` hook: unresolved fields raise.
                value = getattr(self, field.name)
            except AttributeError:
                continue
            # Re-use the `__dir__` hook: empty sub-mapping → `dir(value) == []`.
            if getattr(type(value), "_is_output_mapping", False) and dir(value) == []:
                continue
            parts.append(f"{field.name}={repr(value)}")

        return f"{type(self).__name__}({', '.join(parts)})"

    setattr(cls, "__getattribute__", __getattribute__)
    setattr(cls, "__dir__", __dir__)
    setattr(cls, "__repr__", __repr__)

    # Inject dataclass defaults so that mapping instances can be constructed
    # without supplying every field — the `outputs` cached_property only passes
    # kwargs for fields that resolved, and the rest must come from defaults.
    #
    # Parse-target fields (`Annotated[T, Spec(...)]`) without an explicit
    # fallback get `_NOT_PARSED`, which `__getattribute__` traps to raise a
    # clear "not available" error. Fields with an explicit fallback are left
    # alone — the explicit value is returned directly when the Spec fails.
    #
    # Sub-namespace fields (bare `_OtherMapping`) get a `SubMapping(hint)`
    # placeholder; the `outputs` builder always replaces it with an
    # instantiated sub-mapping, so it never reaches user code.
    #
    # Note: `get_type_hints` evaluates annotations; modules that use
    # `from __future__ import annotations` together with `TYPE_CHECKING`-only
    # sub-mapping imports would raise `NameError` here. Sub-mapping classes
    # must be defined *before* the parent that references them.
    hints = typing.get_type_hints(cls, include_extras=True)
    for name, hint in hints.items():
        if hasattr(cls, name):  # already has a default
            continue

        spec = _spec_from_annotated(hint)

        if spec is not None:
            setattr(cls, name, _NOT_PARSED)
            continue

        if isinstance(hint, type) and getattr(hint, "_is_output_mapping", False):
            setattr(cls, name, SubMapping(hint))
            continue

        raise TypeError(
            f"{cls.__name__}.{name}: needs an `Annotated[T, Spec(...)]` annotation "
            f"(optionally with a fallback default), or a bare annotation whose type "
            f"is an @output_mapping class (which must be defined before this class)"
        )

    setattr(cls, "_is_output_mapping", True)
    return dataclasses.dataclass(frozen=True, repr=False)(cls)  # type: ignore[return-value]


class BaseOutput(abc.ABC, typing.Generic[T]):
    """Abstract base class for code outputs."""

    converters: typing.ClassVar[dict[str, type[BaseConverter]]] = {}
    """Mapping of target-library name to its `BaseConverter` subclass.

    Subclasses populate this with the converters they support, e.g.

        `converters = {"ase": ASEConverter, ...}`

    Each converter is responsible for importing optional dependencies lazily inside the
    `get_conversion_mapping()` classmethod, so simply listing it here does not pull it
    in at import time.
    """

    @classmethod
    def _get_mapping_class(cls) -> type:
        """Extract the mapping class from the generic parameter.

        Example: PwOutput(BaseOutput[_PwMapping]) → _PwMapping
        """
        for base in getattr(cls, "__orig_bases__", []):
            if typing.get_origin(base) is BaseOutput and (
                args := typing.get_args(base)
            ):
                return args[0]  # type: ignore[no-any-return]
        raise TypeError(
            f"{cls.__name__} must subclass BaseOutput[T] with a decorated output mapping, "
            "e.g. class PwOutput(BaseOutput[_PwMapping])"
        )

    def __init__(self, raw_outputs: dict[str, typing.Any]) -> None:
        self.raw_outputs = raw_outputs

        def build(mapping_cls: type) -> dict[str, typing.Any]:
            """Build the nested field mapping from a mapping class.

            Each leaf is a `(spec, unit)` tuple; sub-mappings nest as dicts.
            """

            result: dict[str, typing.Any] = {}
            hints = typing.get_type_hints(mapping_cls, include_extras=True)

            for field in dataclasses.fields(mapping_cls):
                hint = hints[field.name]
                spec = _spec_from_annotated(hint)

                if spec is not None:
                    result[field.name] = (spec, _unit_from_annotated(hint))
                elif isinstance(field.default, SubMapping):
                    result[field.name] = build(field.default.mapping_cls)
                else:
                    raise TypeError(
                        f"{mapping_cls.__name__}.{field.name}: expected an "
                        f"`Annotated[T, Spec(...)]` annotation or a `SubMapping` "
                        f"default, got {field.default!r}"
                    )

            return result

        self._field_mapping = build(self._get_mapping_class())

    @classmethod
    @abc.abstractmethod
    def from_dir(cls, directory: str) -> BaseOutput[T]:
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

    @cached_property
    def outputs(self) -> T:
        """Namespace with available outputs."""

        def build(mapping_cls: type, data: dict[str, typing.Any]) -> typing.Any:
            defaults = {f.name: f.default for f in dataclasses.fields(mapping_cls)}
            kwargs = {}

            for name, default in defaults.items():
                if isinstance(default, SubMapping):
                    kwargs[name] = build(default.mapping_cls, data.get(name, {}))
                elif name in data:
                    kwargs[name] = data[name]

            return mapping_cls(**kwargs)

        return build(self._get_mapping_class(), self.get_output_dict())  # type: ignore[no-any-return]
