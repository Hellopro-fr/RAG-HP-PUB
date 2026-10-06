from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UnitType:
    """Business category of measurement (spec §4.4, C9). Metadata only."""

    id: str
    code: str
    label: str
    description: str | None
    is_active: bool
    dimensions: tuple[str, ...] = ()
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
