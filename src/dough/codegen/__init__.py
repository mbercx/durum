"""Codegen helpers for dough.

`generate_views(module)` walks a Python module that defines pydantic
`BaseModel` subclasses and emits one `InputView` subclass per model,
ready to be written to a sibling `views.py`.
"""

from dough.codegen.views import generate_views

__all__ = ["generate_views"]
