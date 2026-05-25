"""SessionManager: enforces session-boundary rules and per-lap timing.

A session is one contiguous packet stream for one car (constitution
Principle V). Boundaries:
- car-identity change → split (FR-006/FR-007)
- silence > sessionSilenceSeconds → split (FR-007)
- restart resume → Clarification Q1

The transient stream-paused state (silence ≥ 250 ms or 3× cadence)
is a UI-level signal emitted by StateEmitter; it does NOT close a
session. Only `sessionSilenceSeconds` (default 60 s) closes one.

Lap timing follows the Forza reference (session.rs note_tick):
- A lap completes when currentLapS drops to < 1.0 after peaking
  above MIN_LAP_SECS (20 s) while racing and the rewind guard is 0.
- The rewind guard (60 ticks ≈ 1 s at 60 Hz) arms when is_race_on
  drops or race_time jumps backward by > 0.25 s, preventing false
  lap records during scrubbing.
- finalize_final_lap() captures the in-progress lap on session close;
  the DB upsert on (session_id, lap_number) makes this idempotent
  across rewind close/reopen cycles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from fh6.domain.entities.car import Car
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.completed_lap import CompletedLap
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.cars import ordinal_lookup
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)

AdoptListener = Callable[["Session", "datetime"], None]
SessionStartedListener = Callable[["SessionId"], None]


class BoundaryEvent(StrEnum):
    APPENDED = "appended"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"


@dataclass(slots=True)
class BoundaryDecision:
    event: BoundaryEvent
    closed_session: Session | None = None
    opened_session: Session | None = None
    current_session: Session | None = None
    # Normal lap completion for the current session (from _note_tick).
    completed_lap: CompletedLap | None = None
    # Final lap of a session that just closed (from finalize_final_lap).
    closed_final_lap: CompletedLap | None = None
    # Tiny lapless fragment to delete instead of finalize. Mutually
    # exclusive with closed_session — callers route on whichever is set.
    discarded_session_id: SessionId | None = None


def _derive_car_id(raw: FrameRaw) -> CarId:
    """Stable per-car identity. Conservative MVP heuristic:
    `car_<carOrdinal>_<carPI>`. Tune-hash extension is future work.
    """
    ordinal = raw.world.get("carOrdinal", 0)
    pi = raw.world.get("performanceIndex", 0)
    return CarId(f"car_{ordinal}_{pi}")


def build_car_from_raw(raw: FrameRaw, at: datetime) -> Car:
    """Minimal Car row derivable from a single decoded packet. Used to
    upsert the `cars` row before frames/sessions referencing it land —
    the frames→cars and sessions→cars FKs require it to exist first.

    The carOrdinal → display name comes from the bundled community
    table (``infrastructure/cars/ordinal_lookup``). The DB row is the
    authoritative copy once written; the lookup only seeds new rows.
    """
    ordinal = int(raw.world.get("carOrdinal", 0))
    pi = int(raw.world.get("performanceIndex", 0))
    car_class = str(raw.world.get("carClass", "?"))
    drivetrain = str(raw.drivetrain.get("type", "AWD"))
    car_group = int(raw.world.get("carGroup", 0))
    name = ordinal_lookup.lookup_car_name(ordinal)
    display_name = name or f"Car #{ordinal}"
    # Strip the leading year ("2005 Ferrari FXX" → "Ferrari FXX"); the
    # year reads as noise in tight UI chrome. Falls back to the ordinal
    # when the table doesn't know this car.
    short_name = name.split(" ", 1)[-1] if name else f"#{ordinal}"
    return Car(
        id=_derive_car_id(raw),
        display_name=display_name,
        short_name=short_name,
        car_ordinal=ordinal,
        car_class=car_class,
        performance_index=pi,
        drivetrain=drivetrain,
        car_group=car_group,
        last_seen_at=at,
    )


def _session_id_for(car_id: CarId, at: datetime) -> SessionId:
    stamp = at.strftime("%Y-%m-%dT%H-%M-%S")
    return SessionId(f"s_{stamp}_{car_id}")


def _session_type_from(raw: FrameRaw) -> SessionType:
    """Infer session type from packet contents.

    Canonical race discriminator is a three-condition AND:
        is_race_on AND raceTimeS > 0 AND race.position > 0
    `is_race_on` alone only means the game is actively streaming (not
    paused / not in menus). `raceTimeS` and `position` can each linger
    non-zero in stale frames after a return to free-roam, so neither
    alone is sufficient. In free-roam, `position` is always 0; the game
    only assigns a finishing-order position inside an actual race. The
    same combination is used by the Forza reference implementation
    (`Forza/server/enricher.js:89`).

    Time Trial sits between race and free-roam: the lap clock runs
    (`currentLapS > 0`) but `position` stays 0 because there is no
    finishing-order field — only the player's own laps are timed.
    """
    if not raw.is_race_on:
        return SessionType.FREE_ROAM
    race_time_s = float(raw.race.get("raceTimeS", 0.0) or 0.0)
    position = int(raw.race.get("position", 0) or 0)
    current_lap_s = float(raw.race.get("currentLapS", 0.0) or 0.0)
    if race_time_s > 0.0 and position > 0:
        return SessionType.RACE
    if current_lap_s > 0.0 and position == 0:
        return SessionType.TIME_TRIAL
    return SessionType.FREE_ROAM


def _apply_aggregates(session: Session, raw: FrameRaw, dt_s: float = 0.0) -> None:
    """Fold one packet's measurements into the session row in place.

    The Session entity carries the running per-session rollups
    (`distance_m`, `top_speed_mps`, `lap_count`, `best_lap_s`). Each
    field is monotonic within a session: distance/top-speed/lap-count
    take a max, best-lap takes a min over positive values. Type is
    upgraded free_roam → race when the race timer starts; we never
    downgrade race → free_roam mid-session (post-race results screens
    still report ``raceTimeS == 0`` while the same session continues).

    Distance handling (spec Gotcha #14): the game's `distanceTraveled`
    resets on session change, and in some free-roam states it stays at
    0 even while the car is moving. Prefer the game-reported odometer
    whenever it advances past our running max, but fall back to
    integrating ``speed_mps * dt`` so `distance_m` still reflects
    actual travel in those zeroed states. `dt_s` is the elapsed time
    since the previous frame in the same session (0 on session open).

    Lap handling (spec Gotcha #15): `LapNumber` is 0-indexed and only
    increments at start/finish crossings, so `lap_count` is the count
    of crossings (= laps completed). The monotonic-max here is
    equivalent to a transition detector because LapNumber never goes
    backwards within a session.
    """
    speed = float(raw.motion.get("speed_mps", 0.0) or 0.0)
    session.top_speed_mps = max(session.top_speed_mps, speed)

    reported_distance = float(raw.world.get("distanceTraveled", 0.0) or 0.0)
    if reported_distance > session.distance_m:
        session.distance_m = reported_distance
    elif dt_s > 0.0 and speed > 0.0:
        session.distance_m += speed * dt_s

    lap = int(raw.race.get("lap", 0) or 0)
    session.lap_count = max(session.lap_count, lap)

    best_lap = raw.race.get("bestLapS")
    if best_lap is not None:
        best_lap_f = float(best_lap)
        if best_lap_f > 0.0 and (session.best_lap_s is None or best_lap_f < session.best_lap_s):
            session.best_lap_s = best_lap_f

    if session.type == SessionType.FREE_ROAM:
        inferred = _session_type_from(raw)
        if inferred in (SessionType.RACE, SessionType.TIME_TRIAL):
            session.type = inferred

    session.frame_count += 1


class SessionManager:
    # Minimum currentLapS that must have been reached for a lap to count.
    MIN_LAP_SECS: float = 20.0
    # Number of ticks the rewind guard stays armed after a backward jump.
    REWIND_GUARD_TICKS: int = 60
    # Wall-clock window (seconds) within which a session can be reopened
    # after a rewind closes it.
    REWIND_WINDOW_S: float = 30.0
    # Minimum raceTimeS in a new packet for it to be considered a rewind
    # (rather than a fresh race start).
    REWIND_MIN_RACE_TIME_S: float = 5.0
    # Packets of !raw_in_event tolerated before treating the session as
    # "not in event" (pause menu, lap-result screen, packet stutter).
    # ~5 s @ 30 Hz.
    CLOSE_GRACE_TICKS: int = 150
    # A lapless session with fewer frames than this on close is treated
    # as a menu fragment / aborted-race scrap and deleted instead of
    # finalized. Long lapless sprints (point-to-point) clear the bar and
    # are kept. ~10 s @ 40 Hz.
    TINY_SESSION_MAX_FRAMES: int = 400

    def __init__(self, *, silence_seconds: float = 60.0) -> None:
        if silence_seconds <= 0:
            raise ValueError("silence_seconds must be > 0")
        self._silence = timedelta(seconds=silence_seconds)
        self._current: Session | None = None
        self._last_frame_at: datetime | None = None

        # Lap timing state — reset by begin_new_session().
        self._prev_current_lap: float = 0.0
        self._cur_lap_peak: float = 0.0
        self._prev_race_time: float = 0.0
        self._rewind_guard: int = 0
        self._laps_recorded: int = 0
        self._best_lap: float = float("inf")
        self._peak_race_time: float = 0.0

        # Event-exit grace counter. Resets only when raw_in_event=True;
        # intentionally NOT reset by begin_new_session so a brand-new
        # session opened during the middle of a menu burst closes again
        # at the next packet rather than re-spending the full 5 s grace.
        self._close_pending: int = 0

        # Rewind-stash — set by note_close(), consumed by check_reopen().
        self._closed_id: SessionId | None = None
        self._closed_wall_s: float | None = None
        self._peak_race_time_at_close: float = 0.0

        self._adopt_listeners: list[AdoptListener] = []
        self._session_started_listeners: list[SessionStartedListener] = []

    @property
    def silence_threshold(self) -> timedelta:
        return self._silence

    @property
    def current(self) -> Session | None:
        return self._current

    @property
    def last_frame_at(self) -> datetime | None:
        return self._last_frame_at

    # ------------------------------------------------------------------
    # Lap state accessors (tests + finalization logic).
    # ------------------------------------------------------------------

    @property
    def laps_recorded(self) -> int:
        return self._laps_recorded

    @property
    def cur_lap_peak(self) -> float:
        return self._cur_lap_peak

    @property
    def best_lap(self) -> float:
        return self._best_lap

    # ------------------------------------------------------------------
    # Lap-timing primitives.
    # ------------------------------------------------------------------

    def begin_new_session(self) -> None:
        """Reset all lap-timing state for a genuinely new session.

        Called whenever we open a new session that is NOT a rewind
        reopen. A reopen preserves lap state so that the lap index and
        peak survive the close/reopen cycle (Rust test
        rewind_stitch_preserves_lap_state_across_close_reopen).
        """
        self._prev_current_lap = 0.0
        self._cur_lap_peak = 0.0
        self._prev_race_time = 0.0
        self._rewind_guard = 0
        self._laps_recorded = 0
        self._best_lap = float("inf")
        self._peak_race_time = 0.0

    def _note_tick(
        self, is_race_on: bool, current_lap: float, race_time: float
    ) -> CompletedLap | None:
        """Update lap state for one packet; return a CompletedLap when
        currentLapS resets after a valid lap (line crossed).

        Rewind guard: arms for REWIND_GUARD_TICKS ticks whenever
        is_race_on drops OR race_time jumps backward by > 0.25 s. While
        armed, no lap completion is recorded, preventing false laps
        during scrub/rewind.

        The lap time is the PEAK currentLapS reached during that lap
        cycle — the game does not expose a discrete lap-time field, so
        the highest observed value (just before the reset) is the true
        elapsed time. This matches the Forza reference implementation
        (session.rs note_tick).
        """
        self._cur_lap_peak = max(self._cur_lap_peak, current_lap)

        # Arm rewind guard on pause or backward race-clock jump.
        if not is_race_on or (race_time > 0.0 and race_time + 0.25 < self._prev_race_time):
            self._rewind_guard = self.REWIND_GUARD_TICKS

        if race_time > 0.0:
            self._prev_race_time = race_time
            self._peak_race_time = max(self._peak_race_time, race_time)

        completed: CompletedLap | None = None
        if (
            is_race_on
            and self._rewind_guard == 0
            and self._prev_current_lap > self.MIN_LAP_SECS
            and current_lap < 1.0
        ):
            t = self._cur_lap_peak
            self._cur_lap_peak = current_lap  # next lap starts at current value
            idx = self._laps_recorded
            self._laps_recorded += 1
            self._best_lap = min(self._best_lap, t)
            completed = CompletedLap(lap_number=idx, lap_time_s=t)

        if self._rewind_guard > 0 and is_race_on:
            self._rewind_guard -= 1

        self._prev_current_lap = current_lap
        return completed

    def finalize_final_lap(self) -> CompletedLap | None:
        """Capture the in-progress lap when the session closes.

        The final lap of a race ends with the race ending rather than a
        start/finish crossing, so currentLapS never resets. We record it
        here if the peak is at least floor = max(10 s, 0.5 × best_lap)
        — this rejects post-race cool-down rolls.

        Non-destructive: does NOT advance laps_recorded or clear the
        peak, so a rewind close/reopen can re-emit the same lap_number
        and the DB upsert overwrites the provisional value.
        """
        t = self._cur_lap_peak
        floor = 10.0 if self._best_lap == float("inf") else max(10.0, 0.5 * self._best_lap)
        if t >= floor:
            self._best_lap = min(self._best_lap, t)
            return CompletedLap(lap_number=self._laps_recorded, lap_time_s=t)
        return None

    # ------------------------------------------------------------------
    # Rewind-stitch primitives.
    # ------------------------------------------------------------------

    def note_close(self, wall_s: float) -> None:
        """Stash state needed to detect a subsequent rewind reopen.

        Called internally whenever a session closes (any reason). The
        stash is consumed by the FIRST call to check_reopen so it cannot
        fire twice.
        """
        self._closed_id = self._current.id if self._current is not None else None
        self._closed_wall_s = wall_s
        self._peak_race_time_at_close = self._peak_race_time

    def check_reopen(self, new_race_time: float, wall_s: float) -> SessionId | None:
        """Return the session id to reopen when new_race_time went
        backward within REWIND_WINDOW_S of the last close.

        Conditions (translates Rust check_reopen):
        - closed_id is stashed (a session was recently closed)
        - wall gap since close < REWIND_WINDOW_S
        - new_race_time > REWIND_MIN_RACE_TIME_S (not a fresh start)
        - new_race_time < peak_race_time_at_close (time went backward)

        Consumes the stash on success so it cannot fire twice.
        """
        if self._closed_id is None or self._closed_wall_s is None:
            return None
        gap_s = wall_s - self._closed_wall_s
        if (
            0.0 <= gap_s < self.REWIND_WINDOW_S
            and new_race_time > self.REWIND_MIN_RACE_TIME_S
            and new_race_time < self._peak_race_time_at_close
        ):
            result = self._closed_id
            self._closed_id = None  # consume
            return result
        return None

    def add_adopt_listener(self, listener: AdoptListener) -> None:
        """Register a callback invoked at the END of every successful
        `adopt()` call. Used by the rewind detector to re-arm its pause
        flag when a session is reopened.

        Listeners fire in registration order. Exceptions in one listener
        are logged and swallowed so the rest still fire and `adopt()`
        itself never raises.
        """
        self._adopt_listeners.append(listener)

    def add_session_started_listener(self, listener: SessionStartedListener) -> None:
        """Register a callback invoked whenever a brand-new session opens.

        The callback receives the new ``SessionId``. Fires in registration
        order; exceptions in one listener are logged and swallowed so the
        rest still fire and ``on_frame()`` itself never raises.

        Used by ``ShiftPredictor.on_session_started`` to evict the
        previous session's ``_assist_stats`` entry and prevent unbounded
        memory growth across long-running processes.
        """
        self._session_started_listeners.append(listener)

    def _fire_session_started(self, session_id: SessionId) -> None:
        """Internal: invoke all registered session-started listeners."""
        for listener in self._session_started_listeners:
            try:
                listener(session_id)
            except Exception:
                log.exception("session_started_listener_error")

    # ------------------------------------------------------------------
    # Core state machine.
    # ------------------------------------------------------------------

    def on_frame(self, raw: FrameRaw, at: datetime) -> BoundaryDecision:
        car_id = _derive_car_id(raw)
        is_race_on: bool = bool(raw.is_race_on)
        current_lap: float = float(raw.race.get("currentLapS", 0.0) or 0.0)
        race_time: float = float(raw.race.get("raceTimeS", 0.0) or 0.0)
        int(raw.race.get("position", 0) or 0)

        # Event-exit grace: pause menus, lap-result screens, and brief
        # stutters all stop is_race_on without truly ending the session.
        # Reset close_pending on every "real" event packet; otherwise
        # increment and only treat the session as out-of-event once
        # close_pending has reached CLOSE_GRACE_TICKS.
        # is_race_on is the authoritative "actively playing" flag — it goes
        # 0 in menus, pause screens, and lap-result overlays. Previously this
        # also required race_position > 0 or current_lap > 0.0, but FH6
        # free-roam emits is_race_on=1 with both at 0 indefinitely, so the
        # grace timer was tripping after 2.5s and discarding the session
        # (lap_count==0 + frame_count<400 → DISCARD → cascade-delete frames).
        # Free-roam needs is_race_on alone; menus/pauses still close via the
        # grace path because is_race_on really does go 0 then.
        raw_in_event = is_race_on
        if raw_in_event:
            self._close_pending = 0
        else:
            self._close_pending += 1

        # Not-in-event close: existing session has been out of event
        # for the full grace window. Close it (no new session opens —
        # we wait for a real in-event packet to start the next one).
        # This is the only close path that can DISCARD: menu flicker
        # / aborted-race fragments leave is_race_on=0 long enough to
        # trip the grace timer, and only those should evaporate.
        if self._current is not None and self._close_pending >= self.CLOSE_GRACE_TICKS:
            final_lap = self.finalize_final_lap()
            closed = self._current
            self.note_close(at.timestamp())
            if (
                self._laps_recorded == 0
                and final_lap is None
                and closed.frame_count < self.TINY_SESSION_MAX_FRAMES
            ):
                self._current = None
                return BoundaryDecision(
                    event=BoundaryEvent.SESSION_ENDED,
                    discarded_session_id=closed.id,
                )
            closed.finalize(at, SessionCloseReason.NOT_IN_EVENT)
            self._current = None
            return BoundaryDecision(
                event=BoundaryEvent.SESSION_ENDED,
                closed_session=closed,
                closed_final_lap=final_lap,
            )

        # No active session → open one. Lap state is already fresh (either
        # __init__ or begin_new_session was called before this path, or we
        # just adopted a session for a rewind in which case lap state must
        # NOT be reset — that is handled externally by IngestFrame before
        # calling on_frame).
        if self._current is None:
            self.begin_new_session()
            new = Session(
                id=_session_id_for(car_id, at),
                car_id=car_id,
                type=_session_type_from(raw),
                started_at=at,
            )
            _apply_aggregates(new, raw)
            self._current = new
            self._last_frame_at = at
            tick_lap = self._note_tick(is_race_on, current_lap, race_time)
            self._fire_session_started(new.id)
            return BoundaryDecision(
                event=BoundaryEvent.SESSION_STARTED,
                opened_session=new,
                current_session=new,
                completed_lap=tick_lap,
            )

        # Car change → close + open.
        if car_id != self._current.car_id:
            final_lap = self.finalize_final_lap()
            closed = self._current
            self.note_close(at.timestamp())
            closed.finalize(at, SessionCloseReason.CAR_CHANGE)
            self.begin_new_session()
            new = Session(
                id=_session_id_for(car_id, at),
                car_id=car_id,
                type=_session_type_from(raw),
                started_at=at,
            )
            _apply_aggregates(new, raw)
            self._current = new
            self._last_frame_at = at
            tick_lap = self._note_tick(is_race_on, current_lap, race_time)
            self._fire_session_started(new.id)
            return BoundaryDecision(
                event=BoundaryEvent.SESSION_STARTED,
                closed_session=closed,
                opened_session=new,
                current_session=new,
                completed_lap=tick_lap,
                closed_final_lap=final_lap,
            )

        # Silence split → close + open.
        if self._last_frame_at is not None and (at - self._last_frame_at) > self._silence:
            final_lap = self.finalize_final_lap()
            closed = self._current
            self.note_close(self._last_frame_at.timestamp())
            closed.finalize(self._last_frame_at, SessionCloseReason.SILENCE)
            self.begin_new_session()
            new = Session(
                id=_session_id_for(car_id, at),
                car_id=car_id,
                type=_session_type_from(raw),
                started_at=at,
            )
            _apply_aggregates(new, raw)
            self._current = new
            self._last_frame_at = at
            tick_lap = self._note_tick(is_race_on, current_lap, race_time)
            self._fire_session_started(new.id)
            return BoundaryDecision(
                event=BoundaryEvent.SESSION_STARTED,
                closed_session=closed,
                opened_session=new,
                current_session=new,
                completed_lap=tick_lap,
                closed_final_lap=final_lap,
            )

        # Append to current: fold the packet's measurements into the
        # in-flight session row. dt comes from the gap to the previous
        # frame in this session and feeds the speed*dt fallback for
        # distance (Gotcha #14).
        dt_s = (
            (at - self._last_frame_at).total_seconds()
            if self._last_frame_at is not None and at > self._last_frame_at
            else 0.0
        )
        _apply_aggregates(self._current, raw, dt_s=dt_s)
        self._last_frame_at = at
        tick_lap = self._note_tick(is_race_on, current_lap, race_time)
        return BoundaryDecision(
            event=BoundaryEvent.APPENDED,
            current_session=self._current,
            completed_lap=tick_lap,
        )

    def adopt(self, session: Session, last_frame_at: datetime) -> None:
        """Restore a session into the manager (Q1 resume or rewind reopen).

        For rewind reopen the caller must unfinalize the session
        (ended_at = None) BEFORE calling adopt, and pass the current
        packet timestamp as last_frame_at so on_frame's silence check
        does not immediately re-split the session.

        Lap state is intentionally NOT reset here — a rewind reopen
        must preserve the lap index and peak so subsequent laps are
        numbered correctly and the DB upsert can overwrite the
        provisional final-lap time.
        """
        if session.ended_at is not None:
            raise ValueError("cannot adopt a closed session")
        self._current = session
        self._last_frame_at = last_frame_at
        for listener in self._adopt_listeners:
            try:
                listener(session, last_frame_at)
            except Exception:
                log.exception("adopt_listener_error")

    def force_finalize(self, at: datetime, reason: SessionCloseReason) -> Session | None:
        """Immediately close the in-flight session (shutdown / test).

        Does NOT call finalize_final_lap — callers that need the final
        lap (IngestFrame.stop, idle sweeper) must call finalize_final_lap
        themselves before force_finalize.
        """
        if self._current is None:
            return None
        closed = self._current
        self.note_close(at.timestamp())
        closed.finalize(at, reason)
        self._current = None
        return closed

    def maybe_finalize_idle(self, now: datetime) -> Session | None:
        """Finalize the in-flight session if the stream has been silent
        past the silence threshold. Used by a background sweeper so a
        session does not stay open forever when the game stops emitting
        packets without another frame arriving to trigger on_frame's
        boundary check.

        Does NOT call finalize_final_lap — callers must do so before
        this method so the final lap is captured before lap state is
        potentially reused.
        """
        if self._current is None or self._last_frame_at is None:
            return None
        if (now - self._last_frame_at) <= self._silence:
            return None
        closed = self._current
        self.note_close(self._last_frame_at.timestamp())
        closed.finalize(self._last_frame_at, SessionCloseReason.SILENCE)
        self._current = None
        return closed


def attach_session(
    sm: SessionManager,
    raw: FrameRaw,
    at: datetime,
) -> tuple[BoundaryDecision, DecodedFrame]:
    """Convenience: run boundary logic and produce a DecodedFrame tagged
    with the resulting current session id."""
    decision = sm.on_frame(raw, at)
    current = decision.current_session
    car_id = current.car_id if current else _derive_car_id(raw)
    sid = current.id if current else None
    frame = DecodedFrame(session_id=sid, car_id=car_id, received_at=at, raw=raw)
    return decision, frame
