"""add ON DELETE CASCADE to all session_id FKs

Revision ID: 0002_session_fks_cascade
Revises: 0001_initial
Create Date: 2026-05-18 04:35

Without this, deleting a session row raises ForeignKeyViolationError when any
child row exists in frames / coach_callouts / coach_insights / predictions /
replays. The cascade now happens at the DB level, removing the manual loops
the repos had previously been forced to do.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_session_fks_cascade"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (child_table, fk_constraint_name)
_SESSION_FKS: tuple[tuple[str, str], ...] = (
    ("frames", "frames_session_id_fkey"),
    ("coach_callouts", "coach_callouts_session_id_fkey"),
    ("coach_insights", "coach_insights_session_id_fkey"),
    ("predictions", "predictions_session_id_fkey"),
    ("replays", "replays_session_id_fkey"),
)


def upgrade() -> None:
    for table, fk in _SESSION_FKS:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(
            fk,
            source_table=table,
            referent_table="sessions",
            local_cols=["session_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, fk in _SESSION_FKS:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(
            fk,
            source_table=table,
            referent_table="sessions",
            local_cols=["session_id"],
            remote_cols=["id"],
        )
