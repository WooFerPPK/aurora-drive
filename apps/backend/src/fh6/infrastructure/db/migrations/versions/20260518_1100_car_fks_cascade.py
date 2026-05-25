"""add ON DELETE CASCADE to all car_id FKs

Revision ID: 0003_car_fks_cascade
Revises: 0002_session_fks_cascade
Create Date: 2026-05-18 11:00

Lets DELETE on a `cars` row cascade through sessions / frames / mistakes
instead of raising ForeignKeyViolationError. Without this, the new
single-car delete endpoint and the `DELETE /api/data/all` wipe (which
now removes cars too) fail whenever any child row exists.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_car_fks_cascade"
down_revision: str | Sequence[str] | None = "0002_session_fks_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (child_table, fk_constraint_name)
_CAR_FKS: tuple[tuple[str, str], ...] = (
    ("sessions", "sessions_car_id_fkey"),
    ("frames", "frames_car_id_fkey"),
    ("mistakes", "mistakes_car_id_fkey"),
)


def upgrade() -> None:
    for table, fk in _CAR_FKS:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(
            fk,
            source_table=table,
            referent_table="cars",
            local_cols=["car_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, fk in _CAR_FKS:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(
            fk,
            source_table=table,
            referent_table="cars",
            local_cols=["car_id"],
            remote_cols=["id"],
        )
