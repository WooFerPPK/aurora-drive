"""Contract test for modeled.shiftRecommendation on the wire (Task 14).

The ShiftPredictor stores its decoration on `frame.modeled.extras["shiftRecommendation"]`.
The wire serializer must surface that as `modeled.shiftRecommendation` in the JSON
projection so the frontend ShiftCoach can consume it.

When the predictor has not run (or for incomplete fingerprints), `extras` will not
contain the key — the wire's `modeled` block must omit `shiftRecommendation` rather
than emit `null`, to keep the JSON small.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.ws.wire import serialize_frame


def _raw_with_motion() -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "rpm": 6500.0,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 11.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": 4, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        inputs={
            "throttle": 0.9,
            "brake": 0.0,
            "clutch": 0.0,
            "handbrake": 0.0,
            "steer": 0.0,
            "drivingLine": 0.0,
            "aiBrakeDelta": 0.0,
        },
        wheels={
            wn: {
                "slipRatio": 0.0,
                "slipAngle": 0.0,
                "combinedSlip": 0.0,
                "rotation_rad_s": 0.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.0,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.0,
            }
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={
            "carOrdinal": 2451,
            "carClass": "A",
            "performanceIndex": 812,
            "numCylinders": 6,
            "carGroup": 18,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": 1,
            "position": 1,
            "currentLapS": 12.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 30.0,
        },
        tail_reserved_byte=0,
    )


def _frame() -> DecodedFrame:
    return DecodedFrame(
        session_id=SessionId("test-session"),
        car_id=CarId("car-001"),
        received_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        raw=_raw_with_motion(),
    )


def test_shift_recommendation_surfaced_when_present() -> None:
    frame = _frame()
    frame.modeled.extras["shiftRecommendation"] = {
        "byGear": {"3": 7100, "4": 7200},
        "confidenceByGear": {"3": 0.78, "4": 0.65},
        "currentGearTarget": 7200,
        "currentGearConfidence": 0.65,
        "displayActive": True,
        "stage": "learned",
        "byGearSamples": {"3": 280, "4": 150},
        "fingerprint": {"carOrdinal": 2451, "performanceIndex": 812, "numCylinders": 6},
        "modelVersion": "shift-v1",
    }

    out = serialize_frame(frame)

    assert "shiftRecommendation" in out["modeled"]
    rec = out["modeled"]["shiftRecommendation"]
    assert rec["byGear"] == {"3": 7100, "4": 7200}
    assert rec["currentGearTarget"] == 7200
    assert rec["currentGearConfidence"] == 0.65
    assert rec["displayActive"] is True
    assert rec["stage"] == "learned"
    assert rec["modelVersion"] == "shift-v1"


def test_shift_recommendation_absent_when_extras_empty() -> None:
    frame = _frame()
    # extras is empty by default

    out = serialize_frame(frame)

    assert "shiftRecommendation" not in out["modeled"]
