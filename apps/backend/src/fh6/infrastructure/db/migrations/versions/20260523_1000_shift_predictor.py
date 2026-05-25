"""shift predictor tables.

Adds four tables for the learned engine torque curve and shift event audit:
- engine_curves       (per fingerprint per gear per RPM bin)
- gear_ratios         (per fingerprint per gear)
- class_priors        (averaged curve per class key)
- shift_events_clean  (per session, audit only)

Revision ID: 0007_shift_predictor
Revises: 0006_session_events
Create Date: 2026-05-23 10:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_shift_predictor"
down_revision: str | Sequence[str] | None = "0006_session_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engine_curves",
        sa.Column("car_ordinal", sa.Integer(), nullable=False),
        sa.Column("performance_index", sa.Integer(), nullable=False),
        sa.Column("num_cylinders", sa.Integer(), nullable=False),
        sa.Column("gear", sa.Integer(), nullable=False),
        sa.Column("rpm_bin", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mean_torque_nm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("m2_torque", sa.Float(), nullable=False, server_default="0"),
        sa.Column("q90_torque_nm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mean_boost_psi", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "car_ordinal", "performance_index", "num_cylinders", "gear", "rpm_bin"
        ),
    )

    op.create_table(
        "gear_ratios",
        sa.Column("car_ordinal", sa.Integer(), nullable=False),
        sa.Column("performance_index", sa.Integer(), nullable=False),
        sa.Column("num_cylinders", sa.Integer(), nullable=False),
        sa.Column("gear", sa.Integer(), nullable=False),
        sa.Column("ratio", sa.Float(), nullable=False),
        sa.Column("variance", sa.Float(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("car_ordinal", "performance_index", "num_cylinders", "gear"),
    )

    op.create_table(
        "class_priors",
        sa.Column("car_class", sa.String(length=4), nullable=False),
        sa.Column("car_group", sa.Integer(), nullable=False),
        sa.Column("drivetrain_type", sa.String(length=8), nullable=False),
        sa.Column("num_cylinders", sa.Integer(), nullable=False),
        sa.Column("gear", sa.Integer(), nullable=False),
        sa.Column("rpm_bin", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("q90_torque_nm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_built", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "car_class", "car_group", "drivetrain_type", "num_cylinders", "gear", "rpm_bin"
        ),
    )

    op.create_table(
        "shift_events_clean",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("car_ordinal", sa.Integer(), nullable=False),
        sa.Column("performance_index", sa.Integer(), nullable=False),
        sa.Column("num_cylinders", sa.Integer(), nullable=False),
        sa.Column("shift_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gear_from", sa.Integer(), nullable=False),
        sa.Column("gear_to", sa.Integer(), nullable=False),
        sa.Column("actual_rpm", sa.Float(), nullable=False),
        sa.Column("recommended_rpm", sa.Float(), nullable=True),
        sa.Column("recommendation_conf", sa.Float(), nullable=True),
        sa.Column("predicted_post_torque", sa.Float(), nullable=True),
        sa.Column("measured_post_torque", sa.Float(), nullable=True),
        sa.Column("est_cost_s", sa.Float(), nullable=True),
    )
    op.create_index("ix_shift_events_session", "shift_events_clean", ["session_id"])
    op.create_index(
        "ix_shift_events_fingerprint",
        "shift_events_clean",
        ["car_ordinal", "performance_index", "num_cylinders"],
    )


def downgrade() -> None:
    op.drop_index("ix_shift_events_fingerprint", "shift_events_clean")
    op.drop_index("ix_shift_events_session", "shift_events_clean")
    op.drop_table("shift_events_clean")
    op.drop_table("class_priors")
    op.drop_table("gear_ratios")
    op.drop_table("engine_curves")
