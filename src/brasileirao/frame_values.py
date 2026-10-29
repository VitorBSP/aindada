"""Conversões tipadas de valores lidos de DataFrames (itertuples, groupby)."""

from __future__ import annotations

import math
from datetime import date
from typing import SupportsInt, cast

import pandas as pd


def as_int(value: object) -> int:
    return int(cast(SupportsInt, value))


def as_timestamp(value: object) -> pd.Timestamp:
    return pd.Timestamp(cast(date | str, value))


def is_missing(value: object) -> bool:
    """Ausente em DataFrame (None, NA, NaT ou NaN), sem depender da tipagem de `pd.isna`."""
    return value is None or value is pd.NA or value is pd.NaT or (isinstance(value, float) and math.isnan(value))


def optional_int(value: object) -> int | None:
    return None if is_missing(value) else as_int(value)
