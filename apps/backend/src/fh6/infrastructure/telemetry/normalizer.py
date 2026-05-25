"""Optional post-decode normalization layer. The decoder already applies
the lap-zero→null and U8/S8 → [0,1]/[-1,1] conversions; this module
holds additional conversions the API spec may require at the boundary
(e.g., tire-temp normalized-window). Kept lean by design (FR-022).
"""

from __future__ import annotations


def tire_temp_norm_window(raw: float, optimal_low: float, optimal_high: float) -> float:
    """Map raw tire temperature to 0..1 within the optimal window.

    Below the window: 0. Above: 1. Inside: linear.
    """
    if optimal_high <= optimal_low:
        raise ValueError("optimal_high must exceed optimal_low")
    if raw <= optimal_low:
        return 0.0
    if raw >= optimal_high:
        return 1.0
    return (raw - optimal_low) / (optimal_high - optimal_low)
