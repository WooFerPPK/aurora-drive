"""add session_laps table for per-lap timing

Revision ID: 0004_session_laps
Revises: 0003_car_fks_cascade
Create Date: 2026-05-18 12:00

Stores one row per completed lap per session. UNIQUE(session_id, lap_number)
lets the application upsert on rewind: a rewound lap sends the same lap_number
again and the row is overwritten with the true (longer) lap time rather than
duplicated.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_session_laps"
down_revision: str | Sequence[str] | None = "0003_car_fks_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_laps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("lap_time_s", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="session_laps_session_id_fkey",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("session_id", "lap_number", name="uq_session_laps_session_lap"),
    )
    op.create_index("ix_session_laps_session_id", "session_laps", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_session_laps_session_id", table_name="session_laps")
    op.drop_table("session_laps")
