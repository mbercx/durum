# Inputs

!!! warning "Draft"

    This page captures the user-facing UX for input objects in the `dough` ecosystem.
    It is a strawman: the API is not yet implemented and will likely change as the design crystallises.
    Mechanics (parsers, writers, validation layer) live in a separate document.

`dough` provides a common shape for *typed input objects* across simulation codes.
Each code-specific package (`qe-tools`, `strudel`, ...) implements a concrete input class — `PwInput`, `VaspInput`, ... — that follows the same pattern.
This page describes that pattern.

## At a glance

```python
from qe_tools.inputs import PwInput

inp = PwInput()

# rich objects: assigned in whatever type the user has on hand
inp.inputs.structure = ase_atoms
inp.inputs.pseudos = {"Si": "Si.upf", "O": "O.upf"}
inp.inputs.kpoints = (8, 8, 8)

# code-native parameters: tab-completable, mirrors the file format
inp.inputs.control.calculation = "relax"
inp.inputs.system.ecutwfc = 60
inp.inputs.electrons.conv_thr = 1e-8

# bulk-set anything missing
inp.merge_inputs({
    "control": {"tprnfor": True, "tstress": True},
    "system": {"occupations": "smearing", "smearing": "mv", "degauss": 0.01},
})

# write the calculation directory
inp.to_dir("calc/")
```

## Surface

Every input class exposes a default namespace named `inputs`, plus optionally one or more *additional namespaces* (e.g. `common`, `protocols`).
Each namespace is a typed mapping with its own fields and adapters; all of them assign into the same `raw_inputs`.
The default namespace mirrors the output class layout: `out.outputs.<group>.<key>` ↔ `inp.inputs.<group>.<key>`.

```text
inp.inputs.<field>                              read / assign in the default namespace
inp.inputs.<group>.<field>                      read / assign a sub-mapping field
inp.<other_ns>.<field>                          read / assign in another namespace (e.g. inp.common.relax_type)
inp.set_input(name, value, namespace="inputs")  assign a single input (replaces) by dot-path or group
inp.merge_inputs(dict, namespace="inputs")       assign many inputs from a nested dict (additive merge)
inp.get_input(name, resolve=..., namespace="inputs")  read by dot-path or group; resolved or raw
inp.remove_input(name, namespace="inputs")      unset by dot-path
inp.to_dir(path)                                validate + write the calculation directory
PwInput.from_dir(directory)                     parse a calculation directory
PwInput.from_files(input=..., **aux)            parse explicit per-file paths
```

`namespace="inputs"` is the default; pass another namespace name to target it. Direct attribute access works on any namespace (`inp.common.relax_type = ...`).

## The `inputs` namespace

Field names are *semantic* (`structure`, `kpoints`, `pseudos`), not tied to the file format (`atomic_positions`, `cell_parameters`, `k_points`).
Nesting is limited to **two levels** (`inputs.<group>.<field>`); cards with internal structure are exposed as lists at level two, not as a third namespace.

All names are **lowercase**.
Fortran namelists are case-insensitive, but Python is not — we use lowercase throughout for ease and consistency.
Parsers normalise to lowercase; writers emit canonical-cased names that the code accepts.

The shape of the namespace — fields, sub-mappings, accepted types per field — is declared by the downstream package via an `InputsMapping` class (analogous to `OutputsMapping` on the output side).

### Reading

Attribute access returns the value the user set, or raises `AttributeError`:

```python
>>> inp.inputs.system.ecutwfc
60
>>> inp.inputs.control.restart_mode
AttributeError: 'restart_mode' is not set
```

Reading high-level fields (e.g. `inputs.structure`) returns a value re-derived from the code-native form.
Round-tripping a rich object (`atoms → inputs.structure → atoms`) may be lossy; loss-bearing conversions warn.

### Assigning

Attribute assignment converts the value via the `InputsMapping` and assigns it into `raw_inputs`.
Per-field validation runs immediately (e.g. wrong type, out-of-range scalar).
Cross-field validation is deferred to write time (see *Validation* below).

```python
inp.inputs.system.ecutwfc = 60        # ok
inp.inputs.system.ecutwfc = -5        # ValidationError: must be > 0
inp.inputs.control.calculation = 1    # ValidationError: not a valid Literal
```

High-level fields are converted to the code-native form on assignment; the original object is not retained.
Mutating an `Atoms` after assigning it has no effect on the input.

### Set vs merge

Three set semantics, mirroring standard dict behaviour:

```python
inp.set_input("system.ecutrho", 480)             # set one field
inp.set_input("system", {"ecutrho": 480})        # replace whole group (siblings cleared)
inp.merge_inputs({"system": {"ecutrho": 480}})   # bulk additive merge (siblings preserved)
```

Tab-completion (`inp.inputs.system.ecutrho = 480`) is equivalent to the dot-path `set_input`.
`merge_inputs` is the path for setting many fields at once without clobbering anything else.

### Removing

```python
inp.remove_input("system.ecutwfc")
del inp.inputs.system.ecutwfc        # also works
```

### Programmatic access — `get_input`

```python
>>> inp.get_input("control.calculation")
'relax'
>>> inp.get_input("control")
{"calculation": "relax"}                                       # only what user set
>>> inp.get_input("control", resolve=True)
{"calculation": "relax", "restart_mode": "from_scratch", ...}  # set values + code defaults
```

`get_input` accepts a dot-path (single field) or a group name (sub-mapping).
Sub-mapping results are returned as **read-only mappings**: mutation (`pop`, item assignment) raises, rather than silently no-op'ing on a copy.

## Namespaces

A namespace is a typed mapping (`InputsMapping`) attached to the input class as an attribute.
The default namespace is named `inputs` and mirrors the code's native parameter structure (e.g. for QE: namelists × keywords).
Code-package developers may add further namespaces — common-workflow vocab, opinionated protocols, alternative ergonomics — each with its own field set and adapters.

All namespaces assign into the same `raw_inputs`.
A field in one namespace may write to multiple raw fields (e.g. `common.relax_type = "cell+atoms"` sets `control.calculation` and `cell.cell_dofree`); a raw field may be touched by adapters from multiple namespaces.
Last-write-wins on raw fields — namespaces do not coordinate.

Reading a field in any namespace re-derives the value from `raw_inputs`; the same lossy-warn rule as the `structure` adapter applies.

```python
inp = PwInput()
inp.common.relax_type = "cell+atoms"   # writes raw_inputs.control.calculation, .cell.cell_dofree
inp.inputs.system.ecutwfc = 60         # writes raw_inputs.system.ecutwfc
inp.to_dir("calc/")                    # validation + write happens here
```

## State and `raw_inputs`

There is a **single source of state**: the code-native representation (`raw_inputs`), validated by a code-specific schema layer (e.g. `pydantic-espresso` for QE).
The `inputs` namespace and the `set_input` / `merge_inputs` methods are façades — they **assign** into `raw_inputs`, they do not store anything in their own format.

Concretely: every write path (`inp.inputs.x = v`, `inp.set_input(...)`, `inp.merge_inputs(...)`, `PwInput.from_dir(...)`, `PwInput.from_files(...)`) runs the user-supplied value through the `InputsMapping` and writes the result into `raw_inputs`.
Nothing is retained at the mapping level.

### Adapters vs converters

Two related but distinct concepts:

- **Converter** (outputs): *one-way*. Takes the parsed `raw_outputs` and produces a value in another library's type (e.g. `ase.Atoms`, `pymatgen.Structure`). Read-only direction.
- **Adapter** (inputs): *two-way*. Takes a value in some Python type, converts it into `raw_inputs` (assignment); and on read, derives a value back from `raw_inputs` (e.g. reconstructs an `ase.Atoms` from the cards).

High-level fields like `inputs.structure` are backed by an adapter.
The reverse direction may be lossy — adapters warn when conversion drops information.

## Validation

Two levels:

- **Per-set** (immediate): single-field constraints — type, allowed values, range — checked on assignment.
- **Write-time** (at `to_dir`): cross-field constraints — e.g. *if `lda_plus_u` then HUBBARD card required*, *if `nspin == 1` then `starting_magnetization` must not be set*.

Both are implemented by the code-specific schema layer.
Only inputs the user explicitly set are written; code-side defaults are not serialised.

## Constructors

```python
inp = PwInput()                  # empty
inp = PwInput.from_dir("calc/")            # find input files in directory
inp = PwInput.from_files(input="pw.in")    # explicit per-file paths
```

`from_dir` / `from_files` are best-effort: round-trip preserves the *calculation*, not the bytes.
Comments, whitespace, and parameter ordering are not preserved; semantic equivalence is.

Code-agnostic constructors (cf. [aiida-common-workflows](https://github.com/aiidateam/aiida-common-workflows)) are deferred to a follow-up design.

## What this is *not*

- **Not a thin wrapper around the input file format.** The semantic field names and conversions exist precisely to abstract the file format away.
- **Not a workflow engine.** Inputs describe *what* to run, not *how* to run it.
- **Not a validation library.** Validation is delegated to a code-specific schema layer.
