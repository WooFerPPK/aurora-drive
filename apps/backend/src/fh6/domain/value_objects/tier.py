from __future__ import annotations

from enum import StrEnum


class Tier(StrEnum):
    RAW = "raw"
    DERIVED = "derived"
    MODELED = "modeled"
