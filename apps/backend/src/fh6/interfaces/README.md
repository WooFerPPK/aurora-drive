# `interfaces/` — REST + WebSocket transport

## Responsibility

Translates HTTP / WebSocket traffic to use-case calls and back.
Owns FastAPI routers, WebSocket endpoints, Pydantic schemas, the
DI container, and the documented validation-error shape. Every
endpoint here corresponds 1-to-1 to a section in
`api-contract.md`.

## Contents

- `app.py` — FastAPI factory. CORS (`http://localhost:*` +
  `app://*`), lifespan that runs `alembic upgrade head`, seeds
  settings, starts the UDP listener + consumer tasks, and wires
  every domain port to its infrastructure implementation.
- `rest/` — one router per API spec section: `sessions_router`,
  `cars_router`, `driver_router`, `predict_router`, `shift_router`,
  `coach_router` (including `/api/coach/status`, Q3), `track_router`,
  `replay_router`, `settings_router`, `layouts_router`,
  `health_router`. `widget_kinds.py` holds the bare allow-list the
  layout validator checks (`/api/widgets/catalog` itself was removed
  in Phase 3 §1.3 #6 — the widget catalog is a frontend concern).
  `errors.py` exposes `validation_error_400(supported=...)` — the
  shape every 400 response uses (Q5, FR-034a).
- `rest/schemas/` — Pydantic v2 models for every payload. One
  file per spec section, each model with
  `model_config = ConfigDict(extra="forbid")`. The schemas
  mirror the spec verbatim; do not paraphrase.
- `ws/` — `live.py` (`/ws/live`: hello, subscribe, frame, state,
  event, batched-frames, mid-stream rate change), `coach.py`
  (`/ws/coach`: hello includes coach availability per Q3; pushes
  callouts), `heartbeat.py` (5 s idle heartbeat per
  subscriber, API spec §14).

## Rules

- Routers stay thin: validate, call a use-case, return the
  schema. No business logic, no SQL, no port wiring.
- Pydantic schemas mirror the API spec **exactly**. Any drift
  requires a Principle I amendment PR to
  `api-contract.md` before this code
  changes.
- WebSocket subscribers get a bounded per-client `asyncio.Queue`
  (~1 s of frames). Producer drops oldest on overflow — never
  blocks (research R-13, FR-014).
- Every router has a paired contract test under
  `tests/contract/` (Principle X (4)).
- DI happens in `app.py`. Modules below never construct adapters
  directly.

## See also

- [API contract](../../../api-contract.md) — followed verbatim by router shape.
