[![Templated from python-copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mbercx/python-copier/refs/heads/main/docs/img/badge.json)](https://github.com/mbercx/python-copier)

# `dough`

*Roll your own typed wrapper.*

>[!WARNING]
> `dough` is still pre-1.0. The API is still evolving and can break in minor releases.

`dough` is a small framework for building typed Python wrappers around the output files of simulation codes.
It ships the generic machinery — file parsers, declarative output mappings, optional library converters — and stays out of the way of the code-specific details.
Code-specific wrappers live in their own packages (see [Packages built on `dough`](#packages-built-on-dough) below).

## 🌯 The current layers

- **Parsers** — turn one output file into a plain dict. One parser per file format; stateless, with a single `parse(content)` method.
- **Output mappings** — frozen dataclasses whose fields are `Annotated[T, Spec(...)]`. Each field declares the output's name, type, unit (in its docstring), and how to extract it from the parsed dicts via a [`glom`](https://glom.readthedocs.io/) `Spec`. One source of truth per quantity.
- **Converters** — optional adapters that turn base Python outputs into `ase`, `pymatgen`, or `aiida-core` objects. Heavy third-party imports stay lazy so wrapper packages don't pay for them at import time.

See the [outputs design page](https://mbercx.github.io/dough/design/outputs/) for the full picture.

## 🧪 Testing

`dough.testing` ships shared pytest fixtures (`json_serializer`, `robust_data_regression_check`) used by downstream wrapper packages for regression tests.
It's an opt-in plugin — activate it in your top-level `conftest.py` with `pytest_plugins = ["dough.testing.plugin"]`.
See the [testing design page](https://mbercx.github.io/dough/design/testing/).

## 🚀 Bootstrapping a wrapper

First create a git-tracked package directory:

```bash
mkdir my-package
cd my-package
git init
```

Or clone a fresh repo from e.g. GitHub.
Then copy the template:

```bash
copier copy --trust https://github.com/mbercx/dough .
```

This renders the typed-output scaffolding, then chains an opinionated non-interactive [`python-copier`](https://github.com/mbercx/python-copier) run for the Python project skeleton.

## 📦 Packages built on `dough`

| Package | Code | Status |
| --- | --- | --- |
| [`qe-tools`](https://github.com/aiidateam/qe-tools) | [Quantum ESPRESSO](https://www.quantum-espresso.org/) | alpha — `pw.x`, `dos.x` outputs |
| [`strudel`](https://github.com/mbercx/strudel) | [VASP](https://www.vasp.at/) | alpha — basic outputs + magnetization |

## 📚 Docs

Full documentation at [mbercx.github.io/dough](https://mbercx.github.io/dough/).

## 🤝 Contributing

It's still early days, and too soon to accept external contributions.
Feedback is most welcome though, feel free to open issue!
