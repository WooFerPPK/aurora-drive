"""Static carOrdinal → human-readable name lookup.

Forza's Data Out packet only carries the integer ``carOrdinal``; there
is no car-name field. We ship two JSON ordinal tables
(community-maintained, MIT licensed) and merge them at load time with
the FH6-specific table winning over the legacy FM/FH fallback.

The lookup is a one-shot, immutable in-memory dict built at import.
It is the SEED only — once a Car row exists in the DB, its
``display_name`` is authoritative (see PATCH ``/api/cars/{ordinal}``).
"""

from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LEGACY = _HERE / "ordinals" / "car-ordinals.json"
_FH6 = _HERE / "ordinals" / "fh6-car-ordinals.json"


def _load() -> dict[int, str]:
    with _LEGACY.open(encoding="utf-8") as f:
        legacy: dict[str, str] = json.load(f)
    with _FH6.open(encoding="utf-8") as f:
        fh6: dict[str, str] = json.load(f)
    merged: dict[int, str] = {int(k): v for k, v in legacy.items()}
    merged.update({int(k): v for k, v in fh6.items()})
    return merged


_TABLE: dict[int, str] = _load()


def lookup_car_name(ordinal: int) -> str | None:
    return _TABLE.get(int(ordinal))
