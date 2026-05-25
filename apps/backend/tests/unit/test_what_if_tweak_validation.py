"""T143: unit test for closed Q5 what-if tweak set."""

from __future__ import annotations

import pytest

from fh6.domain.entities.replay import WHAT_IF_TWEAK_KINDS
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.ml.what_if_simulator import (
    UnsupportedWhatIfKind,
    WhatIfSimulator,
)
from tests.contract.fake_repos import InMemoryReplayRepository


@pytest.mark.asyncio
async def test_each_supported_kind_round_trips() -> None:
    repo = InMemoryReplayRepository()
    sim = WhatIfSimulator(repo)
    for kind in WHAT_IF_TWEAK_KINDS:
        result = await sim.run(
            session_id=SessionId("s_wi"),
            from_s=0.0,
            to_s=10.0,
            tweaks=[{"kind": kind, "delta": 5.0}],
        )
        assert result.replay_id.startswith("cf_")
        assert result.confidence.model_version.startswith("what-if-v0")
        rep = await repo.get(result.replay_id)  # type: ignore[arg-type]
        assert rep is not None
        assert rep.tweaks is not None and rep.tweaks[0]["kind"] == kind


@pytest.mark.asyncio
async def test_unknown_kind_raises_documented_error() -> None:
    repo = InMemoryReplayRepository()
    sim = WhatIfSimulator(repo)
    with pytest.raises(UnsupportedWhatIfKind) as ei:
        await sim.run(
            session_id=SessionId("s_wi"),
            from_s=0.0,
            to_s=10.0,
            tweaks=[{"kind": "gear_ratio", "delta": 0.1}],
        )
    assert "supported" in str(ei.value)
