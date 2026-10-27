"""Conversões tipadas de valores lidos de DataFrames (itertuples, groupby)."""

from __future__ import annotations

from datetime import date
from typing import SupportsInt, cast

import pandas as pd


def as_int(value: object) -> int:
    return int(cast(SupportsInt, value))


def as_timestamp(value: object) -> pd.Timestamp:
    return pd.Timestamp(cast(date | str, value))
