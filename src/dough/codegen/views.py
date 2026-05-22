"""Generate `InputView` subclasses from a pydantic root model.

Walks `root.model_fields` recursively. For every `(model, dotted_path)`
pair reached, emit an `InputView` subclass with one field per
`model_field`:

- Sub-model fields → typed sub-view (`field_name: <SubViewName>`),
  composing nested namespaces.
- Leaf fields → bare annotations; at runtime `InputView` falls back
  to a `PathAdapter` keyed on the dotted path it sees at construction.

Each view declares its position in `_data` via a `_base_path` class
attribute set to its dotted path under the root.

View names default to a PascalCase of the path
(`KPointsView` for path `"k_points"`). When a single name collides
across the emitted set — e.g. each member of a discriminated union
at the same mount — the colliding entries fall back to including
the class name, with any common prefix between the path-pascal and
the class name collapsed so the result reads as
`KPointsListCardView` rather than `KPointsKPointsListCardView`.
"""

from __future__ import annotations

import sys
import types
import typing
from collections import defaultdict

from pydantic import BaseModel


def generate_views(root: type[BaseModel]) -> str:
    """Render a `views.py` source string for every BaseModel reachable from `root`."""

    def submodels_of(annotation: typing.Any) -> list[type[BaseModel]]:
        """All BaseModel subclasses reachable through a direct or union annotation.

        Returns every submodel when the field's value *is* one of them
        (direct, or any union member). Container annotations like
        `list[Foo]` are handled separately and return an empty list here.
        """
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]

        origin = typing.get_origin(annotation)
        if origin in (types.UnionType, typing.Union):
            return [
                arg
                for arg in typing.get_args(annotation)
                if isinstance(arg, type) and issubclass(arg, BaseModel)
            ]

        return []

    # 1. Walk the schema tree from the root, returning one (model, path) pair
    #    per node reached. Pairs are emitted in walk order so the rendered
    #    file follows schema declaration order from the user's perspective.
    def walk(
        model: type[BaseModel], path: str, seen: set[type[BaseModel]]
    ) -> list[tuple[type[BaseModel], str]]:
        if model in seen:
            raise TypeError(
                f"cyclic schemas are not supported: {model.__name__} is "
                "reachable from itself. `_base_path` is a static dotted "
                "string, so a model with infinite reachable paths cannot "
                "anchor a view."
            )

        seen = seen | {model}
        pairs: list[tuple[type[BaseModel], str]] = [(model, path)]

        for field_name, field in model.model_fields.items():
            sub_path = f"{path}.{field_name}" if path else field_name
            for sub in submodels_of(field.annotation):
                pairs.extend(walk(sub, sub_path, seen))

        return pairs

    pairs = walk(root, "", set())

    # 2. Derive a view name per (model, path) pair. Default is a PascalCase
    #    of the path. Names that collide across pairs fall back to including
    #    the class name, with the longest common prefix between path-pascal
    #    and class name stripped so common cases stay readable.
    def pascal_segment(segment: str) -> str:
        """Convert a single `snake_case` segment to `PascalCase`."""
        return "".join(p.capitalize() for p in segment.split("_") if p)

    def pascal_path(path: str) -> str:
        return "".join(pascal_segment(seg) for seg in path.split("."))

    def collision_name(path_pascal: str, class_name: str) -> str:
        """`<PathPascal><ClassName>View` with the longest shared prefix collapsed."""
        for k in range(len(class_name), 0, -1):
            if path_pascal.endswith(class_name[:k]):
                return f"{path_pascal}{class_name[k:]}View"

        return f"{path_pascal}{class_name}View"

    default_names = {
        (model, path): f"{pascal_path(path)}View" for model, path in pairs if path
    }
    pairs_by_name: dict[str, list[tuple[type[BaseModel], str]]] = defaultdict(list)

    for pair, name in default_names.items():
        pairs_by_name[name].append(pair)

    view_names: dict[tuple[type[BaseModel], str], str] = {
        (root, ""): f"{root.__name__}View"
    }
    for name, occupants in pairs_by_name.items():
        if len(occupants) == 1:
            view_names[occupants[0]] = name
        else:
            for model, path in occupants:
                view_names[(model, path)] = collision_name(
                    pascal_path(path) if path else "", model.__name__
                )

    # 3. Render one `class <Name>View(InputView):` block per emitted pair.
    #    Sub-model fields become typed sub-view references resolved by
    #    (sub_model, sub_path); leaf fields are bare annotations.
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

    for model, path in pairs:
        name = view_names[(model, path)]
        lines = [f"class {name}(InputView):"]

        if model is not root:
            lines.append(f'    _base_path = "{path}"')
            lines.append("")

        for field_name, field in model.model_fields.items():
            sub_path = f"{path}.{field_name}" if path else field_name
            sub_models = submodels_of(field.annotation)

            if len(sub_models) == 1:
                annotation = view_names[(sub_models[0], sub_path)]

            elif len(sub_models) > 1:
                annotation = " | ".join(view_names[(s, sub_path)] for s in sub_models)
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
        f'"""Generated by `dough generate-views` from `{root.__module__}.{root.__name__}`.\n\n'
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
