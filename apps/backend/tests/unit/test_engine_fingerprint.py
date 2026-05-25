"""Tests for EngineFingerprint and EngineClassKey value objects."""

from fh6.domain.entities.frame import FrameRaw
from fh6.domain.value_objects.engine_fingerprint import (
    EngineClassKey,
    EngineFingerprint,
)


def build_frame_raw(
    world: dict | None = None,
    drivetrain: dict | None = None,
) -> FrameRaw:
    """Helper to construct a minimal FrameRaw for testing."""
    if world is None:
        world = {}
    if drivetrain is None:
        drivetrain = {}

    return FrameRaw(
        is_race_on=True,
        timestamp_ms=0,
        engine={},
        drivetrain=drivetrain,
        motion={},
        inputs={},
        wheels={},
        world=world,
        race={},
        tail_reserved_byte=0,
    )


class TestEngineFingerprint:
    """Tests for EngineFingerprint value object."""

    def test_from_frame_raw_extracts_all_fields_when_present(self):
        """from_frame_raw extracts all three fields correctly from fully-populated FrameRaw."""
        frame = build_frame_raw(
            world={
                "carOrdinal": 42,
                "performanceIndex": 537,
                "numCylinders": 8,
            }
        )
        fp = EngineFingerprint.from_frame_raw(frame)

        assert fp.car_ordinal == 42
        assert fp.performance_index == 537
        assert fp.num_cylinders == 8

    def test_from_frame_raw_is_complete_when_all_fields_present(self):
        """from_frame_raw returns fingerprint with is_complete() True when all fields present."""
        frame = build_frame_raw(
            world={
                "carOrdinal": 1,
                "performanceIndex": 100,
                "numCylinders": 6,
            }
        )
        fp = EngineFingerprint.from_frame_raw(frame)

        assert fp.is_complete() is True

    def test_from_frame_raw_missing_performance_index_returns_none(self):
        """Missing performanceIndex -> performance_index is None and is_complete() is False."""
        frame = build_frame_raw(
            world={
                "carOrdinal": 1,
                "numCylinders": 6,
            }
        )
        fp = EngineFingerprint.from_frame_raw(frame)

        assert fp.performance_index is None
        assert fp.is_complete() is False

    def test_from_frame_raw_non_numeric_performance_index_returns_none(self):
        """Non-numeric value for performance_index (e.g. string) -> None."""
        frame = build_frame_raw(
            world={
                "carOrdinal": 1,
                "performanceIndex": "abc",
                "numCylinders": 6,
            }
        )
        fp = EngineFingerprint.from_frame_raw(frame)

        assert fp.performance_index is None

    def test_from_frame_raw_bool_not_accepted_as_int(self):
        """Boolean True for numCylinders is NOT accepted (returns None)."""
        frame = build_frame_raw(
            world={
                "carOrdinal": 1,
                "performanceIndex": 100,
                "numCylinders": True,
            }
        )
        fp = EngineFingerprint.from_frame_raw(frame)

        assert fp.num_cylinders is None


class TestEngineClassKey:
    """Tests for EngineClassKey value object."""

    def test_from_frame_raw_extracts_all_fields_when_present(self):
        """from_frame_raw extracts all four fields correctly from fully-populated FrameRaw."""
        frame = build_frame_raw(
            world={
                "carClass": "S2",
                "carGroup": 5,
                "numCylinders": 8,
            },
            drivetrain={
                "type": "AWD",
            },
        )
        key = EngineClassKey.from_frame_raw(frame)

        assert key.car_class == "S2"
        assert key.car_group == 5
        assert key.drivetrain_type == "AWD"
        assert key.num_cylinders == 8

    def test_from_frame_raw_missing_car_class_returns_none(self):
        """Missing carClass -> car_class is None."""
        frame = build_frame_raw(
            world={
                "carGroup": 5,
                "numCylinders": 8,
            },
            drivetrain={
                "type": "AWD",
            },
        )
        key = EngineClassKey.from_frame_raw(frame)

        assert key.car_class is None

    def test_from_frame_raw_empty_car_class_returns_none(self):
        """Empty string carClass -> car_class is None."""
        frame = build_frame_raw(
            world={
                "carClass": "",
                "carGroup": 5,
                "numCylinders": 8,
            },
            drivetrain={
                "type": "AWD",
            },
        )
        key = EngineClassKey.from_frame_raw(frame)

        assert key.car_class is None

    def test_from_frame_raw_empty_drivetrain_type_returns_none(self):
        """Empty drivetrain.type -> drivetrain_type is None."""
        frame = build_frame_raw(
            world={
                "carClass": "S2",
                "carGroup": 5,
                "numCylinders": 8,
            },
            drivetrain={
                "type": "",
            },
        )
        key = EngineClassKey.from_frame_raw(frame)

        assert key.drivetrain_type is None

    def test_from_frame_raw_missing_drivetrain_type_returns_none(self):
        """Missing drivetrain.type -> drivetrain_type is None."""
        frame = build_frame_raw(
            world={
                "carClass": "S2",
                "carGroup": 5,
                "numCylinders": 8,
            },
            drivetrain={},
        )
        key = EngineClassKey.from_frame_raw(frame)

        assert key.drivetrain_type is None
