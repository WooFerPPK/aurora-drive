from __future__ import annotations

from typing import Protocol, TypeVar

from fh6.domain.value_objects.confidence import Confidence

F = TypeVar("F")
V = TypeVar("V")


class Model[F, V](Protocol):
    """Every modeled-tier producer implements this. Carries declared
    tolerance band and model version metadata (Clarification Q4)."""

    model_version: str
    tolerance_band: float

    def predict(self, features: F) -> tuple[V, Confidence]: ...
