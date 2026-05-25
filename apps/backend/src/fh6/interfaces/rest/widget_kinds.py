"""Backend-side allow-list for widget kinds in layout PUT/PATCH bodies.

The widget *catalog* (kind → title / default size / etc.) is a frontend
concern — `apps/web/.../widgetRegistry.jsx` is authoritative for what
the UI knows how to render. The backend only needs to reject *unknown*
kinds when persisting layouts so a typo doesn't permanently corrupt
someone's saved page.

If the frontend adds a new widget kind, append it here. Removing kinds
is a separate decision (existing saved layouts may reference them).
"""

from __future__ import annotations

# Kinds the frontend renders today; mirrors `apps/web/client/src/widgetRegistry.jsx`.
KINDS: frozenset[str] = frozenset(
    {
        "speed_dial",
        "rpm_tape",
        "rpm_dial",
        "tire_heatmap",
        "tire_viz",
        "tire_wear",
        "tire_failure",
        "world_map",
        "coach_feed",
        "lap_predict",
        "finish_predict",
        "fingerprint",
        "grip_budget",
        "shift_coach",
        "shift_report",
        "session_summary",
        "gear_display",
        "pedals",
        "lap_timer",
        "g_meter",
        "style_drift",
        "highlight_reel",
        "lap_table",
        "lap_compare",
        "steering_wheel",
        "car_silhouette",
        "speed_trace",
        "suspension_viz",
        "boost_gauge",
        "dyno_plot",
        "input_trace",
        "slip_warning",
        "power_flow",
        "crash_risk",
        "race_stats",
        "car_badge",
        "engine_cutaway",
        "physics_insights",
        "position_tracker",
        "stint_timer",
    }
)


__all__ = ["KINDS"]
