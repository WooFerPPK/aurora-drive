"""initial schema: metadata tables + frames hypertable + continuous aggregates

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-17 12:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    # --- Metadata tables ---
    op.create_table(
        "cars",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("display_name", sa.String, nullable=False, server_default=""),
        sa.Column("short_name", sa.String, nullable=False, server_default=""),
        sa.Column("car_ordinal", sa.Integer, nullable=False),
        sa.Column("car_class", sa.String, nullable=False, server_default="?"),
        sa.Column("performance_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("drivetrain", sa.String, nullable=False, server_default="AWD"),
        sa.Column("car_group", sa.Integer, nullable=False, server_default="0"),
        sa.Column("car_group_label", sa.String, nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_seconds_driven", sa.Float, nullable=False, server_default="0"),
    )

    op.create_table(
        "tracks",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("display_name", sa.String, nullable=False, server_default=""),
        sa.Column("inferred", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("confirmed_name", sa.String, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outline", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("corners", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("car_id", sa.String, sa.ForeignKey("cars.id"), nullable=False, index=True),
        sa.Column("type", sa.String, nullable=False, server_default="free_roam"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("duration_s", sa.Float, nullable=True),
        sa.Column("distance_m", sa.Float, nullable=False, server_default="0"),
        sa.Column("top_speed_mps", sa.Float, nullable=False, server_default="0"),
        sa.Column("lap_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_lap_s", sa.Float, nullable=True),
        sa.Column("track_id", sa.String, sa.ForeignKey("tracks.id"), nullable=True),
        sa.Column("summary", sa.String, nullable=False, server_default=""),
        sa.Column("style_drift_delta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("closed_reason", sa.String, nullable=True),
    )

    op.create_table(
        "driver_profile",
        sa.Column("id", sa.String, primary_key=True, server_default="local"),
        sa.Column("laps_analyzed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fingerprint", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("fingerprint_baseline_90d", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("traits", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("strengths", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("weaknesses", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("car_agnostic_share", sa.Float, nullable=False, server_default="0"),
        sa.Column("persona", sa.String, nullable=False, server_default=""),
        sa.Column("persona_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String, nullable=False, server_default="placeholder"),
    )

    op.create_table(
        "coach_callouts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False, index=True
        ),
        sa.Column("at_session_seconds", sa.Float, nullable=False),
        sa.Column("priority", sa.String, nullable=False),
        sa.Column("lap_context", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("text", sa.String, nullable=False),
        sa.Column("cites", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("model_version", sa.String, nullable=False, server_default=""),
        sa.Column("voice", sa.String, nullable=False, server_default="friendly_codriver"),
    )

    op.create_table(
        "coach_insights",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False, index=True
        ),
        sa.Column("priority", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("body", sa.String, nullable=False, server_default=""),
        sa.Column("tone", sa.String, nullable=False),
        sa.Column("actions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("delta_if_fixed_s", sa.Float, nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_id", sa.String, nullable=True),
    )

    op.create_table(
        "predictions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False, index=True),
        sa.Column(
            "session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False, index=True
        ),
        sa.Column("predicted_at_session_seconds", sa.Float, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("model_version", sa.String, nullable=False),
        sa.Column("inputs", sa.JSON, nullable=False, server_default="[]"),
    )

    op.create_table(
        "replays",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column(
            "session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False, index=True
        ),
        sa.Column("from_s", sa.Float, nullable=False),
        sa.Column("to_s", sa.Float, nullable=False),
        sa.Column("frames", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("annotations", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("tweaks", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "mistakes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("car_id", sa.String, sa.ForeignKey("cars.id"), nullable=False, index=True),
        sa.Column("track_id", sa.String, sa.ForeignKey("tracks.id"), nullable=False, index=True),
        sa.Column("pos", sa.JSON, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("corner", sa.String, nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "layouts",
        sa.Column("page_id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False, server_default=""),
        sa.Column("grid", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("widgets", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Frames hypertable ---
    op.create_table(
        "frames",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("car_id", sa.String, sa.ForeignKey("cars.id"), nullable=False),
        sa.Column("packet_timestamp_ms", sa.BigInteger, nullable=False),
        sa.Column("is_race_on", sa.Boolean, nullable=False),
        sa.Column("race", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("engine", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("drivetrain", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("motion", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("inputs", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("wheels", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("world", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("derived", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("modeled", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("tail_reserved_byte", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("session_id", "time"),
    )
    op.create_index("idx_frames_time", "frames", ["time"])
    op.create_index("idx_frames_car_time", "frames", ["car_id", "time"])

    # Convert to hypertable. Chunk = 1 hour per research R-3.
    op.execute(
        "SELECT create_hypertable('frames', 'time', "
        "chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE);"
    )

    # --- Continuous aggregates: 30 Hz and 10 Hz materializations ---
    # Implementation note: full continuous-aggregate views with refresh
    # policies require additional config (timescaledb.continuous, etc.).
    # MVP installation creates the materializations and refresh policies
    # via raw SQL. They project a subset of fields the UI needs at lower
    # cadence. Higher-fidelity scrub paths still query `frames` directly.
    op.execute(
        """
        CREATE MATERIALIZED VIEW frames_30hz
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '33 milliseconds', time) AS bucket,
            session_id,
            car_id,
            last(is_race_on, time) AS is_race_on,
            last(race, time) AS race,
            last(engine, time) AS engine,
            last(motion, time) AS motion,
            last(inputs, time) AS inputs,
            last(wheels, time) AS wheels,
            last(derived, time) AS derived,
            last(modeled, time) AS modeled
        FROM frames
        GROUP BY bucket, session_id, car_id
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'frames_30hz',
            start_offset => INTERVAL '5 minutes',
            end_offset   => INTERVAL '5 seconds',
            schedule_interval => INTERVAL '30 seconds'
        );
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW frames_10hz
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '100 milliseconds', time) AS bucket,
            session_id,
            car_id,
            last(is_race_on, time) AS is_race_on,
            last(race, time) AS race,
            last(engine, time) AS engine,
            last(motion, time) AS motion,
            last(inputs, time) AS inputs,
            last(wheels, time) AS wheels,
            last(derived, time) AS derived,
            last(modeled, time) AS modeled
        FROM frames
        GROUP BY bucket, session_id, car_id
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'frames_10hz',
            start_offset => INTERVAL '5 minutes',
            end_offset   => INTERVAL '5 seconds',
            schedule_interval => INTERVAL '60 seconds'
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS frames_10hz;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS frames_30hz;")
    op.drop_table("frames")
    op.drop_table("layouts")
    op.drop_table("settings")
    op.drop_table("mistakes")
    op.drop_table("replays")
    op.drop_table("predictions")
    op.drop_table("coach_insights")
    op.drop_table("coach_callouts")
    op.drop_table("driver_profile")
    op.drop_table("sessions")
    op.drop_table("tracks")
    op.drop_table("cars")
