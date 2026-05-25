"""Runtime configuration via pydantic-settings.

Replaces the hand-rolled `os.environ.get` loader with a typed BaseSettings
class. Field defaults live on the class; pydantic-settings reads
`FH6_<UPPER_SNAKE_CASE>` from the environment (and from `.env` if present
in the working directory).

Boot-time validation runs as a `model_validator(mode="after")` so
constructing an invalid config raises immediately rather than blowing up
at the first call site.
"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FH6_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    listen_addr: str = "127.0.0.1"
    listen_port: int = 5302
    http_host: str = "127.0.0.1"
    http_port: int = 8000
    db_dsn: str = "postgresql+asyncpg://fh6:fh6@127.0.0.1:5432/fh6"
    redis_url: str | None = None
    llm_dry_run: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "pretty"] = "pretty"

    rewind_continuity_threshold_m: float = 20.0
    rewind_match_tolerance_m: float = 5.0
    rewind_yaw_tolerance_rad: float = math.pi / 2
    rewind_pause_floor_ms: int = 250

    shift_throttle_min: float = 0.95
    shift_brake_max: float = 0.05
    shift_steer_max: float = 0.10
    shift_combined_slip_max: float = 0.20
    shift_gear_stable_frames: int = 5
    shift_warmup_seconds: int = 60
    shift_boost_settle_psi_per_s: float = 1.0
    shift_ewma_half_life_samples: int = 54_000
    shift_bin_min_count: int = 10
    shift_pair_learned_samples: int = 200
    shift_change_z_threshold: float = 3.0
    shift_change_bins_required: int = 3
    shift_recompute_every_n: int = 50
    shift_display_throttle_min: float = 0.70
    shift_turbo_residual_delay_ms: int = 500
    shift_na_residual_delay_ms: int = 300
    shift_residual_window_ms: int = 200
    shift_prior_rebuild_cooldown_s: int = 300
    shift_prior_min_fp_samples: int = 1000
    shift_tcs_slip_threshold: float = 0.50
    shift_tcs_torque_floor_ratio: float = 0.85
    shift_assist_alert_pct: float = 0.05
    shift_assist_recent_window: int = 900
    shift_trans_mode_ring_cap: int = 30
    shift_trans_mode_min_samples: int = 10
    shift_trans_mode_auto_stdev_rpm: float = 50.0
    shift_downshift_brake_display_min: float = 0.10
    shift_downshift_throttle_display_max: float = 0.30

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        # FR-005 / SC-010: refuse to bind to FH6's reserved UDP range.
        if 5200 <= self.listen_port <= 5300:
            raise ValueError(
                f"listen port {self.listen_port} is in FH6 reserved range "
                "[5200, 5300]; constitution / FR-005 / SC-010"
            )
        # FR-037: TCS slip threshold must lie above the v1 slip max so the
        # TrainingFilter's ordered slip-band check classifies frames into
        # the right band (assist_intervention vs slip).
        if self.shift_tcs_slip_threshold <= self.shift_combined_slip_max:
            raise ValueError(
                f"shift_tcs_slip_threshold ({self.shift_tcs_slip_threshold}) must be "
                f"greater than shift_combined_slip_max ({self.shift_combined_slip_max})"
            )
        return self


def load_from_env() -> AppConfig:
    """Construct an AppConfig from the process environment.

    Thin wrapper kept for call-site compatibility; pydantic-settings
    reads env automatically when `AppConfig()` is constructed.
    """
    return AppConfig()
