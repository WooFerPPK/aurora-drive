"""T098: unit test for CooldownPolicy (API spec §7A / FR-025 / FR-026)."""

from __future__ import annotations

from fh6.domain.entities.coach_callout import CalloutPriority
from fh6.infrastructure.coach.cooldown_policy import CooldownPolicy


def test_same_kind_30s_window_blocks_same_priority() -> None:
    p = CooldownPolicy()
    assert p.evaluate(
        kind="oversteer",
        corner="T3",
        priority=CalloutPriority.TIP,
        lap=1,
        now=0.0,
    ).allowed
    p.record(
        kind="oversteer",
        corner="T3",
        priority=CalloutPriority.TIP,
        lap=1,
        now=0.0,
    )
    # 10 s later — still inside 30 s window.
    d = p.evaluate(
        kind="oversteer",
        corner="T3",
        priority=CalloutPriority.TIP,
        lap=2,
        now=10.0,
    )
    assert not d.allowed
    assert d.reason == "global_rate" or d.reason == "same_kind"


def test_global_rate_floor_8s() -> None:
    p = CooldownPolicy()
    p.record(
        kind="oversteer",
        corner="T1",
        priority=CalloutPriority.WARN,
        lap=1,
        now=0.0,
    )
    d = p.evaluate(
        kind="missed_upshift",
        corner="T2",
        priority=CalloutPriority.WARN,
        lap=1,
        now=5.0,
    )
    assert not d.allowed
    assert d.reason == "global_rate"
    # 8.01 s later — past the floor.
    d2 = p.evaluate(
        kind="missed_upshift",
        corner="T2",
        priority=CalloutPriority.WARN,
        lap=1,
        now=8.01,
    )
    assert d2.allowed


def test_warn_overrides_same_kind_cooldown() -> None:
    p = CooldownPolicy()
    p.record(
        kind="oversteer",
        corner="T3",
        priority=CalloutPriority.TIP,
        lap=1,
        now=0.0,
    )
    # 12 s later: outside global rate, inside same-kind cool-down. WARN
    # should be allowed to override the lower-priority TIP.
    d = p.evaluate(
        kind="oversteer",
        corner="T3",
        priority=CalloutPriority.WARN,
        lap=2,
        now=12.0,
    )
    assert d.allowed


def test_same_corner_same_lap_blocks_repeats() -> None:
    p = CooldownPolicy(global_rate_floor_s=0.0, same_kind_cooldown_s=0.0)
    p.record(
        kind="off_track",
        corner="T3",
        priority=CalloutPriority.WARN,
        lap=1,
        now=0.0,
    )
    # Same lap → blocked.
    d = p.evaluate(
        kind="off_track",
        corner="T3",
        priority=CalloutPriority.TIP,
        lap=1,
        now=0.001,
    )
    assert not d.allowed
    # New lap → allowed.
    d_new = p.evaluate(
        kind="off_track",
        corner="T3",
        priority=CalloutPriority.WARN,
        lap=2,
        now=0.002,
    )
    assert d_new.allowed
