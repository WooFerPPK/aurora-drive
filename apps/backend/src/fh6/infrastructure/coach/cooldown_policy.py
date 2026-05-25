"""T097: CooldownPolicy (API spec §7A / FR-025 / FR-026).

Rules:
- Same kind: 30 s cool-down.
- Same corner: 1 lap cool-down per kind.
- Global rate: ≤ 1 callout / 8 s (deque + sliding window).
- Priority override: a `warn` may pre-empt a pending `info`/`tip` cool-down
  on the same kind, but never the global rate floor.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from fh6.domain.entities.coach_callout import CalloutPriority

_PRIORITY_RANK = {
    CalloutPriority.INFO: 0,
    CalloutPriority.TIP: 1,
    CalloutPriority.WARN: 2,
}


@dataclass(slots=True)
class _LastFire:
    at: float
    lap: int
    priority: CalloutPriority


@dataclass(slots=True)
class CooldownDecision:
    allowed: bool
    reason: str | None = None


@dataclass(slots=True)
class CooldownPolicy:
    same_kind_cooldown_s: float = 30.0
    global_rate_floor_s: float = 8.0
    _per_kind: dict[str, _LastFire] = field(default_factory=dict)
    _per_kind_corner: dict[tuple[str, str], _LastFire] = field(default_factory=dict)
    _global: deque[float] = field(default_factory=lambda: deque(maxlen=16))

    def evaluate(
        self,
        *,
        kind: str,
        corner: str,
        priority: CalloutPriority,
        lap: int,
        now: float,
    ) -> CooldownDecision:
        # Global rate: never finer than 8 s, even for warns.
        if self._global and (now - self._global[-1]) < self.global_rate_floor_s:
            return CooldownDecision(allowed=False, reason="global_rate")

        # Same-kind 30 s window — warn may override info/tip.
        last_kind = self._per_kind.get(kind)
        if (
            last_kind is not None
            and (now - last_kind.at) < self.same_kind_cooldown_s
            and _PRIORITY_RANK[priority] <= _PRIORITY_RANK[last_kind.priority]
        ):
            return CooldownDecision(allowed=False, reason="same_kind")

        # Same kind + same corner: 1-lap cool-down (kind-scoped).
        last_corner = self._per_kind_corner.get((kind, corner))
        if (
            last_corner is not None
            and lap == last_corner.lap
            and _PRIORITY_RANK[priority] <= _PRIORITY_RANK[last_corner.priority]
        ):
            return CooldownDecision(allowed=False, reason="same_corner_lap")

        return CooldownDecision(allowed=True)

    def record(
        self,
        *,
        kind: str,
        corner: str,
        priority: CalloutPriority,
        lap: int,
        now: float,
    ) -> None:
        self._per_kind[kind] = _LastFire(at=now, lap=lap, priority=priority)
        self._per_kind_corner[(kind, corner)] = _LastFire(at=now, lap=lap, priority=priority)
        self._global.append(now)
