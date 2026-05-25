# `infrastructure/` — adapters + I/O

## Responsibility

Concrete implementations of `domain/ports/`. The only ring allowed
to touch the network, the database, the filesystem, subprocesses,
scikit-learn, or other third-party runtime dependencies.

## Contents

- `db/` — SQLAlchemy 2.0 async declarative models, Alembic
  migrations, and Postgres-backed repositories that implement the
  domain ports.
- `timeseries/` — `TimescaleFrameStore` (hypertable + continuous
  aggregates `frames_30hz` / `frames_10hz`); projection-aware
  reads pick the right aggregate from the requested `hz`.
- `telemetry/` — `udp_listener.py` (asyncio `DatagramProtocol`,
  unbounded queue → single consumer per research R-5),
  `fh6_decoder.py` (little-endian 324-byte format, isolated
  assumption — Principle VII), `normalizer.py` (units, lap-zero
  null, WheelInPuddle booleans), `cadence_meter.py` (running mean
  of TimestampMS deltas, FR-004).
- `llm/` — `claude_headless_adapter.py` invokes `claude -p`
  via `asyncio.create_subprocess_exec`; `dry_run_adapter.py` for
  test runs without the CLI; `templates/` for prompt
  scaffolding. **Never imports `anthropic`. Never reads
  `ANTHROPIC_API_KEY`.** (Principle III, enforced by
  `tests/contract/test_no_api_key.py`.)
- `ml/` — per-model directories implementing `ml.models.Model`:
  `tire_wear/`, `lap_residual/`, `fuel/`, `crash_risk/`,
  `best_achievable_lap/`, `finish/`, `driver_fingerprint/`. Each
  declares `tolerance_band` + `model_version`. `calibration.py`
  runs the reliability-diagram gate (Q4). `what_if_simulator.py`
  re-runs `derivations.py` with the closed Q5 tweak set.
  `track_inference/cluster.py` produces inferred `tracks` rows
  offline (research R-11).
- `coach/` — `callout_engine.py` (separate consumer task on the
  frame stream), `detectors/` (oversteer, missed upshift,
  off-track, late-throttle-on-exit), `cooldown_policy.py` (same
  kind 30 s, same corner 1 lap, global ≤ 1 / 8 s), `citation_builder.py`.
- `config.py` — reads settings from the `settings` table at
  startup; seeds defaults on first launch.
- `logging.py` — structlog JSON-in-prod / pretty-in-dev.

## Rules

- Implements ports declared in `domain/ports/`. Never adds a port
  here — they belong in `domain/`.
- Application code never imports adapters directly; the DI
  container in `interfaces/app.py` wires ports to implementations
  at startup.
- The decoder is the only module allowed to assume the FH6 packet
  format. The rest of the system reads `DecodedFrame` dataclasses.
- The Claude adapter is the only module allowed to spawn `claude`
  subprocesses.

