"""Per-lap timing, final-lap finalization, and rewind-aware session stitching.

Tests are pure-Python (no DB, no I/O) — they drive the
SessionManager._note_tick / finalize_final_lap / note_close / check_reopen
primitives directly.
"""

from __future__ import annotations

from fh6.application.services.session_manager import SessionManager
from fh6.domain.value_objects.ids import SessionId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sm() -> SessionManager:
    """Fresh SessionManager with a default session already begun."""
    sm = SessionManager(silence_seconds=60.0)
    sm.begin_new_session()
    return sm


# ---------------------------------------------------------------------------
# Basic lap completion (Rust: lap_completes_on_current_lap_reset_while_racing)
# ---------------------------------------------------------------------------


def test_lap_completes_on_current_lap_reset() -> None:
    sm = _sm()

    assert sm._note_tick(True, 5.0, 5.0) is None
    assert sm._note_tick(True, 57.2, 57.2) is None  # peak builds

    l1 = sm._note_tick(True, 0.43, 57.4)  # line crossed
    assert l1 is not None
    assert l1.lap_number == 0
    assert abs(l1.lap_time_s - 57.2) < 0.001

    assert sm._note_tick(True, 30.0, 87.0) is None
    assert sm._note_tick(True, 55.2, 112.4) is None

    l2 = sm._note_tick(True, 0.5, 112.6)
    assert l2 is not None
    assert l2.lap_number == 1
    assert abs(l2.lap_time_s - 55.2) < 0.001


# ---------------------------------------------------------------------------
# Short/invalid laps are not recorded
# ---------------------------------------------------------------------------


def test_no_lap_below_min_lap_secs() -> None:
    sm = _sm()
    # Never exceed MIN_LAP_SECS
    sm._note_tick(True, 5.0, 5.0)
    sm._note_tick(True, 15.0, 15.0)
    result = sm._note_tick(True, 0.4, 15.2)
    assert result is None
    assert sm.laps_recorded == 0


# ---------------------------------------------------------------------------
# Rewind scrub (Rust: rewind_scrub_does_not_record_a_short_lap)
# ---------------------------------------------------------------------------


def test_rewind_scrub_does_not_record_a_short_lap() -> None:
    sm = _sm()
    sm._note_tick(True, 20.0, 20.0)
    sm._note_tick(True, 45.0, 45.0)  # peak = 45

    # Rewind: is_race_on drops, race clock jumps backward.
    sm._note_tick(False, 0.0, 0.0)
    # Current_lap scrubs past 0 — must NOT record a lap.
    result = sm._note_tick(True, 0.5, 30.0)
    assert result is None, "scrub must not be a lap"
    assert sm.laps_recorded == 0

    # Re-drive the lap over many ticks (guard expires in ~60 ticks ≈ 1 s).
    t = 30.0
    for i in range(1, 81):
        cl = 0.5 + i * 0.67  # climbs to ~54 over 80 ticks
        t += 0.67
        assert sm._note_tick(True, cl, t) is None

    lap = sm._note_tick(True, 0.4, t + 0.2)
    assert lap is not None
    assert lap.lap_number == 0
    # Peak reached ~54 — full lap, not the pre-rewind 45.
    assert 53.0 < lap.lap_time_s < 55.0, f"got {lap.lap_time_s}"


# ---------------------------------------------------------------------------
# Backward race clock arms the guard (gap > 0.25 s)
# ---------------------------------------------------------------------------


def test_backward_race_time_arms_rewind_guard() -> None:
    sm = _sm()
    sm._note_tick(True, 30.0, 100.0)
    sm._note_tick(True, 25.0, 100.0)  # current_lap drops but race_time OK
    # Race time jumps backward by > 0.25 s → guard armed then decremented
    # once in the same tick (is_race_on=True).
    sm._note_tick(True, 24.0, 98.0)  # 98 + 0.25 < 100 → guard
    assert sm._rewind_guard == SessionManager.REWIND_GUARD_TICKS - 1


def test_is_race_on_false_arms_guard_and_does_not_decrement() -> None:
    sm = _sm()
    sm._note_tick(True, 30.0, 100.0)
    # is_race_on=False arms guard; decrement gated on is_race_on → stays at max.
    sm._note_tick(False, 0.0, 0.0)
    assert sm._rewind_guard == SessionManager.REWIND_GUARD_TICKS


def test_backward_race_time_within_tolerance_does_not_arm() -> None:
    sm = _sm()
    sm._note_tick(True, 30.0, 100.0)
    # 100 - 0.2 = 99.8; 99.8 + 0.25 = 100.05 > 100 → no guard
    sm._note_tick(True, 25.0, 99.8)
    assert sm._rewind_guard == 0


# ---------------------------------------------------------------------------
# Final-lap finalization (Rust: final_race_lap_finalized_on_close)
# ---------------------------------------------------------------------------


def test_final_race_lap_finalized_on_close() -> None:
    sm = _sm()
    # Lap 0 completes.
    sm._note_tick(True, 57.2, 57.2)
    sm._note_tick(True, 0.4, 57.4)
    # Lap 1 completes.
    sm._note_tick(True, 55.2, 112.6)
    sm._note_tick(True, 0.4, 112.8)
    # Lap 2 in progress, race ends (is_race_on=0, no reset).
    sm._note_tick(True, 40.0, 152.0)
    sm._note_tick(True, 53.6, 165.6)
    sm._note_tick(False, 0.0, 0.0)

    final = sm.finalize_final_lap()
    assert final is not None
    assert abs(final.lap_time_s - 53.6) < 0.001
    assert final.lap_number == 2  # third lap, 0-indexed


# ---------------------------------------------------------------------------
# Post-race cool-down is NOT finalized (Rust: post_race_cooldown_is_not_finalized)
# ---------------------------------------------------------------------------


def test_post_race_cooldown_not_finalized() -> None:
    sm = _sm()
    # Lap completes via line crossing.
    sm._note_tick(True, 53.0, 53.0)
    l = sm._note_tick(True, 0.4, 53.2)
    assert l is not None and abs(l.lap_time_s - 53.0) < 0.001

    # Cool-down: short in-progress arc after the finish.
    sm._note_tick(True, 1.5, 54.5)
    sm._note_tick(True, 3.8, 56.8)

    # 3.8 s peak < max(10 s, 0.5 × 53 = 26.5 s) floor → not finalized.
    assert sm.finalize_final_lap() is None
    assert abs(sm.best_lap - 53.0) < 0.001


# ---------------------------------------------------------------------------
# Rewind stitch (Rust: rewind_stitch_preserves_lap_state_across_close_reopen)
# ---------------------------------------------------------------------------


def test_rewind_stitch_preserves_lap_state() -> None:
    sm = _sm()

    # Lap 0 completes.
    sm._note_tick(True, 50.0, 50.0)
    l0 = sm._note_tick(True, 0.4, 50.2)
    assert l0 is not None and l0.lap_number == 0

    # Mid lap 1, rewind closes session — provisional final captured.
    sm._note_tick(True, 30.0, 80.0)
    prov = sm.finalize_final_lap()
    assert prov is not None and prov.lap_number == 1
    # Lap state survives: laps_recorded is still 1, NOT reset.
    assert sm.laps_recorded == 1

    # Reopen same session (lap state preserved; index unchanged).
    sm._note_tick(True, 55.0, 105.0)
    l1 = sm._note_tick(True, 0.5, 105.2)
    assert l1 is not None
    assert l1.lap_number == 1  # same index → DB upsert overwrites
    assert abs(l1.lap_time_s - 55.0) < 0.001
    assert sm.laps_recorded == 2


# ---------------------------------------------------------------------------
# note_close / check_reopen (Rust: rewind_reopens_session_within_window, etc.)
# ---------------------------------------------------------------------------


def _prime_session_id(sm: SessionManager, sid_str: str) -> None:
    """Inject a session id into the manager via a minimal fake session."""
    from datetime import UTC, datetime

    from fh6.domain.entities.session import Session, SessionType
    from fh6.domain.value_objects.ids import CarId

    sm._current = Session(  # type: ignore[attr-defined]
        id=SessionId(sid_str),
        car_id=CarId("car_0_0"),
        type=SessionType.FREE_ROAM,
        started_at=datetime(2026, 5, 18, 0, 0, tzinfo=UTC),
    )


def test_check_reopen_within_window() -> None:
    sm = _sm()
    _prime_session_id(sm, "s_42")
    sm._note_tick(True, 30.0, 90.0)  # peak_race_time = 90
    sm.note_close(wall_s=1_000.0)
    sm._current = None

    # New stream at 60 s — backward, within 30 s wall gap.
    result = sm.check_reopen(new_race_time=60.0, wall_s=1_005.0)
    assert result == SessionId("s_42")


def test_no_reopen_after_long_gap() -> None:
    sm = _sm()
    _prime_session_id(sm, "s_7")
    sm._note_tick(True, 30.0, 90.0)
    sm.note_close(wall_s=0.0)
    sm._current = None

    # 61 s gap — beyond REWIND_WINDOW_S.
    result = sm.check_reopen(new_race_time=60.0, wall_s=61.0)
    assert result is None


def test_no_reopen_for_fresh_start() -> None:
    sm = _sm()
    _prime_session_id(sm, "s_5")
    sm._note_tick(True, 30.0, 120.0)
    sm.note_close(wall_s=0.0)
    sm._current = None

    # Race time near zero — looks like a new race, not a rewind.
    result = sm.check_reopen(new_race_time=1.0, wall_s=2.0)
    assert result is None


def test_no_reopen_when_time_advances() -> None:
    sm = _sm()
    _prime_session_id(sm, "s_3")
    sm._note_tick(True, 20.0, 45.0)
    sm.note_close(wall_s=0.0)
    sm._current = None

    # Race time went forward — not a rewind.
    result = sm.check_reopen(new_race_time=50.0, wall_s=5.0)
    assert result is None


def test_rewind_during_grace_window_uses_peak_not_scrubbed() -> None:
    """Peak race time is tracked across scrubbing; check_reopen compares
    against peak, so a scrub-then-reopen still works."""
    sm = _sm()
    _prime_session_id(sm, "s_11")
    sm._note_tick(True, 20.0, 90.0)  # peak = 90
    # Scrub backward mid-close grace.
    sm._note_tick(True, 5.0, 8.0)  # race_time guards, peak stays 90
    sm.note_close(wall_s=1.0)
    sm._current = None

    # New stream at rewound position — below peak → reopen.
    result = sm.check_reopen(new_race_time=9.0, wall_s=2.0)
    assert result == SessionId("s_11")


def test_check_reopen_consumes_closed_id() -> None:
    sm = _sm()
    _prime_session_id(sm, "s_9")
    sm._note_tick(True, 20.0, 80.0)
    sm.note_close(wall_s=0.0)
    sm._current = None

    assert sm.check_reopen(40.0, 1.0) is not None  # first call succeeds
    assert sm.check_reopen(40.0, 2.0) is None  # consumed


# ---------------------------------------------------------------------------
# begin_new_session resets everything
# ---------------------------------------------------------------------------


def test_begin_new_session_clears_lap_state() -> None:
    sm = _sm()
    sm._note_tick(True, 50.0, 50.0)
    sm._note_tick(True, 0.4, 50.2)  # records lap 0

    sm.begin_new_session()

    assert sm.laps_recorded == 0
    assert sm.cur_lap_peak == 0.0
    assert sm.best_lap == float("inf")
    assert sm._rewind_guard == 0
    assert sm._prev_current_lap == 0.0


# ---------------------------------------------------------------------------
# Integration: on_frame carries completed_lap and closed_final_lap
# ---------------------------------------------------------------------------


def test_on_frame_appended_carries_completed_lap(make_packet) -> None:
    from datetime import UTC, datetime, timedelta

    from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder

    dec = FH6PacketDecoder()
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

    # Seed session, build up a lap. Note: field name is CurrentLap (not CurrentLapTime).
    sm.on_frame(dec.decode(make_packet(IsRaceOn=1, CurrentLap=5.0, CurrentRaceTime=5.0)), t0)
    sm.on_frame(
        dec.decode(make_packet(IsRaceOn=1, CurrentLap=57.0, CurrentRaceTime=57.0)),
        t0 + timedelta(seconds=52),
    )
    # Line crossing — CurrentLap drops near 0.
    decision = sm.on_frame(
        dec.decode(make_packet(IsRaceOn=1, CurrentLap=0.4, CurrentRaceTime=57.4)),
        t0 + timedelta(seconds=52.4),
    )
    assert decision.completed_lap is not None
    assert decision.completed_lap.lap_number == 0
    assert abs(decision.completed_lap.lap_time_s - 57.0) < 0.5


def test_on_frame_silence_split_carries_closed_final_lap(make_packet) -> None:
    from datetime import UTC, datetime, timedelta

    from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder

    dec = FH6PacketDecoder()
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)

    # Open session, accumulate a meaningful lap-in-progress (> 20 s peak).
    sm.on_frame(dec.decode(make_packet(IsRaceOn=1, CurrentLap=5.0, CurrentRaceTime=5.0)), t0)
    sm.on_frame(
        dec.decode(make_packet(IsRaceOn=1, CurrentLap=45.0, CurrentRaceTime=45.0)),
        t0 + timedelta(seconds=40),
    )

    # Silence split with best_lap still inf → floor = 10 s; peak 45 ≥ 10.
    decision = sm.on_frame(
        dec.decode(make_packet(IsRaceOn=1, CurrentLap=46.0, CurrentRaceTime=46.0)),
        t0 + timedelta(seconds=120),  # > 60 s silence
    )
    assert decision.closed_session is not None
    assert decision.closed_final_lap is not None
    assert decision.closed_final_lap.lap_time_s >= 10.0
