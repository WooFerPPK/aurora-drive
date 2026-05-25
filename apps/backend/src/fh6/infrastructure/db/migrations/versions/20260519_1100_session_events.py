"""session_events table.

Stores per-session event log produced by event_emitter so historical
sessions can render their highlight reel / chronological event list.

Revision ID: 0006_session_events
Revises: 0005_session_name_bookmarked
Create Date: 2026-05-19 11:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_session_events"
down_revision: str | Sequence[str] | None = "0005_session_name_bookmarked"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("at_s", sa.Float(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_session_events_session_id_at_s",
        "session_events",
        ["session_id", "at_s"],
    )
    op.create_index("ix_session_events_kind", "session_events", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_session_events_kind", table_name="session_events")
    op.drop_index("ix_session_events_session_id_at_s", table_name="session_events")
    op.drop_table("session_events")
