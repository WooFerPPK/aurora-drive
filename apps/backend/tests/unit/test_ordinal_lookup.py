"""Static carOrdinal → name table.

Forza only emits the integer ordinal, never the car's human name; we
recover the name via the bundled community table (legacy FM/FH +
FH6-specific overlay). Merge precedence: FH6 file wins on conflict.
Tests pin that:

- a known ordinal resolves to the table's name (verifies the JSON
  files were copied and the merge ran);
- the FH6 file overrides the legacy file for any shared key;
- unknown ordinals return None, leaving the caller to fall back to
  the `Car #{ordinal}` placeholder.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fh6.application.services.session_manager import build_car_from_raw
from fh6.domain.entities.frame import FrameRaw
from fh6.infrastructure.cars import ordinal_lookup

_HERE = Path(ordinal_lookup.__file__).resolve().parent
_FH6_JSON = json.loads((_HERE / "ordinals" / "fh6-car-ordinals.json").read_text())
_LEGACY_JSON = json.loads((_HERE / "ordinals" / "car-ordinals.json").read_text())


def test_known_fh6_ordinal_resolves_from_table() -> None:
    # Pick the first entry from the FH6 file and verify it round-trips.
    sample_key = next(iter(_FH6_JSON))
    assert ordinal_lookup.lookup_car_name(int(sample_key)) == _FH6_JSON[sample_key]


def test_known_legacy_only_ordinal_resolves() -> None:
    # Pick an ordinal that only exists in the legacy file.
    legacy_only = next(k for k in _LEGACY_JSON if k not in _FH6_JSON)
    assert ordinal_lookup.lookup_car_name(int(legacy_only)) == _LEGACY_JSON[legacy_only]


def test_fh6_wins_over_legacy_on_shared_ordinal() -> None:
    shared = next((k for k in _FH6_JSON if k in _LEGACY_JSON), None)
    if shared is None:
        # Nothing shared in the bundled tables today → contract is
        # vacuously satisfied. Skip rather than assert a false negative.
        return
    assert ordinal_lookup.lookup_car_name(int(shared)) == _FH6_JSON[shared]


def test_unknown_ordinal_returns_none() -> None:
    # Pick an ordinal guaranteed not to exist (negative).
    assert ordinal_lookup.lookup_car_name(-1) is None
    assert ordinal_lookup.lookup_car_name(0) is None


def _make_raw(ordinal: int) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=0,
        engine={},
        drivetrain={"type": "AWD"},
        motion={},
        inputs={},
        wheels={},
        world={
            "carOrdinal": ordinal,
            "performanceIndex": 800,
            "carClass": "A",
            "carGroup": 0,
        },
        race={},
        tail_reserved_byte=0,
    )


def test_build_car_from_raw_uses_table_name_for_known_ordinal() -> None:
    sample_key = next(iter(_FH6_JSON))
    ordinal = int(sample_key)
    car = build_car_from_raw(_make_raw(ordinal), datetime(2026, 5, 18, tzinfo=UTC))
    assert car.display_name == _FH6_JSON[sample_key]
    # short_name strips the leading year ("2005 Ferrari FXX" → "Ferrari FXX").
    assert car.display_name.split(" ", 1)[-1] == car.short_name


def test_build_car_from_raw_falls_back_to_placeholder_for_unknown() -> None:
    car = build_car_from_raw(_make_raw(-999), datetime(2026, 5, 18, tzinfo=UTC))
    assert car.display_name == "Car #-999"
    assert car.short_name == "#-999"
