"""In-memory fake repositories for contract tests.

Implements the same domain ports the production Postgres adapters
implement. Stays inside `tests/` so production code remains free of
test scaffolding (constitution Principle VII).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal

from fh6.domain.entities.car import Car
from fh6.domain.entities.coach_callout import CoachCallout
from fh6.domain.entities.coach_insight import CoachInsight
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.entities.replay import Replay
from fh6.domain.entities.session import Session, SessionCloseReason
from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    ClassPriorBin,
    RatioRecord,
    ResetCounts,
    ShiftEventRow,
    TransmissionModeRecord,
)
from fh6.domain.value_objects.completed_lap import CompletedLap
from fh6.domain.value_objects.engine_fingerprint import EngineClassKey, EngineFingerprint
from fh6.domain.value_objects.frame_position import FramePositionSnapshot
from fh6.domain.value_objects.ids import CarId, ReplayId, SessionId
from fh6.domain.value_objects.session_event import SessionEvent


class InMemoryCarRepository:
    def __init__(self, session_repo: InMemorySessionRepository | None = None) -> None:
        self.cars: dict[str, Car] = {}
        # Optional back-ref so the fake can simulate the FK CASCADE that
        # the pg adapter relies on (migration 0003_car_fks_cascade).
        self._session_repo = session_repo

    async def upsert(self, car: Car) -> None:
        self.cars[str(car.id)] = car

    async def get(self, car_id: CarId) -> Car | None:
        return self.cars.get(str(car_id))

    async def list_all(self) -> list[Car]:
        return list(self.cars.values())

    async def delete_all_sessions(self, car_id: CarId) -> int:
        if self._session_repo is None:
            return 0
        to_remove = [
            sid for sid, s in self._session_repo.sessions.items() if str(s.car_id) == str(car_id)
        ]
        for sid in to_remove:
            self._session_repo.sessions.pop(sid, None)
        return len(to_remove)

    async def delete(self, car_id: CarId) -> bool:
        if str(car_id) not in self.cars:
            return False
        # Cascade: drop the car's sessions too.
        await self.delete_all_sessions(car_id)
        del self.cars[str(car_id)]
        return True

    async def delete_all(self) -> int:
        count = len(self.cars)
        if self._session_repo is not None:
            self._session_repo.sessions.clear()
        self.cars.clear()
        return count

    async def rename_by_ordinal(self, ordinal: int, *, display_name: str, short_name: str) -> int:
        from dataclasses import replace

        n = 0
        for cid, car in list(self.cars.items()):
            if car.car_ordinal == ordinal:
                self.cars[cid] = replace(car, display_name=display_name, short_name=short_name)
                n += 1
        return n


class InMemorySessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    async def save(self, session: Session) -> None:
        self.sessions[str(session.id)] = session

    async def get(self, session_id: SessionId) -> Session | None:
        return self.sessions.get(str(session_id))

    async def latest_in_flight(self) -> Session | None:
        for s in reversed(list(self.sessions.values())):
            if s.ended_at is None:
                return s
        return None

    async def list_for_car(self, car_id: CarId, limit: int = 50) -> list[Session]:
        out = [s for s in self.sessions.values() if str(s.car_id) == str(car_id)]
        out.sort(key=lambda s: (s.bookmarked, s.started_at), reverse=True)
        return out[:limit]

    async def list_all(self, limit: int = 10_000) -> list[Session]:
        out = list(self.sessions.values())
        out.sort(key=lambda s: (s.bookmarked, s.started_at), reverse=True)
        return out[:limit]

    async def delete(self, session_id: SessionId) -> bool:
        return self.sessions.pop(str(session_id), None) is not None

    async def delete_all(self) -> int:
        n = len(self.sessions)
        self.sessions.clear()
        return n

    async def rename(self, session_id: SessionId, name: str | None) -> Session | None:
        s = self.sessions.get(str(session_id))
        if s is None:
            return None
        trimmed = name.strip() if name is not None else None
        s.name = trimmed if trimmed else None
        return s

    async def set_bookmark(self, session_id: SessionId, bookmarked: bool) -> Session | None:
        s = self.sessions.get(str(session_id))
        if s is None:
            return None
        s.bookmarked = bookmarked
        return s

    async def finalize_stale(
        self,
        *,
        older_than: datetime,
        except_id: SessionId | None,
    ) -> int:
        count = 0
        for s in self.sessions.values():
            if s.ended_at is not None:
                continue
            if s.started_at >= older_than:
                continue
            if except_id is not None and str(s.id) == str(except_id):
                continue
            s.finalize(older_than, SessionCloseReason.RESTART_FINALIZE)
            count += 1
        return count


class InMemoryFrameStore:
    """Holds DecodedFrame objects; serves projections for contract tests."""

    def __init__(self) -> None:
        self.frames: dict[str, list[DecodedFrame]] = {}

    async def append(self, frame: DecodedFrame) -> None:
        if frame.session_id is None:
            raise ValueError("frame has no session_id")
        self.frames.setdefault(str(frame.session_id), []).append(frame)

    async def append_batch(self, frames: Sequence[DecodedFrame]) -> None:
        for f in frames:
            await self.append(f)

    async def read_projection(
        self,
        session_id: SessionId,
        *,
        from_s: float | None = None,
        to_s: float | None = None,
        hz: Literal[10, 30, 60] = 30,
        fields: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        rows = self.frames.get(str(session_id), [])
        if not rows:
            return {
                "sessionId": str(session_id),
                "hz": hz,
                "fields": list(fields) if fields else ["speed", "throttle", "brake", "position"],
                "data": [],
            }
        # Apply hz downsampling by stride; source assumed 60 Hz.
        stride = {10: 6, 30: 2, 60: 1}[hz]
        sampled = rows[::stride]
        t0 = sampled[0].received_at
        out: list[list[object]] = []
        for f in sampled:
            t_rel = (f.received_at - t0).total_seconds()
            if from_s is not None and t_rel < from_s:
                continue
            if to_s is not None and t_rel > to_s:
                continue
            wheels = f.raw.wheels or {}
            accel = (f.raw.motion or {}).get("acceleration") or {}
            race = f.raw.race or {}
            derived = getattr(f, "derived", None) or {}
            # derived may not be present on the DecodedFrame — fall back to {}
            row_dict = {
                "speed": f.raw.motion.get("speed_mps") if f.raw.motion else None,
                "throttle": f.raw.inputs.get("throttle") if f.raw.inputs else None,
                "brake": f.raw.inputs.get("brake") if f.raw.inputs else None,
                "position": (
                    [
                        f.raw.motion["position"]["x"],
                        f.raw.motion["position"]["y"],
                        f.raw.motion["position"]["z"],
                    ]
                    if f.raw.motion and "position" in f.raw.motion
                    else None
                ),
                "rpm": f.raw.engine.get("rpm") if f.raw.engine else None,
                "gear": f.raw.drivetrain.get("gear") if f.raw.drivetrain else None,
                "currentLapS": race.get("currentLapS"),
                "lastLapS": race.get("lastLapS"),
                "bestLapS": race.get("bestLapS"),
                "gripBudget": derived.get("gripBudgetUsed") if isinstance(derived, dict) else None,
                "acceleration": (
                    [accel.get("x"), accel.get("y"), accel.get("z")] if accel else None
                ),
                "tireTemp": (
                    [
                        (wheels.get("fl") or {}).get("tireTemp_normWindow"),
                        (wheels.get("fr") or {}).get("tireTemp_normWindow"),
                        (wheels.get("rl") or {}).get("tireTemp_normWindow"),
                        (wheels.get("rr") or {}).get("tireTemp_normWindow"),
                    ]
                    if wheels
                    else None
                ),
            }
            if fields is None:
                out.append(
                    [
                        t_rel,
                        row_dict["speed"],
                        row_dict["throttle"],
                        row_dict["brake"],
                        row_dict["position"],
                    ]
                )
            else:
                out.append([t_rel, *(row_dict.get(field) for field in fields)])
        return {
            "sessionId": str(session_id),
            "hz": hz,
            "fields": list(fields) if fields else ["speed", "throttle", "brake", "position"],
            "data": out,
        }

    async def last_frame_time(self, session_id: SessionId) -> datetime | None:
        rows = self.frames.get(str(session_id), [])
        return rows[-1].received_at if rows else None

    async def bytes_used_by_car(self, car_id: CarId) -> int:
        total = 0
        for sid, rows in self.frames.items():
            for f in rows:
                if str(f.car_id) == str(car_id):
                    total += 1200  # match production estimate (R-3)
        return total

    async def delete_session(self, session_id: SessionId) -> int:
        return len(self.frames.pop(str(session_id), []))

    async def read_last_position_snapshot(
        self, session_id: SessionId
    ) -> FramePositionSnapshot | None:
        frames = self.frames.get(str(session_id), [])
        if not frames:
            return None
        latest = max(frames, key=lambda f: f.received_at)
        pos = latest.raw.motion.get("position") or {}
        orient = latest.raw.motion.get("orientation") or {}
        return FramePositionSnapshot(
            time=latest.received_at,
            x=float(pos.get("x", 0.0)),
            y=float(pos.get("y", 0.0)),
            z=float(pos.get("z", 0.0)),
            yaw=float(orient.get("yaw", 0.0)),
        )

    async def read_position_track(self, session_id: SessionId) -> list[FramePositionSnapshot]:
        frames = sorted(self.frames.get(str(session_id), []), key=lambda f: f.received_at)
        out: list[FramePositionSnapshot] = []
        for f in frames:
            pos = f.raw.motion.get("position") or {}
            orient = f.raw.motion.get("orientation") or {}
            out.append(
                FramePositionSnapshot(
                    time=f.received_at,
                    x=float(pos.get("x", 0.0)),
                    y=float(pos.get("y", 0.0)),
                    z=float(pos.get("z", 0.0)),
                    yaw=float(orient.get("yaw", 0.0)),
                )
            )
        return out

    async def delete_frames_in_range(
        self,
        session_id: SessionId,
        *,
        after: datetime,
        before: datetime,
    ) -> int:
        frames = self.frames.get(str(session_id), [])
        kept = [f for f in frames if not (after < f.received_at < before)]
        deleted = len(frames) - len(kept)
        self.frames[str(session_id)] = kept
        return deleted


class InMemoryCoachRepository:
    def __init__(self) -> None:
        self.callouts: dict[str, list[CoachCallout]] = {}
        self.insights: dict[str, list[CoachInsight]] = {}
        self.dismissed: set[str] = set()

    async def save_callout(self, callout: CoachCallout) -> None:
        self.callouts.setdefault(str(callout.session_id), []).append(callout)

    async def list_callouts(self, session_id: SessionId) -> list[CoachCallout]:
        return list(self.callouts.get(str(session_id), []))

    async def save_insight(self, insight: CoachInsight) -> None:
        self.insights.setdefault(str(insight.session_id), []).append(insight)

    async def list_insights(self, session_id: SessionId) -> list[CoachInsight]:
        return [i for i in self.insights.get(str(session_id), []) if i.id not in self.dismissed]

    async def get_insight(self, insight_id: str) -> CoachInsight | None:
        for items in self.insights.values():
            for i in items:
                if i.id == insight_id:
                    return i
        return None

    async def dismiss_insight(self, insight_id: str) -> bool:
        already = insight_id in self.dismissed
        self.dismissed.add(insight_id)
        return not already


class InMemoryReplayRepository:
    def __init__(self) -> None:
        self.replays: dict[str, Replay] = {}

    async def save(self, replay: Replay) -> None:
        self.replays[str(replay.id)] = replay

    async def get(self, replay_id: ReplayId) -> Replay | None:
        return self.replays.get(str(replay_id))


class InMemoryLapRepository:
    def __init__(self) -> None:
        # keyed by (session_id_str, lap_number)
        self._laps: dict[tuple[str, int], CompletedLap] = {}

    async def upsert_lap(self, session_id: SessionId, lap: CompletedLap) -> None:
        self._laps[(str(session_id), lap.lap_number)] = lap

    async def list_laps_for_session(self, session_id: SessionId) -> list[CompletedLap]:
        sid = str(session_id)
        out = [lap for key, lap in self._laps.items() if key[0] == sid]
        out.sort(key=lambda lap: lap.lap_number)
        return out

    async def min_lap_time_for_session(self, session_id: SessionId) -> float | None:
        laps = await self.list_laps_for_session(session_id)
        return min((l.lap_time_s for l in laps), default=None)


class InMemoryDriverRepository:
    def __init__(self) -> None:
        from fh6.domain.entities.driver_profile import DriverProfile

        self._profile = DriverProfile()

    async def get(self):  # type: ignore[no-untyped-def]
        return self._profile

    async def save(self, profile) -> None:  # type: ignore[no-untyped-def]
        self._profile = profile


class InMemorySessionEventsRepository:
    """Fake `SessionEventsRepository` for contract + integration tests."""

    def __init__(self) -> None:
        self._by_session: dict[str, list[SessionEvent]] = {}

    async def save_many(self, events: list[SessionEvent]) -> None:
        for e in events:
            self._by_session.setdefault(str(e.session_id), []).append(e)

    async def list_for_session(self, session_id) -> list[SessionEvent]:  # type: ignore[no-untyped-def]
        out = list(self._by_session.get(str(session_id), []))
        out.sort(key=lambda e: e.at_s)
        return out


class InMemoryShiftPredictorRepo:
    """Fake `ShiftPredictorRepository` for unit + contract tests."""

    def __init__(self) -> None:
        self._bins: dict[tuple[EngineFingerprint, int, int], BinRecord] = {}
        self._ratios: dict[tuple[EngineFingerprint, int], RatioRecord] = {}
        self._class_priors: dict[tuple[EngineClassKey, int, int], ClassPriorBin] = {}
        self._shift_events: list[ShiftEventRow] = []
        self._next_id: int = 1
        self._transmission_modes: dict[EngineFingerprint, TransmissionModeRecord] = {}

    async def upsert_bin(self, rec: BinRecord) -> None:
        self._bins[(rec.fingerprint, rec.gear, rec.rpm_bin)] = rec

    async def upsert_bins(self, recs: Sequence[BinRecord]) -> None:
        for rec in recs:
            await self.upsert_bin(rec)

    async def read_bins(self, fp: EngineFingerprint) -> list[BinRecord]:
        return [v for (f, _g, _r), v in self._bins.items() if f == fp]

    async def upsert_ratio(self, rec: RatioRecord) -> None:
        self._ratios[(rec.fingerprint, rec.gear)] = rec

    async def read_ratios(self, fp: EngineFingerprint) -> list[RatioRecord]:
        return [v for (f, _g), v in self._ratios.items() if f == fp]

    async def upsert_class_prior_bin(self, rec: ClassPriorBin) -> None:
        self._class_priors[(rec.class_key, rec.gear, rec.rpm_bin)] = rec

    async def read_class_prior(self, key: EngineClassKey) -> list[ClassPriorBin]:
        return [v for (k, _g, _r), v in self._class_priors.items() if k == key]

    async def record_shift_event(self, row: ShiftEventRow) -> None:
        if row.id is None:
            row = replace(row, id=self._next_id)
            self._next_id += 1
        self._shift_events.append(row)

    async def read_shift_events(self, session_id: SessionId) -> list[ShiftEventRow]:
        out = [r for r in self._shift_events if str(r.session_id) == str(session_id)]
        out.sort(key=lambda r: r.shift_at)
        return out

    async def reset_fingerprint(self, fp: EngineFingerprint) -> ResetCounts:
        old_bins = {k: v for k, v in self._bins.items() if k[0] == fp}
        old_ratios = {k: v for k, v in self._ratios.items() if k[0] == fp}
        old_events = [r for r in self._shift_events if r.fingerprint == fp]

        for k in old_bins:
            del self._bins[k]
        for k in old_ratios:
            del self._ratios[k]
        self._shift_events = [r for r in self._shift_events if r.fingerprint != fp]

        return ResetCounts(
            engine_curves=len(old_bins),
            gear_ratios=len(old_ratios),
            shift_events=len(old_events),
        )

    # ------------------------------------------------------------------
    # v2 surfaces: transmission_modes + class-key fingerprint aggregation
    # ------------------------------------------------------------------

    async def list_fingerprints_for_class_key(
        self,
        *,
        candidate_fingerprints: Sequence[EngineFingerprint],
        min_total_samples: int,
    ) -> list[tuple[EngineFingerprint, int]]:
        if not candidate_fingerprints:
            return []
        candidate_set = set(candidate_fingerprints)
        totals: dict[EngineFingerprint, int] = {}
        for (fp, _gear, _rpm_bin), rec in self._bins.items():
            if fp not in candidate_set:
                continue
            totals[fp] = totals.get(fp, 0) + rec.count
        return [(fp, total) for fp, total in totals.items() if total >= min_total_samples]

    async def upsert_transmission_mode(self, rec: TransmissionModeRecord) -> None:
        # PK is (car_ordinal, performance_index, num_cylinders) — i.e. the
        # EngineFingerprint itself. Replace-in-place mirrors ON CONFLICT DO UPDATE.
        self._transmission_modes[rec.fingerprint] = rec

    async def read_transmission_mode(self, fp: EngineFingerprint) -> TransmissionModeRecord | None:
        return self._transmission_modes.get(fp)

    async def delete_transmission_mode(self, fp: EngineFingerprint) -> int:
        return 1 if self._transmission_modes.pop(fp, None) is not None else 0
