"""Input-side adapters.

`Adapter` is the per-field two-way bridge between user values and `base`.
`PathAdapter` shuttles a value to/from a single dotted path, walking
pydantic submodels by type and constructing missing intermediates.
"""

import typing

from glom import Assign, PathAccessError, glom

__all__ = ["Adapter", "PathAdapter"]


class Adapter:
    """Per-field two-way bridge between user values and `base`.

    Subclasses override `to_base` and/or `from_base`. `from_base(base)`
    reads the user-facing value out of `base`. `to_base(base, value)`
    writes `value` into `base` (in place).

    A direction left unoverridden raises `AttributeError` when called:
    write-only fields have no `from_base`, read-only fields have no
    `to_base`.
    """

    def to_base(self, base: typing.Any, value: typing.Any) -> None:
        raise AttributeError(f"{type(self).__name__} is read-only (no to_base)")

    def from_base(self, base: typing.Any) -> typing.Any:
        raise AttributeError(f"{type(self).__name__} is write-only (no from_base)")


class PathAdapter(Adapter):
    """Passthrough adapter targeting a single dotted attribute path.

    Reads via `glom`. Writes walk the path with `setattr` at every level
    so each parent's `__pydantic_fields_set__` records the child as set
    (relevant for `model_dump(exclude_unset=True)`). Assumes intermediate
    pydantic submodels already exist on `base` (built eagerly by
    `BaseInput.__init__`).
    """

    def __init__(self, path: str):
        self.path = path

    def from_base(self, base: typing.Any) -> typing.Any:
        source = base if isinstance(base, dict) else base.model_dump(exclude_unset=True)
        try:
            return glom(source, self.path)
        except PathAccessError:
            leaf = self.path.rsplit(".", 1)[-1]
            raise AttributeError(f"{leaf} not set") from None

    def to_base(self, base: typing.Any, value: typing.Any) -> None:
        if isinstance(base, dict):
            glom(base, Assign(self.path, value, missing=dict))
            return

        *intermediate_names, leaf_name = self.path.split(".")

        parent = base
        for name in intermediate_names:
            child = getattr(parent, name)
            setattr(parent, name, child)
            parent = child

        setattr(parent, leaf_name, value)
