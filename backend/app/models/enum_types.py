"""Portable SQLAlchemy enum helpers.

The codebase stores enum *values* in business data (for example ``active`` and
``RSS``), while PostgreSQL native enums default to Python member names.  Use a
non-native VARCHAR enum so SQLite and PostgreSQL persist the same values.
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum as SqlEnum


def value_enum(enum_cls: type[enum.Enum]) -> SqlEnum:
    return SqlEnum(
        enum_cls,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
    )
