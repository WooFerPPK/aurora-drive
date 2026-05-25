from __future__ import annotations

import math
import os
from unittest.mock import patch

from fh6.infrastructure.config import load_from_env


def test_rewind_defaults_present_when_env_unset() -> None:
    with patch.dict(os.environ, {}, clear=False):
        for k in (
            "FH6_REWIND_CONTINUITY_THRESHOLD_M",
            "FH6_REWIND_MATCH_TOLERANCE_M",
            "FH6_REWIND_YAW_TOLERANCE_RAD",
            "FH6_REWIND_PAUSE_FLOOR_MS",
        ):
            os.environ.pop(k, None)
        cfg = load_from_env()
    assert cfg.rewind_continuity_threshold_m == 20.0
    assert cfg.rewind_match_tolerance_m == 5.0
    assert abs(cfg.rewind_yaw_tolerance_rad - (math.pi / 2)) < 1e-9
    assert cfg.rewind_pause_floor_ms == 250


def test_rewind_env_overrides() -> None:
    env = {
        "FH6_REWIND_CONTINUITY_THRESHOLD_M": "30.0",
        "FH6_REWIND_MATCH_TOLERANCE_M": "2.5",
        "FH6_REWIND_YAW_TOLERANCE_RAD": "1.0",
        "FH6_REWIND_PAUSE_FLOOR_MS": "500",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = load_from_env()
    assert cfg.rewind_continuity_threshold_m == 30.0
    assert cfg.rewind_match_tolerance_m == 2.5
    assert cfg.rewind_yaw_tolerance_rad == 1.0
    assert cfg.rewind_pause_floor_ms == 500
