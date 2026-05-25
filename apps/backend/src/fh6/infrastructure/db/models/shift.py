"""SQLAlchemy models for the shift predictor tables.

Four tables added by migration 0007_shift_predictor:
- engine_curves       (per fingerprint per gear per RPM bin)
- gear_ratios         (per fingerprint per gear)
- class_priors        (averaged curve per class key)
- shift_events_clean  (per session shift audit)

Migration 0008_shift_predictor_v2 adds:
- transmission_modes  (per fingerprint detected gearbox mode)
- two new nullable columns on shift_events_clean (downshift evaluator)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class EngineCurveModel(Base):
    __tablename__ = "engine_curves"

    car_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    performance_index: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    num_cylinders: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    gear: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    rpm_bin: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_torque_nm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    m2_torque: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    q90_torque_nm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mean_boost_psi: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_updated: Mapped[datetime] = mapped_column(nullable=False)


class GearRatioModel(Base):
    __tablename__ = "gear_ratios"

    car_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    performance_index: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    num_cylinders: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    gear: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    ratio: Mapped[float] = mapped_column(Float, nullable=False)
    variance: Mapped[float] = mapped_column(Float, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(nullable=False)


class ClassPriorModel(Base):
    __tablename__ = "class_priors"

    car_class: Mapped[str] = mapped_column(String(4), primary_key=True, nullable=False)
    car_group: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    drivetrain_type: Mapped[str] = mapped_column(String(8), primary_key=True, nullable=False)
    num_cylinders: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    gear: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    rpm_bin: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    q90_torque_nm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_built: Mapped[datetime] = mapped_column(nullable=False)


class ShiftEventCleanModel(Base):
    __tablename__ = "shift_events_clean"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    car_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_index: Mapped[int] = mapped_column(Integer, nullable=False)
    num_cylinders: Mapped[int] = mapped_column(Integer, nullable=False)
    shift_at: Mapped[datetime] = mapped_column(nullable=False)
    gear_from: Mapped[int] = mapped_column(Integer, nullable=False)
    gear_to: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_rpm: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation_conf: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_post_torque: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_post_torque: Mapped[float | None] = mapped_column(Float, nullable=True)
    est_cost_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Downshift evaluator columns (FR-048). Upshift rows leave
    # `recommended_post_rpm` NULL; downshift rows populate both.
    post_shift_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_post_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_shift_events_session", "session_id"),
        Index("ix_shift_events_fingerprint", "car_ordinal", "performance_index", "num_cylinders"),
    )


class TransmissionModeModel(Base):
    """Detected transmission mode per engine fingerprint (FR-042).

    Primary key is the full EngineFingerprint tuple. Populated by
    `TransmissionModeInferer` once the calibration sample count crosses
    its confidence threshold.
    """

    __tablename__ = "transmission_modes"

    car_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    performance_index: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    num_cylinders: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
