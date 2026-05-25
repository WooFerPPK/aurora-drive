"""Wire serialization for `/ws/live` messages.

Converts in-memory `DecodedFrame` / `StateChange` / `Event` into the JSON
shapes documented in `api-contract.md` §2.

Pydantic v2 models in `interfaces/rest/schemas/live.py` are the
source-of-truth shape; this module assembles their plain-dict forms so
the WebSocket layer can `json.dumps` directly without the per-call
Pydantic instantiation cost.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fh6.application.services.event_emitter import Event
from fh6.application.services.state_emitter import StateChange
from fh6.domain.entities.frame import DecodedFrame


def _to_seconds(at: datetime) -> float:
    return at.timestamp()


def serialize_frame(frame: DecodedFrame) -> dict[str, Any]:
    raw = frame.raw
    return {
        "type": "frame",
        "t": _to_seconds(frame.received_at),
        "sessionId": str(frame.session_id) if frame.session_id is not None else "",
        "carId": str(frame.car_id),
        "isRaceOn": raw.is_race_on,
        "race": dict(raw.race),
        "engine": dict(raw.engine),
        "drivetrain": dict(raw.drivetrain),
        "motion": {
            "speed_mps": raw.motion["speed_mps"],
            "velocity": dict(raw.motion["velocity"]),
            "acceleration": dict(raw.motion["acceleration"]),
            "angularVelocity": dict(raw.motion["angularVelocity"]),
            "orientation": dict(raw.motion["orientation"]),
            "position": dict(raw.motion["position"]),
        },
        "inputs": dict(raw.inputs),
        "wheels": {k: dict(v) for k, v in raw.wheels.items()},
        "world": {
            "carOrdinal": raw.world["carOrdinal"],
            "carClass": raw.world["carClass"],
            "performanceIndex": raw.world["performanceIndex"],
            "numCylinders": raw.world["numCylinders"],
            "carGroup": raw.world["carGroup"],
            "smashableVelDiff": raw.world["smashableVelDiff"],
            "smashableMass": raw.world["smashableMass"],
        },
        "derived": {
            "balance": frame.derived.balance,
            "weightFront": frame.derived.weight_front,
            "weightLeft": frame.derived.weight_left,
            "bodyControl": frame.derived.body_control,
            "gripBudgetUsed": frame.derived.grip_budget_used,
            "powerBandOccupancy": frame.derived.power_band_occupancy,
            "throttleSmoothness": frame.derived.throttle_smoothness,
            "stopDistance_m": frame.derived.stop_distance_m,
        },
        "modeled": _modeled_block(frame),
    }


def _modeled_block(frame: DecodedFrame) -> dict[str, Any]:
    block: dict[str, Any] = {
        "tireWear": dict(frame.modeled.tire_wear),
        "tireWearConfidence": frame.modeled.tire_wear_confidence.value,
        "modeledByVersion": frame.modeled.tire_wear_confidence.model_version,
    }
    rec = frame.modeled.extras.get("shiftRecommendation")
    if rec is not None:
        block["shiftRecommendation"] = rec
    return block


def serialize_frame_batch(frames: list[DecodedFrame]) -> dict[str, Any]:
    return {"type": "frames", "batch": [serialize_frame(f) for f in frames]}


def serialize_state(change: StateChange) -> dict[str, Any]:
    return {
        "type": "state",
        "state": change.state.value,
        "at": _to_seconds(change.at),
        "lastFrameAt": (
            _to_seconds(change.last_frame_at) if change.last_frame_at is not None else None
        ),
        "reason": change.reason,
    }


def serialize_event(event: Event) -> dict[str, Any]:
    out: dict[str, Any] = {**event.payload}
    # Reserve top-level keys regardless of payload contents.
    out["type"] = "event"
    out["kind"] = event.kind
    out["at"] = _to_seconds(event.at)
    return out


def hello_message(server: str = "fh6-backend/0.1.0") -> dict[str, Any]:
    return {
        "type": "hello",
        "server": server,
        "capabilities": [
            "frames",
            "frames-batched",
            "events",
            "heartbeat",
            "rate-change",
        ],
    }


def heartbeat_message(now: datetime) -> dict[str, Any]:
    return {"type": "heartbeat", "at": _to_seconds(now)}


__all__ = [
    "heartbeat_message",
    "hello_message",
    "serialize_event",
    "serialize_frame",
    "serialize_frame_batch",
    "serialize_state",
]
