"""predictions: add confidence value + tolerance_band columns.

The Prediction entity carries a `Confidence` value object with three
fields: `value`, `tolerance_band`, `model_version`. The table only had
`model_version`; the other two had no home. The Pg adapter landing in
2d.6 persists all three.

Revision ID: 0010_prediction_confidence
Revises: 0009_driver_analyzed_stats
Create Date: 2026-05-24 13:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_prediction_confidence"
down_revision: str | Sequence[str] | None = "0009_driver_analyzed_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column(
            "confidence_value",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "confidence_tolerance_band",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("predictions", "confidence_tolerance_band")
    op.drop_column("predictions", "confidence_value")
