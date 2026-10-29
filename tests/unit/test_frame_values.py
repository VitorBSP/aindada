"""Conversões de valores de DataFrame (synthetic)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from brasileirao.frame_values import optional_int


@pytest.mark.parametrize("value", [None, pd.NA, pd.NaT, math.nan])
def test_optional_int_maps_missing_values_to_none(value: object) -> None:
    assert optional_int(value) is None


def test_optional_int_converts_numbers() -> None:
    assert optional_int(7.0) == 7
