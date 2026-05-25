from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WireModel(BaseModel):
    """Base for every payload defined in the API spec.
    Forbids extra fields — contract drift surfaces as a test failure.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
