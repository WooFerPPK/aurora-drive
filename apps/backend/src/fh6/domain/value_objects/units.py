from __future__ import annotations

THROTTLE_U8_SCALE = 1.0 / 255.0
STEER_S8_SCALE = 1.0 / 127.0


def u8_to_norm(v: int) -> float:
    return max(0.0, min(1.0, v * THROTTLE_U8_SCALE))


def s8_to_norm(v: int) -> float:
    return max(-1.0, min(1.0, v * STEER_S8_SCALE))


def zero_lap_to_none(v: float) -> float | None:
    # Per API spec §12 item 9: 0.0 in lap-time fields means "not applicable".
    # LapNumber=0 is a legitimate integer value (item 10) and is handled separately.
    return None if v == 0.0 else v
