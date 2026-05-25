"""driver_profile: add analyzed-stats columns.

Adds `distance_analyzed_m` and `seconds_analyzed` to `driver_profile`.
The DriverProfile dataclass and the `/api/driver/profile` REST response
have always exposed these fields, but the table never had columns for
them — the legacy boot-time _InMemoryDriverRepository hid the drift.
The Pg adapter landing in 2d.2 needs the columns to persist what the
domain model carries.

Revision ID: 0009_driver_analyzed_stats
Revises: 0008_shift_predictor_v2
Create Date: 2026-05-24 12:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_driver_analyzed_stats"
down_revision: str | Sequence[str] | None = "0008_shift_predictor_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "driver_profile",
        sa.Column(
            "distance_analyzed_m",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "driver_profile",
        sa.Column(
            "seconds_analyzed",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("driver_profile", "seconds_analyzed")
    op.drop_column("driver_profile", "distance_analyzed_m")
