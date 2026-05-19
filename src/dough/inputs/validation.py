"""Schema-driven validation helpers.

All pydantic-touching code lives in this module so the rest of dough
stays pydantic-free at module import time.
"""

from __future__ import annotations

import functools
import typing

from pydantic import BaseModel, TypeAdapter

__all__ = ["validate_leaf"]


def validate_leaf(
    base_model: type[BaseModel], path: str, value: typing.Any
) -> typing.Any:
    """Validate `value` against the annotation of `path` on `base_model`.

    Walks the dotted `path` through nested pydantic submodels declared
    on `base_model`, picks the leaf field's annotation, and validates
    `value` against it via `TypeAdapter`. Returns the validated (and
    possibly coerced) value.

    Raises `KeyError` if the path does not resolve to a leaf field on
    the `base_model` (missing name, or walks into a non-submodel annotation).
    Raises `pydantic.ValidationError` if `value` does not match the
    leaf annotation.
    """
    *intermediate, leaf = path.split(".")

    model: type[BaseModel] = base_model

    for name in intermediate:
        field = model.model_fields.get(name)

        if field is None:
            raise KeyError(f"{model.__name__} has no field {name!r} (in path {path!r})")

        submodel = next(
            (
                sub_annot
                for sub_annot in (field.annotation, *typing.get_args(field.annotation))
                if isinstance(sub_annot, type) and issubclass(sub_annot, BaseModel)
            ),
            None,
        )
        if submodel is None:
            raise KeyError(
                f"{model.__name__}.{name} is a leaf ({field.annotation!r}); "
                f"cannot walk into it (in path {path!r})"
            )

        model = submodel

    leaf_field = model.model_fields.get(leaf)

    if leaf_field is None:
        raise KeyError(f"{model.__name__} has no field {leaf!r} (in path {path!r})")

    annotation: typing.Any = leaf_field.annotation
    type_adapter = get_type_adapter(annotation, tuple(leaf_field.metadata))

    return type_adapter.validate_python(value)


@functools.lru_cache(maxsize=None)
def get_type_adapter(
    annotation: typing.Any, metadata: tuple[typing.Any, ...]
) -> TypeAdapter[typing.Any]:
    if metadata:
        annotation = typing.Annotated[(annotation, *metadata)]
    return TypeAdapter(annotation)
