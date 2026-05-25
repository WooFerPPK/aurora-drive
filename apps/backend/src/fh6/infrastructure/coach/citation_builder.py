"""T111: CitationBuilder.

Builds the API spec §7B citation shapes from a session window or
sector aggregate. Used by both the live CalloutEngine (T099) and the
Q&A AskCoach use case (T110).
"""

from __future__ import annotations

from datetime import datetime

from fh6.domain.value_objects.ids import SessionId


def telemetry_window(
    *,
    session_id: SessionId,
    from_at: datetime,
    to_at: datetime,
    fields: list[str],
) -> dict[str, object]:
    return {
        "kind": "telemetry_window",
        "sessionId": str(session_id),
        "from": from_at.isoformat(),
        "to": to_at.isoformat(),
        "fields": fields,
    }


def lap_aggregate(
    *,
    session_id: SessionId,
    sector: int,
) -> dict[str, object]:
    return {
        "kind": "lap_aggregate",
        "sessionId": str(session_id),
        "sector": sector,
    }
