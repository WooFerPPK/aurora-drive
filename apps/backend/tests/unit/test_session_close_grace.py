"""Session-lifecycle fixes: 5-second event-exit grace, Time Trial
classification, and tiny-lapless-fragment discard.

The Time Trial branch encodes the canonical FH6 discriminator: lap
clock running, no finishing-order `RacePosition` (it's only assigned in
graded races and Rivals).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fh6.application.services.session_manager import (
    BoundaryEvent,
    SessionManager,
    _session_type_from,
)
from fh6.domain.entities.session import SessionCloseReason, SessionType
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder


def _decode(payload: bytes):
    return FH6PacketDecoder().decode(payload)


# ---------------------------------------------------------------------------
# (1) 5-second close grace
# ---------------------------------------------------------------------------


def test_paused_game_burst_does_not_close_session(make_packet) -> None:
    """A short paused-menu burst (is_race_on=0, lap clock paused) under
    the CLOSE_GRACE_TICKS window must NOT close the in-flight race."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

    # Open a race session.
    race_pkt = _decode(
        make_packet(IsRaceOn=1, RacePosition=3, CurrentLap=30.0, CurrentRaceTime=30.0)
    )
    d = sm.on_frame(race_pkt, t0)
    assert d.event == BoundaryEvent.SESSION_STARTED
    session_id = sm.current.id

    # Send a paused burst: is_race_on=0, position/lap clock zeroed. 100
    # ticks is well under CLOSE_GRACE_TICKS=150, so the session must
    # stay open through the pause.
    pause_pkt = _decode(
        make_packet(IsRaceOn=0, RacePosition=0, CurrentLap=0.0, CurrentRaceTime=30.0)
    )
    for i in range(1, 101):
        d = sm.on_frame(pause_pkt, t0 + timedelta(milliseconds=33 * i))
        assert d.event == BoundaryEvent.APPENDED, f"closed at tick {i}"
        assert sm.current is not None
        assert sm.current.id == session_id

    # Resume the race — close_pending resets to 0, session continues.
    d = sm.on_frame(race_pkt, t0 + timedelta(seconds=5))
    assert d.event == BoundaryEvent.APPENDED
    assert sm.current.id == session_id


def test_close_grace_fires_after_full_window(make_packet) -> None:
    """Sustained !raw_in_event past CLOSE_GRACE_TICKS closes the session
    via the new not_in_event reason — no silence gap required."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

    race_pkt = _decode(
        make_packet(IsRaceOn=1, RacePosition=3, CurrentLap=30.0, CurrentRaceTime=30.0)
    )
    sm.on_frame(race_pkt, t0)
    # Send enough completed laps to clear the tiny-session discard bar.
    # Two line-crossings, both > MIN_LAP_SECS peak.
    sm.on_frame(
        _decode(make_packet(IsRaceOn=1, RacePosition=3, CurrentLap=55.0, CurrentRaceTime=80.0)),
        t0 + timedelta(seconds=1),
    )
    sm.on_frame(
        _decode(make_packet(IsRaceOn=1, RacePosition=3, CurrentLap=0.4, CurrentRaceTime=80.2)),
        t0 + timedelta(seconds=1.2),
    )

    pause_pkt = _decode(
        make_packet(IsRaceOn=0, RacePosition=0, CurrentLap=0.0, CurrentRaceTime=80.2)
    )
    # 149 ticks of !in_event — still open.
    for i in range(149):
        d = sm.on_frame(pause_pkt, t0 + timedelta(seconds=2, milliseconds=33 * i))
        assert d.event == BoundaryEvent.APPENDED, f"closed too early at tick {i}"

    # 150th tick — close_pending crosses CLOSE_GRACE_TICKS → close.
    d = sm.on_frame(pause_pkt, t0 + timedelta(seconds=10))
    assert d.event == BoundaryEvent.SESSION_ENDED
    assert d.closed_session is not None
    assert d.closed_session.closed_reason == SessionCloseReason.NOT_IN_EVENT
    assert d.opened_session is None
    assert sm.current is None


def test_raw_in_event_resets_pending_each_tick(make_packet) -> None:
    """Even single isolated in-event packets between paused ones reset
    the grace counter — the close should never fire if events keep
    arriving at all."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    race_pkt = _decode(
        make_packet(IsRaceOn=1, RacePosition=3, CurrentLap=30.0, CurrentRaceTime=30.0)
    )
    pause_pkt = _decode(
        make_packet(IsRaceOn=0, RacePosition=0, CurrentLap=0.0, CurrentRaceTime=30.0)
    )
    sm.on_frame(race_pkt, t0)

    # Alternate 100 paused / 1 race packets over a long burst.
    for cycle in range(5):
        for i in range(100):
            sm.on_frame(
                pause_pkt,
                t0 + timedelta(seconds=cycle * 10, milliseconds=30 * i),
            )
        sm.on_frame(race_pkt, t0 + timedelta(seconds=cycle * 10 + 4))
        assert sm.current is not None, f"closed during cycle {cycle}"


# ---------------------------------------------------------------------------
# (2) Time Trial detection
# ---------------------------------------------------------------------------


def test_time_trial_detected_when_lap_clock_runs_without_position(make_packet) -> None:
    """is_race_on=1, current_lap>0, race_position=0 → TIME_TRIAL.
    raceTimeS is irrelevant; Time Trial leaves it at 0."""
    raw = _decode(make_packet(IsRaceOn=1, CurrentRaceTime=0.0, RacePosition=0, CurrentLap=12.3))
    assert _session_type_from(raw) == SessionType.TIME_TRIAL


def test_time_trial_session_opens_with_correct_type(make_packet) -> None:
    """Opening a session on a Time Trial packet stamps type=TIME_TRIAL.
    The pre-fix behaviour stamped FREE_ROAM (position==0) which the API
    surfaces in `session.type` and downstream views key off."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    raw = _decode(
        make_packet(
            IsRaceOn=1,
            CurrentRaceTime=0.0,
            RacePosition=0,
            CurrentLap=12.3,
            LapNumber=1,
            BestLap=0.0,
        )
    )
    d = sm.on_frame(raw, t0)
    assert d.opened_session is not None
    assert d.opened_session.type == SessionType.TIME_TRIAL


def test_race_still_classified_when_position_present(make_packet) -> None:
    """The TIME_TRIAL branch must not shadow the existing RACE rule:
    position>0 AND race_time>0 still wins."""
    raw = _decode(make_packet(IsRaceOn=1, CurrentRaceTime=42.0, RacePosition=3, CurrentLap=15.0))
    assert _session_type_from(raw) == SessionType.RACE


# ---------------------------------------------------------------------------
# (3) Tiny lapless discard
# ---------------------------------------------------------------------------


def _drive_lapless_for(
    sm: SessionManager,
    make_packet,
    *,
    in_event_frames: int,
    start: datetime,
) -> None:
    """Open a session and append in-event packets without ever crossing
    the finish line. Lap peak stays under MIN_LAP_SECS so finalize_final_lap
    returns None and laps_recorded stays 0."""
    pkt = _decode(
        make_packet(
            IsRaceOn=1,
            RacePosition=3,
            CurrentLap=5.0,
            CurrentRaceTime=5.0,
            LapNumber=0,
            BestLap=0.0,
        )
    )
    for i in range(in_event_frames):
        sm.on_frame(pkt, start + timedelta(milliseconds=25 * i))


def _close_via_grace(sm: SessionManager, make_packet, *, start: datetime):
    """Drain the close grace by sending pause packets back-to-back from
    `start` until SESSION_ENDED fires. Returns the closing decision."""
    pause_pkt = _decode(
        make_packet(IsRaceOn=0, RacePosition=0, CurrentLap=0.0, CurrentRaceTime=5.0)
    )
    for i in range(SessionManager.CLOSE_GRACE_TICKS + 1):
        d = sm.on_frame(pause_pkt, start + timedelta(milliseconds=33 * i))
        if d.event == BoundaryEvent.SESSION_ENDED:
            return d
    raise AssertionError("session never closed via grace")


def test_tiny_lapless_session_is_discarded_on_close_grace(make_packet) -> None:
    """200-frame lapless session that exits the event must be DELETED
    on close (discarded_session_id set, closed_session unset)."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

    _drive_lapless_for(sm, make_packet, in_event_frames=200, start=t0)
    assert sm.current is not None
    assert sm.current.frame_count == 200
    discarded_id = sm.current.id

    # Pause packets follow with no silence gap, so the only close path
    # available is the not_in_event grace.
    pause_start = sm.last_frame_at + timedelta(milliseconds=33)
    closure = _close_via_grace(sm, make_packet, start=pause_start)

    assert closure.discarded_session_id == discarded_id
    assert closure.closed_session is None
    assert closure.closed_final_lap is None
    assert sm.current is None


def test_long_lapless_sprint_is_kept_on_close_grace(make_packet) -> None:
    """5000-frame lapless run (sprint / point-to-point) clears the
    TINY_SESSION_MAX_FRAMES bar — must finalize, not discard."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

    _drive_lapless_for(sm, make_packet, in_event_frames=5000, start=t0)
    assert sm.current is not None
    assert sm.current.frame_count == 5000
    kept_id = sm.current.id

    pause_start = sm.last_frame_at + timedelta(milliseconds=33)
    closure = _close_via_grace(sm, make_packet, start=pause_start)

    assert closure.discarded_session_id is None
    assert closure.closed_session is not None
    assert closure.closed_session.id == kept_id
    assert closure.closed_session.closed_reason == SessionCloseReason.NOT_IN_EVENT


def test_frame_count_increments_per_packet(make_packet) -> None:
    """frame_count is the discriminator the discard check reads; ensure
    every appended packet bumps it exactly once."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    pkt = _decode(make_packet(IsRaceOn=1, RacePosition=3, CurrentLap=5.0, CurrentRaceTime=5.0))
    for i in range(50):
        sm.on_frame(pkt, t0 + timedelta(milliseconds=25 * i))
    assert sm.current is not None
    assert sm.current.frame_count == 50


def test_free_roam_session_stays_open_with_is_race_on_only(make_packet) -> None:
    """Free-roam streams (is_race_on=1 with RacePosition=0 and CurrentLap=0)
    must keep the session open indefinitely — previously raw_in_event also
    required position>0 or lap>0, so free-roam sessions tripped the grace
    timer after 2.5s and got discarded along with their frames."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    pkt = _decode(
        make_packet(
            IsRaceOn=1,
            RacePosition=0,
            CurrentLap=0.0,
            CurrentRaceTime=0.0,
            LapNumber=0,
            BestLap=0.0,
        )
    )
    # Drive far past the grace window (150 ticks) and the tiny-session
    # threshold (400 frames). Pre-fix, the session would have been
    # discarded somewhere after frame ~150.
    for i in range(800):
        d = sm.on_frame(pkt, t0 + timedelta(milliseconds=25 * i))
        assert d.event != BoundaryEvent.SESSION_ENDED, (
            f"free-roam session closed prematurely at frame {i}"
        )
    assert sm.current is not None
    assert sm.current.frame_count == 800
