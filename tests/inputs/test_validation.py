"""Tests for the schema-driven leaf validator."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, ValidationError

from dough.inputs.validation import validate_leaf


class Basis(BaseModel):
    ecut: float = Field(gt=0)


class Calculation(BaseModel):
    type: str
    spin: str = "none"


class InputModel(BaseModel):
    calculation: Calculation
    basis: Basis
    optional_section: Basis | None = None


def test_validates_top_level_leaf():
    assert validate_leaf(InputModel, "calculation.type", "relax") == "relax"


def test_coerces_via_type_adapter():
    assert validate_leaf(InputModel, "basis.ecut", "3.5") == 3.5


def test_rejects_wrong_type():
    with pytest.raises(ValidationError):
        validate_leaf(InputModel, "calculation.type", 42)


def test_rejects_field_constraint_violation():
    with pytest.raises(ValidationError):
        validate_leaf(InputModel, "basis.ecut", -1.0)


def test_walks_through_optional_union():
    # `Basis | None` -> walker picks the `Basis` branch and descends.
    assert validate_leaf(InputModel, "optional_section.ecut", 30.0) == 30.0


def test_missing_intermediate_field_raises_keyerror():
    with pytest.raises(KeyError, match="bogus"):
        validate_leaf(InputModel, "bogus.x", 1)


def test_missing_leaf_field_raises_keyerror():
    with pytest.raises(KeyError, match="bogus"):
        validate_leaf(InputModel, "calculation.bogus", 1)


def test_walking_into_leaf_raises_keyerror():
    with pytest.raises(KeyError, match="leaf"):
        validate_leaf(InputModel, "basis.ecut.subfield", 1)
