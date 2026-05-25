# `application/` — use cases + services

## Responsibility

Orchestrates the domain. Implements the things the system *does*:
ingest a frame, start / close a session, request a prediction,
push a callout, rebuild a fingerprint, enforce retention. Depends
only on `domain/` ports — never on infrastructure adapters
directly.

## Contents

- `use_cases/` — one file per discrete operation. Each is a thin
  coordinator: validate inputs, call ports, return results. No
  framework I/O, no SQL, no HTTP. Examples: `ingest_frame.py`,
  `resume_session_on_restart.py` (Clarification Q1),
  `get_live_aggregate_for_car.py`,
  `create_telemetry_clip_replay.py`, `ask_coach.py`,
  `rebuild_driver_fingerprint.py`, `generate_insights.py`,
  `get_session_detail.py`, `get_session_frames.py`.
- `services/` — longer-lived collaborators that survive across
  use-case invocations: `session_manager.py` (boundary detection +
  events), `derivations.py` (physics: balance, weight, grip budget,
  body control, throttle smoothness, power-band occupancy),
  `state_emitter.py` (stream-paused / resumed / lost),
  `event_emitter.py` (lap, sector, shift, oversteer, off-track,
  smashable-hit), `retention_enforcer.py` (age + per-car cap, Q2),
  `coach_availability.py` (Q3 — `claude --version` with 1 s TTL),
  `modeled_placeholder.py` (US1 stub until US5 lands),
  `hot_cache.py` (3 s rolling window keyed by
  `(session_id, car_id)`).

## Rules

- Depend on `domain/`. Never import from `infrastructure/` or
  `interfaces/`.
- All side effects flow through a port — repositories,
  `LLMPort`, `MLPort`, `Clock`. Tests substitute in-memory fakes.
- Pure-function preference for derivations and detectors — they
  must be safe to call analytically (Principle X (3)).
- One consumer task drains the ingest queue (`IngestFrame`); fan-out
  happens here before adapters touch the wire.

## See also

- [API contract](../../../api-contract.md) — REST + WebSocket field shapes.
