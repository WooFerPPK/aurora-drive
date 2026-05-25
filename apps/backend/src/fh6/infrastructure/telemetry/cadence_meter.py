from __future__ import annotations

from collections import deque


class CadenceMeter:
    """Tracks effective packet cadence from TimestampMS deltas (FR-004).

    Reports Hz over the trailing N samples. Robust to TimestampMS
    wraparound at U32 boundary.
    """

    _U32_MOD = 1 << 32

    def __init__(self, window: int = 60) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        self._window = window
        self._deltas_ms: deque[int] = deque(maxlen=window)
        self._last_ts: int | None = None

    def observe(self, packet_timestamp_ms: int) -> None:
        if self._last_ts is None:
            self._last_ts = packet_timestamp_ms
            return
        delta = packet_timestamp_ms - self._last_ts
        if delta < 0:
            delta += self._U32_MOD  # wraparound
        if 0 < delta < 1_000:  # ignore implausible gaps (idle / wrap heuristic)
            self._deltas_ms.append(delta)
        self._last_ts = packet_timestamp_ms

    @property
    def effective_hz(self) -> float | None:
        if not self._deltas_ms:
            return None
        mean_ms = sum(self._deltas_ms) / len(self._deltas_ms)
        return 1000.0 / mean_ms if mean_ms > 0 else None

    def reset(self) -> None:
        self._deltas_ms.clear()
        self._last_ts = None
