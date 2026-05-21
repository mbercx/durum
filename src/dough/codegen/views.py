"""Generate `InputView` subclasses from a module of pydantic models.

For each `BaseModel` defined in the target module, emit an `InputView`
subclass with one field per `model_field`:

- Sub-model fields → typed sub-view (`field_name: <SubModelName>View`),
  composing nested namespaces.
- Leaf fields → bare annotations; at runtime `InputView` falls back
  to a `PathAdapter` keyed on the dotted path it sees at construction.

Each view declares its position in `_data` via a `_base_path` class
attribute, derived from a walk of the schema tree starting at the
model that nothing else references. If the root is ambiguous (zero
or multiple candidates), `_base_path` is left empty and the user's
`BaseInput` subclass picks the anchor by mount point.
"""

from __future__ import annotations

import sys
import types
import typing

from pydantic import BaseModel


def generate_views(module: types.ModuleType) -> str:
    """Render a `views.py` source string for every BaseModel in `module`."""
    candidates: list[type[BaseModel]] = []
    seen: set[int] = set()
    for value in vars(module).values():
        if (
            isinstance(value, type)
            and issubclass(value, BaseModel)
            and value is not BaseModel
            and value.__module__ == module.__name__
            and id(value) not in seen
        ):
            candidates.append(value)
            seen.add(id(value))

    # Drop any candidate that exists only as a base class for another candidate.
    # These contribute no fields of their own and would otherwise show up as
    # unreferenced root candidates that derail `_base_path` resolution.
    parents: set[type[BaseModel]] = set()
    for cls in candidates:
        for base in cls.__mro__[1:]:
            if base in candidates:
                parents.add(base)

    # Drop candidates that only appear as the element type of a container field
    # (`list[X]`, `tuple[X, ...]`, etc.) and any of their subclasses. Container
    # elements are dynamic — they have no static path to anchor a view on, so
    # they live as raw dicts in `_data`; pydantic validates them at write time.
    container_elements: set[type[BaseModel]] = set()

    for cls in candidates:
        for field in cls.model_fields.values():
            origin = typing.get_origin(field.annotation)

            if origin in (types.UnionType, typing.Union, None):
                continue

            for arg in typing.get_args(field.annotation):
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    container_elements.add(arg)

    container_subclasses: set[type[BaseModel]] = set(container_elements)

    for cls in candidates:
        if any(issubclass(cls, parent) for parent in container_elements):
            container_subclasses.add(cls)

    # Drop candidates that declare no fields of their own. An empty view has
    # nothing to read or write, and it would surface as an unreferenced root
    # candidate that derails `_base_path` resolution for everything else.
    field_less = {cls for cls in candidates if not cls.model_fields}

    models = [
        m
        for m in candidates
        if m not in parents and m not in container_subclasses and m not in field_less
    ]

    def submodel_of(annotation: typing.Any) -> type[BaseModel] | None:
        """Pick the BaseModel subclass out of an annotation (direct or in a union)."""
        for sub_annot in (annotation, *typing.get_args(annotation)):
            if isinstance(sub_annot, type) and issubclass(sub_annot, BaseModel):
                return sub_annot
        return None

    # Resolve each model's absolute dotted path. The root is the model
    # no other references via a field; if ambiguous, every model gets
    # an empty path and the user mounts views manually.
    referenced: set[type[BaseModel]] = set()
    for model in models:
        for field in model.model_fields.values():
            sub = submodel_of(field.annotation)
            if sub is not None and sub in models and sub is not model:
                referenced.add(sub)

    roots = [m for m in models if m not in referenced]
    paths: dict[type[BaseModel], str] = {m: "" for m in models}

    if len(roots) == 1:

        def walk(
            model: type[BaseModel], prefix: str, seen: set[type[BaseModel]]
        ) -> None:
            """Recurse through sub-models, assigning each its dotted path under `prefix`."""
            if model in seen:
                raise TypeError(
                    f"cyclic schema: {model.__name__} is reachable from itself"
                )

            seen = seen | {model}
            paths[model] = prefix

            for field_name, field in model.model_fields.items():
                sub = submodel_of(field.annotation)

                if sub is None or sub not in paths:
                    continue

                walk(sub, f"{prefix}.{field_name}" if prefix else field_name, seen)

        walk(roots[0], "", set())

    # Render one `class <ModelName>View(InputView)` block per model.
    # Sub-model fields become typed sub-view references; leaf fields
    # are bare annotations (resolved at runtime via PathAdapter). Field
    # descriptions become attribute docstrings on the next line, and
    # any non-builtin types encountered are collected into `user_types`
    # for the import block, grouped by source module.
    user_types: set[type] = set()
    class_blocks: list[str] = []

    def render_annotation(annotation: typing.Any) -> str:
        """Render a runtime annotation back to source, adding non-builtin types to `user_types`."""
        if annotation is type(None):
            return "None"

        if sys.version_info >= (3, 12) and isinstance(annotation, typing.TypeAliasType):
            return render_annotation(annotation.__value__)

        if isinstance(annotation, type):
            if annotation.__module__ == "builtins":
                return annotation.__name__
            # For nested classes (qualname contains a dot), import the
            # outermost enclosing class and refer to the nested one via
            # its dotted qualname.
            qualname = annotation.__qualname__

            if "." in qualname:
                outer_name = qualname.split(".", 1)[0]
                source_module = sys.modules.get(annotation.__module__)
                outer = (
                    getattr(source_module, outer_name, None) if source_module else None
                )
                if outer is not None:
                    user_types.add(outer)
                    return qualname

            user_types.add(annotation)
            return annotation.__name__

        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)

        if origin is typing.Annotated:
            return render_annotation(args[0])

        if origin is typing.Literal:
            return f"Literal[{', '.join(repr(a) for a in args)}]"

        if origin in (types.UnionType, typing.Union):
            return " | ".join(render_annotation(a) for a in args)

        if origin is not None:
            rendered_args = ", ".join(render_annotation(a) for a in args)
            origin_name = getattr(origin, "__name__", repr(origin))
            return f"{origin_name}[{rendered_args}]"

        raise TypeError(  # pragma: no cover
            f"render_annotation: unsupported annotation {annotation!r}"
        )

    for model in models:
        lines = [f"class {model.__name__}View(InputView):"]

        if paths[model]:
            lines.append(f'    _base_path = "{paths[model]}"')
            lines.append("")

        for field_name, field in model.model_fields.items():
            sub = submodel_of(field.annotation)
            if sub is not None and sub in models:
                annotation = f"{sub.__name__}View"
            else:
                annotation = render_annotation(field.annotation)
            lines.append(f"    {field_name}: {annotation}")
            if field.description is not None:
                lines.append(f'    """{field.description}"""')
            lines.append("")

        while lines and lines[-1] == "":
            lines.pop()

        class_blocks.append("\n".join(lines))

    docstring = (
        f'"""Generated by `dough generate-views` from `{module.__name__}`.\n\n'
        "Do not edit by hand — re-run the codegen instead.\n"
        '"""'
    )
    imports = [
        "from __future__ import annotations",
        "",
        "from typing import Literal",
        "",
        "from dough.inputs import InputView",
    ]

    def public_module(cls: type) -> str:
        """Walk up `cls.__module__` parents; return the shallowest that re-exports `cls`.

        Picks the public import path when a stdlib type lives in a private
        submodule that the parent module re-exports (e.g. `Path.__module__ ==
        "pathlib._local"` on Python 3.13 → `"pathlib"`).
        """
        parts = cls.__module__.split(".")
        for depth in range(1, len(parts) + 1):
            candidate = ".".join(parts[:depth])
            mod = sys.modules.get(candidate)
            if mod is not None and getattr(mod, cls.__name__, None) is cls:
                return candidate
        return cls.__module__

    by_module: dict[str, list[str]] = {}
    for cls in user_types:
        by_module.setdefault(public_module(cls), []).append(cls.__name__)
    for mod in sorted(by_module):
        names = sorted(set(by_module[mod]))
        imports.append(f"from {mod} import {', '.join(names)}")

    header = f"{docstring}\n\n" + "\n".join(imports)

    return header + "\n\n\n" + "\n\n\n".join(class_blocks) + "\n"
