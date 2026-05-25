# `domain/` — innermost ring

## Responsibility

Pure business model. Entities, value objects, and ports (Protocol
interfaces). No framework imports, no I/O, no async runtime, no
SQLAlchemy / FastAPI / pydantic dependencies. Stable across
infrastructure changes.

## Contents

- `entities/` — dataclasses for `Session`, `Car`, `Frame`,
  `DriverProfile`, `CoachCallout`, `CoachInsight`, `Prediction`,
  `Replay`, `Track`. Plain data + invariants. No persistence concerns.
- `value_objects/` — `units.py`, `ids.py` (typed `SessionId` /
  `CarId` / `ReplayId`), `confidence.py` (refuses construction
  without `value`, `tolerance_band`, `model_version` — FR-017 +
  Clarification Q4), `tier.py` (`RAW | DERIVED | MODELED`).
- `ports/` — `typing.Protocol` interfaces the application layer
  depends on. Implementations live in `infrastructure/`. One file per
  port: `frame_store`, `session_repository`, `car_repository`,
  `driver_repository`, `coach_repository`, `replay_repository`,
  `settings_repository`, `layouts_repository`, `packet_decoder`,
  `llm_port`, `ml_port`, `clock`.

## Rules

- Never import from `application/`, `infrastructure/`, or
  `interfaces/`.
- Never import third-party runtime libraries (FastAPI, SQLAlchemy,
  asyncio primitives, pydantic). Standard library only.
- A new port lives here before its first implementation.
- Confidence values flow through `value_objects/confidence.py` —
  raw floats never cross the modeled-tier boundary.

