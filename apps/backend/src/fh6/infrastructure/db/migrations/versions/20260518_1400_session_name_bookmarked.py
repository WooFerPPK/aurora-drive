"""add session metadata columns: name and bookmarked

Revision ID: 0005_session_name_bookmarked
Revises: 0004_session_laps
Create Date: 2026-05-18 14:00

Frontend Sessions page needs to rename sessions and pin favourites.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_session_name_bookmarked"
down_revision: str | Sequence[str] | None = "0004_session_laps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("name", sa.Text(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "bookmarked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "bookmarked")
    op.drop_column("sessions", "name")
