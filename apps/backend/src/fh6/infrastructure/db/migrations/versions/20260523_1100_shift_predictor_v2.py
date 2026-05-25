"""shift predictor v2: transmission_modes + downshift columns on shift_events_clean.

Adds one new table and two new nullable columns on the existing audit table.

Revision ID: 0008_shift_predictor_v2
Revises: 0007_shift_predictor
Create Date: 2026-05-23 11:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_shift_predictor_v2"
down_revision: str | Sequence[str] | None = "0007_shift_predictor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transmission_modes",
        sa.Column("car_ordinal", sa.Integer(), nullable=False),
        sa.Column("performance_index", sa.Integer(), nullable=False),
        sa.Column("num_cylinders", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("car_ordinal", "performance_index", "num_cylinders"),
    )
    # Downshift evaluator columns (FR-048).
    # Upshift rows leave `recommended_post_rpm` NULL; downshift rows populate both.
    op.add_column(
        "shift_events_clean",
        sa.Column("post_shift_rpm", sa.Float(), nullable=True),
    )
    op.add_column(
        "shift_events_clean",
        sa.Column("recommended_post_rpm", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shift_events_clean", "recommended_post_rpm")
    op.drop_column("shift_events_clean", "post_shift_rpm")
    op.drop_table("transmission_modes")
