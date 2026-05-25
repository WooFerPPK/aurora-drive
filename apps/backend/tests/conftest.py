from __future__ import annotations

from typing import Any

import pytest


def _pack_golden_packet(**overrides: Any) -> bytes:
    """Build a valid 324-byte FH6 Data Out payload with sane defaults.

    Tests pass overrides to vary fields. The byte layout MUST match
    src/fh6/infrastructure/telemetry/fh6_decoder.py._STRUCT_FORMAT.
    """
    fields: dict[str, Any] = {
        # 0..192 (49 fields)
        "IsRaceOn": 1,
        "TimestampMS": 1_000,
        "EngineMaxRpm": 8000.0,
        "EngineIdleRpm": 900.0,
        "CurrentEngineRpm": 6240.0,
        "AccelX": 0.0,
        "AccelY": 0.0,
        "AccelZ": 1.9,
        "VelX": 0.0,
        "VelY": 0.0,
        "VelZ": 41.7,
        "AngVelX": 0.0,
        "AngVelY": 0.1,
        "AngVelZ": 0.0,
        "Yaw": 1.57,
        "Pitch": 0.0,
        "Roll": 0.0,
        # 4 quartets F32
        "SuspNormFL": 0.5,
        "SuspNormFR": 0.5,
        "SuspNormRL": 0.5,
        "SuspNormRR": 0.5,
        "SlipRatioFL": 0.04,
        "SlipRatioFR": 0.04,
        "SlipRatioRL": 0.05,
        "SlipRatioRR": 0.05,
        "WheelRotFL": 96.0,
        "WheelRotFR": 96.0,
        "WheelRotRL": 96.0,
        "WheelRotRR": 96.0,
        # 2 quartets S32
        "OnRumbleFL": 0,
        "OnRumbleFR": 0,
        "OnRumbleRL": 0,
        "OnRumbleRR": 0,
        "InPuddleFL": 0,
        "InPuddleFR": 0,
        "InPuddleRL": 0,
        "InPuddleRR": 0,
        # 3 quartets F32
        "SurfRumbleFL": 0.03,
        "SurfRumbleFR": 0.03,
        "SurfRumbleRL": 0.03,
        "SurfRumbleRR": 0.03,
        "SlipAngleFL": 0.07,
        "SlipAngleFR": 0.07,
        "SlipAngleRL": 0.07,
        "SlipAngleRR": 0.07,
        "CombSlipFL": 0.09,
        "CombSlipFR": 0.09,
        "CombSlipRL": 0.09,
        "CombSlipRR": 0.09,
        # 196..208 suspension meters
        "SuspMFL": 0.07,
        "SuspMFR": 0.07,
        "SuspMRL": 0.07,
        "SuspMRR": 0.07,
        # 212..240
        "CarOrdinal": 2451,
        "CarClass": 3,  # → "A"
        "CarPI": 812,
        "Drivetrain": 2,  # → AWD
        "NumCylinders": 6,
        "CarGroup": 18,
        "SmashableVelDiff": 0.0,
        "SmashableMass": 0.0,
        # 244..280
        "PosX": 12843.6,
        "PosY": 312.4,
        "PosZ": -5421.9,
        "Speed": 41.7,
        "Power": 257000.0,
        "Torque": 490.0,
        "TireTempFL": 184.0,
        "TireTempFR": 184.0,
        "TireTempRL": 184.0,
        "TireTempRR": 184.0,
        # 284..308
        "Boost": 11.8,
        "Fuel": 0.63,
        "DistanceTraveled": 23420.0,
        "BestLap": 68.421,
        "LastLap": 69.012,
        "CurrentLap": 12.441,
        "CurrentRaceTime": 134.992,
        # 312
        "LapNumber": 8,
        # 314..322
        "RacePosition": 3,
        "Accel": 214,  # ≈0.84 / 255
        "Brake": 0,
        "Clutch": 0,
        "HandBrake": 0,
        "Gear": 4,
        "Steer": -12,
        "DrivingLine": 3,
        "AIBrakeDelta": -4,
        # 323
        "TailReserved": 0,
    }
    fields.update(overrides)

    values = (
        fields["IsRaceOn"],
        fields["TimestampMS"],
        fields["EngineMaxRpm"],
        fields["EngineIdleRpm"],
        fields["CurrentEngineRpm"],
        fields["AccelX"],
        fields["AccelY"],
        fields["AccelZ"],
        fields["VelX"],
        fields["VelY"],
        fields["VelZ"],
        fields["AngVelX"],
        fields["AngVelY"],
        fields["AngVelZ"],
        fields["Yaw"],
        fields["Pitch"],
        fields["Roll"],
        fields["SuspNormFL"],
        fields["SuspNormFR"],
        fields["SuspNormRL"],
        fields["SuspNormRR"],
        fields["SlipRatioFL"],
        fields["SlipRatioFR"],
        fields["SlipRatioRL"],
        fields["SlipRatioRR"],
        fields["WheelRotFL"],
        fields["WheelRotFR"],
        fields["WheelRotRL"],
        fields["WheelRotRR"],
        fields["OnRumbleFL"],
        fields["OnRumbleFR"],
        fields["OnRumbleRL"],
        fields["OnRumbleRR"],
        fields["InPuddleFL"],
        fields["InPuddleFR"],
        fields["InPuddleRL"],
        fields["InPuddleRR"],
        fields["SurfRumbleFL"],
        fields["SurfRumbleFR"],
        fields["SurfRumbleRL"],
        fields["SurfRumbleRR"],
        fields["SlipAngleFL"],
        fields["SlipAngleFR"],
        fields["SlipAngleRL"],
        fields["SlipAngleRR"],
        fields["CombSlipFL"],
        fields["CombSlipFR"],
        fields["CombSlipRL"],
        fields["CombSlipRR"],
        fields["SuspMFL"],
        fields["SuspMFR"],
        fields["SuspMRL"],
        fields["SuspMRR"],
        fields["CarOrdinal"],
        fields["CarClass"],
        fields["CarPI"],
        fields["Drivetrain"],
        fields["NumCylinders"],
        fields["CarGroup"],
        fields["SmashableVelDiff"],
        fields["SmashableMass"],
        fields["PosX"],
        fields["PosY"],
        fields["PosZ"],
        fields["Speed"],
        fields["Power"],
        fields["Torque"],
        fields["TireTempFL"],
        fields["TireTempFR"],
        fields["TireTempRL"],
        fields["TireTempRR"],
        fields["Boost"],
        fields["Fuel"],
        fields["DistanceTraveled"],
        fields["BestLap"],
        fields["LastLap"],
        fields["CurrentLap"],
        fields["CurrentRaceTime"],
        fields["LapNumber"],
        fields["RacePosition"],
        fields["Accel"],
        fields["Brake"],
        fields["Clutch"],
        fields["HandBrake"],
        fields["Gear"],
        fields["Steer"],
        fields["DrivingLine"],
        fields["AIBrakeDelta"],
        fields["TailReserved"],
    )

    from fh6.infrastructure.telemetry.fh6_decoder import _STRUCT

    payload = _STRUCT.pack(*values)
    assert len(payload) == 324
    return payload


@pytest.fixture
def golden_packet() -> bytes:
    return _pack_golden_packet()


@pytest.fixture
def make_packet():
    return _pack_golden_packet
