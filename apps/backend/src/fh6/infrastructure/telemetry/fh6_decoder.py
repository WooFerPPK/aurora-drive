"""FH6 Data Out packet decoder.

The byte layout is sourced from `forza-horizon-telemetry-research.md`
(consolidated telemetry property reference). Documented fields run
0..322 (inclusive); byte 323 is preserved as `tail_reserved_byte`
per FR-002 and API spec §12 item 1.

Little-endian assumption (FR-003, API spec §12 item 2) is isolated
in `_STRUCT_FORMAT` here. To flip endianness later, change only the
leading byte-order character.
"""

from __future__ import annotations

import struct
from typing import Any

from fh6.domain.entities.frame import FrameRaw
from fh6.domain.ports.packet_decoder import MalformedPacket, PacketDecoder
from fh6.domain.value_objects.units import s8_to_norm, u8_to_norm, zero_lap_to_none
from fh6.infrastructure.telemetry.normalizer import tire_temp_norm_window

# Drivetrain enum: 0=FWD, 1=RWD, 2=AWD (research doc).
_DRIVETRAIN: dict[int, str] = {0: "FWD", 1: "RWD", 2: "AWD"}

# CarClass enum: 0..7 inclusive → D, C, B, A, S, R, P, X (official FH6 dev
# docs: "Between 0 (D -- worst cars) and 7 (X class -- best cars) inclusive").
_CAR_CLASS: dict[int, str] = {
    0: "D",
    1: "C",
    2: "B",
    3: "A",
    4: "S",
    5: "R",
    6: "P",
    7: "X",
}

# Struct format string. Total = 324 bytes. Built as an explicit string
# so the parser sees a single literal: 78 four-byte fields (offsets
# 0..311), then U16 LapNumber, 6 U8 fields, 3 S8 fields, 1 U8 reserved.
# Layout sourced from forza-horizon-telemetry-research.md.
_STRUCT_FORMAT = (
    # byte order: little-endian (FR-003, API spec sec.12 item 2).
    "<"
    # 0..16: IsRaceOn, TimestampMS, EngineMaxRpm, EngineIdleRpm, CurrentEngineRpm
    "iIfff"
    # 20..52: AccelXYZ, VelXYZ, AngVelXYZ (9 floats)
    "fffffffff"
    # 56..64: Yaw, Pitch, Roll
    "fff"
    # 68..80: NormalizedSuspensionTravel FL/FR/RL/RR
    "ffff"
    # 84..96: TireSlipRatio FL/FR/RL/RR
    "ffff"
    # 100..112: WheelRotationSpeed FL/FR/RL/RR
    "ffff"
    # 116..128: WheelOnRumbleStrip FL/FR/RL/RR (S32 booleans)
    "iiii"
    # 132..144: WheelInPuddle FL/FR/RL/RR (S32 booleans -- FR-023)
    "iiii"
    # 148..160: SurfaceRumble FL/FR/RL/RR
    "ffff"
    # 164..176: TireSlipAngle FL/FR/RL/RR
    "ffff"
    # 180..192: TireCombinedSlip FL/FR/RL/RR
    "ffff"
    # 196..208: SuspensionTravelMeters FL/FR/RL/RR
    "ffff"
    # 212..240: CarOrdinal, CarClass, CarPI, Drivetrain, NumCylinders (5 S32),
    # CarGroup (U32), SmashableVelDiff, SmashableMass (2 F32)
    "iiiiiIff"
    # 244..280: PositionXYZ, Speed, Power, Torque, TireTemp FL/FR/RL/RR
    "ffffffffff"
    # 284..308: Boost, Fuel, DistanceTraveled, BestLap, LastLap,
    # CurrentLap, CurrentRaceTime
    "fffffff"
    # 312: LapNumber (U16)
    "H"
    # 314..319: RacePosition, Accel, Brake, Clutch, HandBrake, Gear (6 U8)
    "BBBBBB"
    # 320..322: Steer, NormalizedDrivingLine, NormalizedAIBrakeDifference (3 S8)
    "bbb"
    # 323: tail_reserved_byte (1 U8)
    "B"
)

_STRUCT = struct.Struct(_STRUCT_FORMAT)
_EXPECTED_SIZE = 324
assert _STRUCT.size == _EXPECTED_SIZE, (
    f"struct format size {_STRUCT.size} != expected {_EXPECTED_SIZE}"
)

# Optional Motorsport-style trailing tire-wear block (4 × f32 = 16 bytes at
# offsets 324..339). FH6 officially omits this — see
# forza-horizon-telemetry-research.md §7 — but Motorsport packets reaching
# us by mistake (or a future FH6 patch) should be handled defensively.
_TIRE_WEAR_STRUCT = struct.Struct("<ffff")
_TIRE_WEAR_SIZE = _EXPECTED_SIZE + _TIRE_WEAR_STRUCT.size  # 340

# Fixed optimal-window for tire-temp normalization. FH6 ships only raw
# Celsius; the normalized value lives in [0, 1] with 0 = cold, 1 = over-
# temp, ~0.5 = inside the ideal band. Window matches api-contract.md §3
# example (raw 84.4°C → 0.32). A future per-car / per-compound override
# would replace these constants.
_TIRE_TEMP_OPTIMAL_LOW_C = 70.0
_TIRE_TEMP_OPTIMAL_HIGH_C = 115.0


class FH6PacketDecoder(PacketDecoder):
    expected_packet_size: int = _EXPECTED_SIZE

    def decode(self, payload: bytes) -> FrameRaw:
        if len(payload) < _EXPECTED_SIZE:
            raise MalformedPacket(f"expected >= {_EXPECTED_SIZE} bytes, got {len(payload)}")
        try:
            v = _STRUCT.unpack_from(payload, 0)
        except struct.error as exc:  # pragma: no cover
            raise MalformedPacket(str(exc)) from exc

        # v indices line up with the format string above.
        idx = 0

        def take() -> Any:
            nonlocal idx
            x = v[idx]
            idx += 1
            return x

        is_race_on = bool(take())
        timestamp_ms = int(take())
        engine_max_rpm = float(take())
        engine_idle_rpm = float(take())
        current_rpm = float(take())
        ax, ay, az = float(take()), float(take()), float(take())
        vx, vy, vz = float(take()), float(take()), float(take())
        wx, wy, wz = float(take()), float(take()), float(take())
        yaw, pitch, roll = float(take()), float(take()), float(take())
        susp_norm = [float(take()) for _ in range(4)]
        slip_ratio = [float(take()) for _ in range(4)]
        wheel_rot = [float(take()) for _ in range(4)]
        on_rumble = [int(take()) for _ in range(4)]
        in_puddle = [int(take()) for _ in range(4)]  # FR-023
        surface_rumble = [float(take()) for _ in range(4)]
        slip_angle = [float(take()) for _ in range(4)]
        combined_slip = [float(take()) for _ in range(4)]
        susp_m = [float(take()) for _ in range(4)]

        car_ordinal = int(take())
        car_class_raw = int(take())
        car_pi = int(take())
        drivetrain_raw = int(take())
        num_cylinders = int(take())
        car_group = int(take())
        smashable_vel_diff = float(take())
        smashable_mass = float(take())

        px, py, pz = float(take()), float(take()), float(take())
        speed = float(take())
        power = float(take())
        torque = float(take())
        # Forza emits tire temps in Fahrenheit.
        tire_temp_c = [(float(take()) - 32.0) * 5.0 / 9.0 for _ in range(4)]

        boost = float(take())
        fuel = float(take())
        distance = float(take())
        best_lap = float(take())
        last_lap = float(take())
        current_lap = float(take())
        race_time = float(take())

        lap_number = int(take())  # U16; LapNumber=0 is legitimate (FR-021)
        race_position = int(take())
        accel_u8 = int(take())
        brake_u8 = int(take())
        clutch_u8 = int(take())
        handbrake_u8 = int(take())
        gear_u8 = int(take())
        steer_s8 = int(take())
        driving_line_s8 = int(take())
        ai_brake_delta_s8 = int(take())
        tail = int(take())

        wheels: dict[str, dict[str, float | int]] = {}
        for i, key in enumerate(("fl", "fr", "rl", "rr")):
            wheels[key] = {
                "slipRatio": slip_ratio[i],
                "slipAngle": slip_angle[i],
                "combinedSlip": combined_slip[i],
                "rotation_rad_s": wheel_rot[i],
                "suspensionTravel_norm": susp_norm[i],
                "suspensionTravel_m": susp_m[i],
                "tireTemp_c": tire_temp_c[i],
                "tireTemp_normWindow": tire_temp_norm_window(
                    tire_temp_c[i],
                    _TIRE_TEMP_OPTIMAL_LOW_C,
                    _TIRE_TEMP_OPTIMAL_HIGH_C,
                ),
                "onRumble": on_rumble[i],
                "inPuddle": in_puddle[i],  # 0/1 boolean (FR-023)
                "surfaceRumble": surface_rumble[i],
            }

        # Optional Motorsport-style tire wear at offsets 324..339.
        tire_wear: dict[str, float] | None = None
        tire_wear_source: str = "modeled"
        if len(payload) >= _TIRE_WEAR_SIZE:
            try:
                wear_vals = _TIRE_WEAR_STRUCT.unpack_from(payload, _EXPECTED_SIZE)
            except struct.error as exc:  # pragma: no cover
                raise MalformedPacket(str(exc)) from exc
            tire_wear = {
                "fl": float(wear_vals[0]),
                "fr": float(wear_vals[1]),
                "rl": float(wear_vals[2]),
                "rr": float(wear_vals[3]),
            }
            tire_wear_source = "packet"

        return FrameRaw(
            is_race_on=is_race_on,
            timestamp_ms=timestamp_ms,
            engine={
                "rpm": current_rpm,
                "idleRpm": engine_idle_rpm,
                "maxRpm": engine_max_rpm,
                "power_w": power,
                "torque_nm": torque,
                "boost_psi": boost,
                "fuel": fuel,
            },
            drivetrain={
                "gear": gear_u8,
                "clutch": u8_to_norm(clutch_u8),
                "type": _DRIVETRAIN.get(drivetrain_raw, "AWD"),
            },
            motion={
                "speed_mps": speed,
                "velocity": {"x": vx, "y": vy, "z": vz},
                "acceleration": {"x": ax, "y": ay, "z": az},
                "angularVelocity": {"x": wx, "y": wy, "z": wz},
                "orientation": {"yaw": yaw, "pitch": pitch, "roll": roll},
                "position": {"x": px, "y": py, "z": pz},
            },
            inputs={
                "throttle": u8_to_norm(accel_u8),
                "brake": u8_to_norm(brake_u8),
                "clutch": u8_to_norm(clutch_u8),
                "handbrake": u8_to_norm(handbrake_u8),
                "steer": s8_to_norm(steer_s8),
                "drivingLine": s8_to_norm(driving_line_s8),
                "aiBrakeDelta": s8_to_norm(ai_brake_delta_s8),
            },
            wheels=wheels,
            world={
                "carOrdinal": car_ordinal,
                "carClass": _CAR_CLASS.get(car_class_raw, "?"),
                "carClassRaw": car_class_raw,
                "performanceIndex": car_pi,
                "numCylinders": num_cylinders,
                "carGroup": car_group,
                "smashableVelDiff": smashable_vel_diff,
                "smashableMass": smashable_mass,
                "distanceTraveled": distance,
            },
            race={
                # Per FR-021 / API spec §12 item 9: 0.0 in lap times → null.
                "lap": lap_number,  # LapNumber=0 is legitimate; preserved as int.
                "position": race_position,
                "currentLapS": zero_lap_to_none(current_lap),
                "lastLapS": zero_lap_to_none(last_lap),
                "bestLapS": zero_lap_to_none(best_lap),
                "raceTimeS": race_time,
            },
            tail_reserved_byte=tail,
            tire_wear=tire_wear,
            tire_wear_source=tire_wear_source,
        )
