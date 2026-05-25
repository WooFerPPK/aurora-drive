# Forza Telemetry Dashboard — Backend API Spec

This doc tells the backend what the dashboard needs to render every page. It's organized by data domain. Pick whatever shape (REST, WS, GraphQL) you like — the field names + semantics here are what matters.

> **Reconciliation note (Phase 2.5, 2026-05-24).** This file has been
> rewritten section-by-section to describe what the FastAPI handlers in
> `src/fh6/interfaces/rest/` actually return today. Where the
> implementation diverged from earlier drafts (collapsed envelopes for
> finish/crashRisk/bestAchievableLap; flattened Cars list field names;
> reshaped Track + Mistakes payloads; renamed callout fields), the
> binding contract is what's documented here, not the older shapes.
> Phase 3 froze this contract into
> [`packages/contract/openapi.json`](../../packages/contract/openapi.json)
> and [`packages/contract/ws.schema.json`](../../packages/contract/ws.schema.json).

---

## 1. Overall architecture

```
[FH6 game] --UDP 324B @ frame rate--> [UDP listener]
                                            |
                                            v
                                  [Decoder + Normalizer]
                                            |
              +-----------------+-----------+----------+-----------------+
              v                 v                      v                 v
        [Hot state cache]   [Session store]    [Time-series DB]   [Models / LLM]
              |                 |                      |                 |
              +-----WS / SSE-----+--REST------+--REST--+-------REST------+
                                              v
                                       [Dashboard UI]
```

Three transport channels the UI expects:

| Channel | Protocol | Purpose |
|---|---|---|
| `live` | **WebSocket** | Realtime telemetry frames + state-transition events (stream-started, stream-paused, lap-completed, etc.) |
| `coach` | **WebSocket or SSE** | LLM-generated co-driver callouts pushed as they're produced. Cooled-down server-side. |
| `api` | **REST (JSON)** | Everything else — sessions, cars, driver profile, predictions on demand, settings, replays |

CORS: dashboard is local-first; allow `http://localhost:*` and `app://*` by default.

Times are **ISO-8601 UTC**. Durations in **seconds (float)**. Distances **meters**. Speeds **m/s** in payloads (UI converts to km/h / mph). Tire temps: pass through raw value AND a normalized 0..1 in the optimal-window (window edges configurable per-car).

---

## 2. Live telemetry — `/ws/live`

A WebSocket the dashboard opens on page load.

### Connection lifecycle

```
Client opens     /ws/live?sessionId=auto&car=current&frameRate=30
Server sends     { type: "hello", server: "fh6-backend/0.1.0",
                   capabilities: ["frames", "frames-batched", "events", "heartbeat", "rate-change"] }
Server may push  { type: "udp_bind_failed", message: "..." }  // one-shot; only if listener didn't bind
Server pushes    { type: "frame", ... }              // many per second while driving
Server pushes    { type: "state", state: "...", at: ... }  // transitions
Server pushes    { type: "event", kind: "...", ... }       // discrete events
Server pushes    { type: "heartbeat", at: ... }            // every 5s when no other traffic
Client may send  { type: "subscribe", topics: ["frames", "events"] }
Client may send  { type: "rate", hz: 10 }                  // mid-stream back-pressure
```

`frameRate` accepts `10 | 30 | 60`; other values close the socket with
code 1008.

Topics allowed on `/ws/live`: **`frames`**, **`events`**. The
`coach` topic is served by `/ws/coach`; subscribing to it here returns
an `error: wrong-channel` and the server closes the connection.

### Error frames

The server emits structured error messages instead of silently dropping
malformed client input:

```json
{ "type": "error", "code": "wrong-channel",  "message": "coach topic is served by /ws/coach" }
{ "type": "error", "code": "unknown-topic",  "topics": ["bogus"] }
{ "type": "error", "code": "unknown-message","received": "ping" }
{ "type": "error", "code": "unsupported-rate","hz": 120 }
```

Clients SHOULD surface these to the user (toast / status pill) rather
than dropping them.

### `frame` payload — every emitted packet

This is the workhorse. We do NOT need 60 of these per second over the wire — see "downsampling" below. But the schema is identical regardless of cadence.

```json
{
  "type": "frame",
  "t": 1731953683.812,        // seconds since session start (float)
  "sessionId": "s_2025-05-14T14-22-08_lambo_svj",
  "carId": "car_lambo_svj_2025",

  "isRaceOn": true,
  "race": {
    "lap": 8,
    "position": 3,
    "currentLapS": 12.441,
    "lastLapS": 69.012,
    "bestLapS": 68.421,
    "raceTimeS": 134.992
  },

  "engine": {
    "rpm": 6240.1,
    "idleRpm": 900,
    "maxRpm": 7800,
    "power_w": 257000,
    "torque_nm": 490,
    "boost_psi": 11.8,
    "fuel": 0.63               // 0..1
  },

  "drivetrain": {
    "gear": 4,                  // 0=neutral, R=reverse — match FH6 encoding; document yours
    "clutch": 0,                // 0..1 (FH6 reports 0 or 1; expose as float anyway)
    "type": "AWD"               // FWD | RWD | AWD
  },

  "motion": {
    "speed_mps": 41.7,
    "velocity":     { "x": 0.10, "y": 0.00, "z": 41.70 },
    "acceleration": { "x": 0.24, "y": -0.08, "z": 1.91 },
    "angularVelocity": { "x": 0.02, "y": 0.11, "z": -0.03 },
    "orientation":  { "yaw": 1.57, "pitch": 0.01, "roll": -0.02 },
    "position":     { "x": 12843.6, "y": 312.4, "z": -5421.9 }
  },

  "inputs": {
    "throttle": 0.84,           // normalized 0..1 (decode from u8 0..255)
    "brake":    0.00,
    "clutch":   0.00,
    "handbrake":0.00,
    "steer":   -0.094,          // -1..+1 (decode from s8 -127..127)
    "drivingLine":     0.02,    // -1..+1
    "aiBrakeDelta":   -0.03     // -1..+1
  },

  "wheels": {
    "fl": { "slipRatio": 0.04, "slipAngle": 0.07, "combinedSlip": 0.09,
             "rotation_rad_s": 96.3, "suspensionTravel_norm": 0.55, "suspensionTravel_m": 0.071,
             "tireTemp_c": 84.4, "tireTemp_normWindow": 0.32,
             "onRumble": 0, "inPuddle": 0, "surfaceRumble": 0.03 },
    "fr": { ... },
    "rl": { ... },
    "rr": { ... }
  },

  "world": {
    "carOrdinal": 2451,
    "carClass": "A",            // map S32 0..7 to D|C|B|A|S|R|P|X (official FH6 dev docs)
    "performanceIndex": 812,
    "numCylinders": 6,
    "carGroup": 18,             // FH6 CarGroup id
    "smashableVelDiff": 0.0,
    "smashableMass": 0.0
  },

  "derived": {                  // physics layer — computed server-side
    "balance": -0.07,           // -1=full understeer .. +1=full oversteer (signed)
    "weightFront": 0.54,        // 0..1
    "weightLeft":  0.61,
    "bodyControl": 0.72,        // 0..1, 1=damped
    "gripBudgetUsed": 0.78,     // 0..1
    "powerBandOccupancy": 0.62, // 0..1, time near peak power
    "throttleSmoothness": 0.71, // 0..1
    "stopDistance_m": 47.3      // kinematic v²/(2·decel) along -v̂; 0 when not actually braking
  },

  "modeled": {                  // ML/inferred — frame-level
    "tireWear":   { "fl": 0.28, "fr": 0.32, "rl": 0.51, "rr": 0.73 },  // 0..1 (FH6 doesn't ship this)
    "tireWearConfidence": 0.84,
    "modeledByVersion": "tire-wear-v3.2",
    "shiftRecommendation": {    // optional: present once the shift predictor has fired
      "byGear": { "1": 7100, "2": 7200 },
      "confidenceByGear": { "1": 0.7, "2": 0.8 },
      "currentGearTarget": 7200,
      "currentGearConfidence": 0.81,
      "displayActive": true,
      "stage": "learned",       // "learned" | "prior" | "fallback"
      "byGearSamples": { "1": 42, "2": 38 },
      "fingerprint": { "carOrdinal": 2451, "performanceIndex": 920, "numCylinders": 12 },
      "modelVersion": "shift-v1"
    }
  }
}
```

The decoder also preserves byte 323 of the UDP packet as
`tail_reserved_byte` in the DB column of the same name — it is **not**
serialized on the WS frame. The on-wire frame schema above is exhaustive.

### `state` transitions

```json
{ "type": "state", "state": "driving",        "at": 12.41 }
{ "type": "state", "state": "stream-paused",  "at": 134.9, "lastFrameAt": 134.6, "reason": "menu" }
{ "type": "state", "state": "stream-resumed", "at": 156.2 }
{ "type": "state", "state": "stream-lost",    "at": 220.0 }
```

**Rules:**
- Treat **packet silence ≥ 250ms (or 3× expected frame interval)** as `stream-paused`.
- After 30s of silence, emit `stream-lost`.
- The UI uses `stream-paused` to render the **idle/standby** state — the last frame is frozen until packets resume.

### `event` payloads — discrete events worth surfacing

All 10 kinds below are emitted today by the `EventEmitter` service.
Each event carries `type: "event"`, `kind`, `at` (seconds since session
start), and any kind-specific fields.

```json
{ "type": "event", "kind": "lap_started",     "lap": 9,  "at": 134.9 }
{ "type": "event", "kind": "lap_completed",   "lap": 8,  "time_s": 68.42, "isPersonalBest": true }
{ "type": "event", "kind": "sector_completed","sector": 2, "delta_s": -0.34, "isPB": true }
{ "type": "event", "kind": "shift",           "from": 3, "to": 4, "smoothness": 0.82, "rpm": 6800 }
{ "type": "event", "kind": "missed_upshift",  "gear": 3, "overshoot_ms": 320 }
{ "type": "event", "kind": "oversteer",       "duration_ms": 480, "peak_yaw_rs": 0.9, "corner": "T11" }
{ "type": "event", "kind": "off_track",       "duration_ms": 850, "corner": "T3" }
{ "type": "event", "kind": "smashable_hit",   "mass_kg": 12.4, "velDiff_mps": 0.6 }
{ "type": "event", "kind": "session_started", "sessionId": "...", "type": "free_roam|race|time_trial|drift|cross_country" }
{ "type": "event", "kind": "session_ended",   "sessionId": "...", "summary": { ... } }
```

### Downsampling

The dashboard cannot consume 60 fps of `frame` packets across the WebSocket without back-pressure issues on weaker machines. Server should:
- Always push `state` and `event` messages immediately, full fidelity.
- For `frame`, send at **30 Hz by default**, configurable via `?frameRate=N` (10/30/60). UI requests 30 by default; some pages (Live primary) can ask for 60.
- **Archive raw 60 Hz frames** server-side so the time-series DB has them for replay/analysis.

---

## 3. Sessions — `/api/sessions`

A "session" = one contiguous stream of packets. A new session is opened on `session_started` and closed when stream silence exceeds 60s (configurable). Sessions also auto-split on car change.

### `GET /api/sessions/current`
Returns the most recent in-flight session (`ended_at IS NULL`) as a
`SessionListItem` (shape below). The Live page polls this to find the
session id to wire predictions, coach feed, and session detail against.
`404 not_found` (`resource: "session"`) when no session is open.

### `GET /api/sessions`
Query params: `?carId=...&type=race&from=...&to=...&limit=50&cursor=...`

Returns a bare JSON array (no envelope). Pagination metadata travels in
response headers so the body stays homogeneous:

- `X-Next-Cursor: <opaque>` — opaque cursor for the next page. Omitted on
  the last page. Pass it back as `?cursor=...`.

**Ordering**: bookmarked sessions first, then `startedAt` descending —
i.e. `ORDER BY bookmarked DESC, started_at DESC`. The Sessions page pins
favourites to the top of the list regardless of recency.

```json
[
  {
    "id": "s_2025-05-14T14-22-08_lambo_svj",
    "carId": "car_lambo_svj_2025",
    "type": "free_roam",
    "startedAt": "2025-05-14T14:22:08Z",
    "endedAt":   "2025-05-14T14:40:50Z",
    "durationS": 1122.4,
    "lapCount": 0,
    "bestLapS": null,
    "topSpeedMps": 78.9,
    "distanceM": 23420,
    "trackId": null,
    "summary": "Free roam · mostly mountain pass · top speed 284 km/h",
    "closedReason": null,
    "name": "Sunday morning hot lap",
    "bookmarked": true
  }
]
```

Field notes:

- `name` (`string | null`) — user-supplied label for the session, shown in
  the Sessions list and detail header. `null` when the user has not
  renamed the session (UI falls back to the auto-generated summary).
- `bookmarked` (`bool`) — pin marker. Always present, defaults to `false`.
- `trackId` (`string | null`) — inferred-track id (`open_world`, learned
  cluster id, etc.). The track *display* name lives on
  `GET /api/track/current`; sessions only carry the id. `null` for
  free-roam runs before any cluster is matched.
- `closedReason` (`string | null`) — one of `"car_change"`, `"silence"`,
  `"shutdown"`, `"restart_finalize"`, `"not_in_event"` for closed
  sessions, `null` for the in-flight one.
- `styleDriftDelta` is **not** on list items — it's only on
  `GET /api/sessions/:id` (detail) because computing it needs the
  full session frame projection.

### `GET /api/sessions/:id`
Full session detail. Returns a `SessionDetailResponse`: every
`SessionListItem` field above, plus

```json
{
  "...": "all SessionListItem fields",
  "styleDriftDelta": { "smooth": 0.12, "brave": -0.04 },
  "lapRollups": [
    { "lap": 1, "timeS": 70.41, "sectorTimes": [22.3, 28.5, 19.6],
      "topSpeedMps": 78.9, "avgThrottle": 0.62, "avgBrake": 0.18 }
  ],
  "perCornerStats": [],
  "callouts": [
    { "id": "c_8e7a3b", "atS": 134.9, "priority": "tip",
      "text": "Brake later into T3" }
  ],
  "timeline10hz": [
    { "t": 0.0, "speed": 12.4, "throttle": 0.0, "brake": 0.10 }
  ],
  "events": [
    { "atS": 12.4, "kind": "session_started", "payload": { "...": "..." } }
  ]
}
```

- `perCornerStats` is always `[]` today — per-corner aggregation lands
  with the corner-detection model (US5/US6).
- `events` is the historical event log persisted by
  `PgSessionEventsRepository`; same `kind` set as the live WS `event`
  messages but replayed in chronological order.

### `GET /api/sessions/:id/driver-profile`
Builds the driver fingerprint from this session alone (vs the
cumulative `/api/driver/profile`). Returns the same
`DriverProfileResponse` shape as §5 so the Driver page can compare
session-scope to all-time. `404 not_found` if `:id` is unknown.

### `GET /api/sessions/:id/frames`
Query params: `?from=...&to=...&hz=10|30|60&fields=speed,throttle,position`
Returns a packed time-series so the UI can scrub. **Important**: support `fields=` projection so we don't ship a fat payload for a 30-minute session.

Supported fields today (full `SUPPORTED_FIELDS` set, see
`application/use_cases/get_session_frames.py:26`): `speed`, `throttle`,
`brake`, `position`, `rpm`, `gear`, `currentLapS`, `lastLapS`, `bestLapS`,
`gripBudget`, `acceleration` (`[x, y, z]`), `tireTemp`
(`[fl, fr, rl, rr]` normalised-window values). The default projection
(when `fields=` is omitted) is still the first four — the remaining fields are
opt-in so existing callers (e.g. the world-map heatmap) aren't forced to ship a
bigger payload. The widget-redesign additions (`currentLapS`/`lastLapS`/
`bestLapS`, `gripBudget`, `acceleration`, `tireTemp`) were introduced so the
LapTimer, GripBudget, GMeter, and TireHeatmap widgets follow the scrubber in
replay mode instead of flatlining.

Unknown fields return `400 validation_failed` with `field: "fields"`.
**Known bug:** the current handler's `supported=` list on that error
only enumerates the default four — Phase 3 ticket: surface the full
`SUPPORTED_FIELDS` set (`sessions_router.py:208`).

```json
{
  "sessionId": "...",
  "hz": 10,
  "fields": ["speed", "throttle", "brake", "position"],
  "data": [
    [0.0, 12.4, 0.0, 0.1, [12843.6, 312.4, -5421.9]],
    [0.1, 12.8, 0.2, 0.0, [12843.7, 312.4, -5421.6]],
    ...
  ]
}
```

### `PATCH /api/sessions/:id`
Rename a session and/or toggle its bookmark from the Sessions list.

Request body (both keys optional; send only what you're changing):

```json
{ "name": "Sunday morning hot lap", "bookmarked": true }
```

- `name` (`string | null`) — new label. An empty or whitespace-only string
  CLEARS the label back to `null` so the UI falls back to the
  auto-generated summary.
- `bookmarked` (`bool`) — pin / unpin. Changing this re-sorts the list on
  the next `GET /api/sessions`.

Response: the updated session as a `SessionListItem` (same shape as
elements of `GET /api/sessions`). `404 not_found` if `:id` is unknown.

### `DELETE /api/sessions/:id`
Delete one session. Used by the Sessions page "remove" action.

### `DELETE /api/sessions` (gated)
Clear every session row (and their frame projections). The Sessions page
calls this for "delete all sessions". Requires header
`X-Confirm-Clear-All: yes`; without it the server returns `400` with
`error: "confirmation_required"`. With the header, the response is
`204 No Content` and the table is empty afterwards.

Note: the in-flight session (if any) is recreated on the next telemetry
packet — same behaviour as the per-car wipe endpoints — so the only
observable effect on live capture is that the current stream restarts
under a fresh session id.

---

## 4. Cars — `/api/cars`

A car ID is opaque from the dashboard's perspective. It can be derived from `carOrdinal + tune-hash` or whatever you want; just be stable.

### `GET /api/cars`

The wire-level field names below diverged from the spec during
implementation (short, opaque keys to keep payloads tight). The
frontend `CarSummary` type mirrors these names; `apps/web` consumes
them directly.

```json
{
  "cars": [
    {
      "id": "car_lambo_svj_2025",
      "display": "Lambo Aventador SVJ",
      "short": "Lambo SVJ",
      "ordinal": 2451,
      "class": "S",
      "pi": 920,
      "drivetrain": "AWD",
      "group": 13,
      "groupLabel": "Modern Supercars",
      "lastSeenAt": "2025-05-14T14:40:50Z",
      "sessionCount": 9,
      "totalSecondsDriven": 15120,
      "bestLapByTrack": []
    }
  ]
}
```

Field mapping vs the original spec:

| Wire key | What it is |
|---|---|
| `display` | Full display name (was `displayName`) |
| `short` | Short / dropdown label (was `shortName`) |
| `ordinal` | FH6 car ordinal (was `carOrdinal`) |
| `class` | `"D" \| "C" \| "B" \| "A" \| "S" \| "R" \| "P" \| "X"` (was `carClass`) |
| `pi` | Performance index (was `performanceIndex`) |
| `group` | FH6 `CarGroup` int (was `carGroup`) |
| `groupLabel` | Human-readable group name from the bundled lookup table (FR-020); `null` when unknown |
| `bestLapByTrack` | List of `{trackId, bestLapS}` — **always `[]` today**. Population lands with cross-session best aggregation; UI must tolerate the empty list. |

### `GET /api/cars/:id/aggregate`
This is the **live = aggregate-over-all-sessions** view. The dashboard's Live page reads this on car-change to seed its baselines.

```json
{
  "carId": "car_lambo_svj_2025",
  "lapsTotal": 412,
  "sectorBests": [
    { "sector": 1, "bestS": 22.10 },
    { "sector": 2, "bestS": 28.41 },
    { "sector": 3, "bestS": 17.91 }
  ],
  "perCornerAverages": [
    { "corner": "T1", "avgEntrySpeedMps": 38.2, "avgApexSpeedMps": 22.4, "avgExitSpeedMps": 32.0 },
    { "corner": "T3", "avgEntrySpeedMps": 36.1, "avgApexSpeedMps": 24.0, "avgExitSpeedMps": 30.5 }
  ],
  "shift": { "smoothnessUp": 0.82, "smoothnessDown": 0.61, "revMatch": 0.45 },
  "tirePeakUseByCorner": [
    { "corner": "T3", "peakTemp": 96.4 }
  ],
  "preferredGearByCorner": [
    { "corner": "T1", "gear": 3 },
    { "corner": "T3", "gear": 2 },
    { "corner": "T8", "gear": 4 }
  ],
  "gripBudgetCeiling": 0.86,
  "thisCarSpecificStyle": {
    "earlyBrakingInHeavyCars": 0.71
  }
}
```

Reshape notes:

- `sectorBests`, `perCornerAverages`, `preferredGearByCorner`, and
  `tirePeakUseByCorner` are **lists** of typed objects, not objects
  keyed by sector/corner name. List-form makes contract-test
  iteration simpler and survives the open-set of corner ids the
  inferred-track service produces.
- `perCornerAverages` carries `avgEntrySpeedMps` / `avgApexSpeedMps` /
  `avgExitSpeedMps`; the original spec's `timeLost_s` is not produced
  yet (waits on optimal-line synthesis).
- `shift` and `thisCarSpecificStyle` are open `{str: float}` maps
  whose keys can grow as more derivations land.

### `PATCH /api/cars/:ordinal`
Crowdsource a corrected human-readable name for a car. Forza's UDP
packet only emits the integer `carOrdinal`; the server seeds new rows
from a bundled community ordinal → name table (legacy FM/FH plus an
FH6 overlay), but the table will always lag behind Playground's
car-pack drops. When a user sees a placeholder like `Car #2451` they
PATCH the ordinal with the real name; every `cars` row sharing that
ordinal (across tunes / PI variants) is updated, and the DB row is
authoritative for subsequent reads — later ingests do not overwrite a
user-supplied name.

Request body accepts either `displayName` (camelCase, canonical) or
`display_name` (snake_case alias). `shortName` is derived by stripping
the leading year ("2005 Ferrari FXX" → "Ferrari FXX").

```json
{ "displayName": "Lamborghini Huracán Tecnica" }
```

Response:
```json
{
  "ordinal": 2451,
  "displayName": "Lamborghini Huracán Tecnica",
  "shortName": "Huracán Tecnica",
  "updated": 1
}
```

Errors: `404 not_found` (`resource: "car_ordinal"`) if no car with that
ordinal has been ingested yet (the lookup table is the only data source
until a packet arrives), and also `404 not_found` if `displayName` is
empty / whitespace-only. (Implementation treats "no rows to update" the
same way as "ordinal unknown"; a 422 distinction is not produced today.)

### `DELETE /api/cars/:id/sessions`
Wipe all sessions for one car (closed and open alike — see note below).
Confirmed by UI. Idempotent: unknown `:id` still returns `204`. The car
row itself stays in the dropdown — use `DELETE /api/cars/:id` to remove it.

### `DELETE /api/cars/:id`
Remove the car row entirely. Sessions, frames, and mistakes for that car
cascade via FK (`ON DELETE CASCADE`, migration `0003_car_fks_cascade`),
so the car disappears from the dropdown and all of its driving history
goes with it. Idempotent: unknown `:id` still returns `204`.

### `DELETE /api/data/all` (gated)
Nuke everything: every car row, and via FK cascade every session, frame,
and mistake. The cars dropdown is empty afterwards. UI shows a destructive
confirm. Requires `X-Confirm: true` header; without it the server returns
`400` with `error: "confirmation_required"`.

> All three delete endpoints remove sessions regardless of `ended_at`. The
> single in-flight session held in memory by `SessionManager` will be
> re-created on the next packet (sessions are upserted), so the only
> observable side-effect of deleting a live session is that the current
> stream restarts under a fresh session id — and, for `DELETE /api/cars/:id`
> or `/data/all`, under a freshly-created car row as well. A periodic
> background sweeper finalizes any open session that's been silent past
> the silence threshold, so abandoned rows never accumulate to confuse
> future bulk deletes.

---

## 5. Driver profile — `/api/driver`

The driver fingerprint, learned over time across all cars.

### `GET /api/driver/profile`
```json
{
  "lapsAnalyzed": 412,
  "distanceAnalyzedM": 1284350.0,
  "secondsAnalyzed": 41220.5,
  "fingerprint": {
    "smooth":   0.78,
    "brave":    0.55,
    "early":    0.38,
    "patient":  0.62,
    "precise":  0.82,
    "consist":  0.50
  },
  "fingerprintBaseline90d": {
    "smooth": 0.55, "brave": 0.55, "early": 0.55, "patient": 0.55, "precise": 0.55, "consist": 0.55
  },
  "traits": [
    { "id": "late_braker", "name": "Late braker", "score": 0.86, "blurb": "..." },
    { "id": "smooth_hands", "name": "Smooth hands", "score": 0.78, "blurb": "..." }
  ],
  "strengths": ["smooth steering", "trail-braking", "throttle on exit"],
  "weaknesses": ["slow corners", "downshift timing", "tight chicanes"],
  "carAgnosticShare": 0.72,
  "persona": "You're a smooth late-braker who likes to muscle the throttle on corner exit. Properly quick in fast sweepers, a bit rough in slow technical stuff — but your consistency is genuinely getting better.",
  "personaUpdatedAt": "2025-05-13T00:00:00Z",
  "modelVersion": "fingerprint-v1"
}
```

Field notes:

- `distanceAnalyzedM`, `secondsAnalyzed`, `modelVersion` are required
  (added with the analyzed-stats migration `0009`).
- `fingerprintBaseline90d` is camelCase, **no underscore** — the
  90-day baseline against which the current fingerprint deltas are
  shown.
- `traits` keys (`id`, `name`, `score`, `blurb`) are stable; the trait
  set is open and evolves as new detectors land.

### `GET /api/driver/evolution?days=90`
Returns time-series of trait scores so the Driver page can plot them.

Series is keyed by the same six fingerprint traits as `/api/driver/profile`:
`smooth, brave, early, patient, precise, consist`. Each entry is a list of
`[unix_timestamp_seconds, value]` pairs.

```json
{
  "days": 90,
  "series": {
    "smooth":  [[1747526400, 0.78], [1748131200, 0.79]],
    "brave":   [[1747526400, 0.55], [1748131200, 0.55]],
    "early":   [[1747526400, 0.38], [1748131200, 0.38]],
    "patient": [[1747526400, 0.62], [1748131200, 0.63]],
    "precise": [[1747526400, 0.82], [1748131200, 0.82]],
    "consist": [[1747526400, 0.50], [1748131200, 0.52]]
  },
  "sessionClusters": []
}
```

Caveats:

- **Series is synthesised today** — `driver_router.py:81-95` stamps the
  current fingerprint at past timestamps stepping back through `days`.
  Real per-session history requires persisted per-session profiles
  (follow-up beyond Phase 3).
- `sessionClusters` is a list of `{sessionId, fingerprint}` for the
  Driver page's planned per-session scatter; empty today.

---

## 6. Predictions — `/api/predict`

All predictions return a **value, confidence, and the inputs used**. The
UI shows confidence bands on every prediction — never quote a number
without one. Several endpoints share a common `PredictionEnvelope` shape:

```ts
type PredictionEnvelope = {
  kind: "finish" | "crashRisk" | "bestAchievableLap"; // discriminator
  value: number;
  confidence: number;          // 0..1
  toleranceBand: number;       // ±band around `value` in the same units
  modelVersion: string;
  inputs: string[];
};
```

`sessionId` is a required query param on every `/api/predict/*` route
except `whatIf` (which takes it in the body); a `404 not_found`
(`resource: "session"`) is returned for unknown ids.

### `GET /api/predict/lap?sessionId=live&n=3`
Project the next `n` lap times (`n` defaults to 3, max 10).

```json
{
  "predictedAt": 134.9,
  "modelVersion": "lap-residual-v2.1",
  "predictions": [
    { "lap": 9,  "time_s": 68.6, "lower_s": 68.2, "upper_s": 69.0, "confidence": 0.78 },
    { "lap": 13, "time_s": 69.4, "lower_s": 68.3, "upper_s": 70.5, "confidence": 0.52 }
  ],
  "limiter": null,
  "inputs": ["best_lap_s", "lap_count", "raceTimeS"]
}
```

- `predictedAt` is `raceTimeS` from the latest hot-cache frame; `0.0`
  when no frame has arrived yet (callers should treat 0.0 as "no live
  frame yet").
- `predictions` is empty on a cold session (`best_lap_s IS NULL`).
- Confidence is monotone non-increasing across `k` (capped at the
  first projection's value and decayed by 0.9 per lap).
- `limiter` is `null` today — tire-wear gating is a follow-up.

### `GET /api/predict/fuel`
**Not implemented.** Forza games emit `Fuel` at offset 288 of the UDP
packet but the tank never actually depletes during gameplay (see
`DOCS.md §5` byte 288). The endpoint was specified for parity with the
dashboard mock; building a real model would always read constant. Don't
gate UI features on it; the Live page's fuel widget renders from
`frame.engine.fuel` directly.

### `GET /api/predict/tireFailure?sessionId=live`
```json
{
  "perCorner": {
    "fl": { "wear": 0.31, "failureAtLap": 24, "confidence": 0.78 },
    "fr": { "wear": 0.34, "failureAtLap": 22, "confidence": 0.78 },
    "rl": { "wear": 0.48, "failureAtLap": 15, "confidence": 0.78 },
    "rr": { "wear": 0.53, "failureAtLap": 13, "confidence": 0.78 }
  },
  "limitingCorner": "rr",
  "modelVersion": "tire-wear-v0-slip-energy",
  "inputs": ["modeled.tireWear", "session.lap_count"]
}
```

`failureAtLap` is `null` in free-roam sessions or before any lap has
completed. `limitingCorner` falls back to the worst-wear corner if no
projected failure exists; `null` if every wear value is 0.

### `GET /api/predict/finish?sessionId=live`
Envelope shape (`kind: "finish"`). `value` is the projected finishing
position (1 = leader).

```json
{
  "kind": "finish",
  "value": 2.0,
  "confidence": 0.62,
  "toleranceBand": 1.0,
  "modelVersion": "finish-baseline-v1",
  "inputs": ["current_position", "gap_to_leader_s", "laps_remaining"]
}
```

The richer "overtake plan" shape from earlier drafts
(`{position, wasPosition, overtake: {...}}`) is **not** produced today —
it requires a per-AI-rival model. Future model upgrade; the envelope
shape is the binding contract.

### `GET /api/predict/crashRisk?sessionId=live`
Envelope shape (`kind: "crashRisk"`). `value` is the risk fraction
(0..1).

```json
{
  "kind": "crashRisk",
  "value": 0.12,
  "confidence": 0.61,
  "toleranceBand": 0.10,
  "modelVersion": "crash-risk-baseline-v1",
  "inputs": ["avg_combined_slip", "smashable_velocity_diff", "speed_mps"]
}
```

The `elevatedReason` / `etaCorner` / `withinLaps` enrichment from
earlier drafts is **not** produced today — the baseline model only
emits a scalar risk. Future model upgrade.

### `GET /api/predict/bestAchievableLap?sessionId=live`
Envelope shape (`kind: "bestAchievableLap"`). `value` is the projected
best-achievable lap time in seconds (the "if you fixed your mistakes"
lap).

```json
{
  "kind": "bestAchievableLap",
  "value": 67.20,
  "confidence": 0.70,
  "toleranceBand": 0.45,
  "modelVersion": "best-achievable-lap-baseline-v1",
  "inputs": ["sector_best_times"]
}
```

The `fixes: [...]` list from earlier drafts is **not** produced today —
it requires the mistake-attribution model. Future model upgrade; the
envelope shape is the binding contract.

### `POST /api/predict/whatIf`
Counter-factual simulator (Predictions page V3).

```json
// request
{
  "sessionId": "live",
  "from": 0.0,
  "to": 60.0,
  "tweaks": [
    { "kind": "brake_point_offset",  "delta": 10.0 },
    { "kind": "throttle_smoothness", "delta": 0.2 }
  ]
}
// response
{
  "sessionId": "live",
  "lapDeltaS": -0.74,
  "confidence": 0.62,
  "toleranceBand": 0.20,
  "modelVersion": "what-if-baseline-v1",
  "perTweak": [
    { "kind": "brake_point_offset",  "deltaS": -0.34 },
    { "kind": "throttle_smoothness", "deltaS": -0.40 }
  ],
  "replayId": "cf_8e7a3b"
}
```

Request notes:

- `sessionId` is required. `from` / `to` are session-relative seconds;
  defaults are `0.0` / `60.0`.
- `tweaks[].kind` is a closed set: `brake_point_offset`,
  `throttle_smoothness`, `apex_offset`, `shift_timing_offset`
  (`WHAT_IF_TWEAK_KINDS` in `domain/entities/replay.py`). Unknown kinds
  return `400 validation_failed` with the supported list under
  `supported`.
- Per-corner addressing (`corner`, `deltaMeters`) is **not** produced
  today — tweaks are scalar magnitudes applied across the simulated
  window.

Response notes:

- `perTweak` reports per-tweak deltas keyed by `kind`. (Earlier draft's
  `perTweakDelta_s: [floats]` was index-positional; the named shape
  survives reordering and the closed-kind set.)
- `replayId` is the id of a stored counter-factual replay — call
  `GET /api/replay/:id` to fetch the projected frames.
- `warnings` from earlier drafts is **not** produced today; the
  cross-correlation note ("combined delta is correlated; per-tweak sum
  > total") will land with the explainer follow-up.

---

## 6b. Shift predictions — `/api/predict/shift*`

Landed post-spec as FR-021 (predict) / FR-022 (report) / FR-023 (reset).
Router: `interfaces/rest/shift_router.py`. All routes accept
`sessionId="live"` to resolve the latest in-flight session.

### `GET /api/predict/shift?sessionId=live`
Current shift recommendation for the session's engine fingerprint.

```json
{
  "fingerprint": {
    "carOrdinal": 2451,
    "performanceIndex": 920,
    "numCylinders": 12
  },
  "byGear": { "1": 7100, "2": 7200, "3": 7250, "4": 7250, "5": 7200, "6": 7100 },
  "confidenceByGear": { "1": 0.72, "2": 0.81, "3": 0.88 },
  "ratios": { "1->2": 1.42, "2->3": 1.31 },
  "ratioConfidenceByGear": { "1->2": 0.80, "2->3": 0.78 },
  "stage": "learned",
  "trainedSampleCount": 4210,
  "lastUpdated": "2025-05-14T14:40:50Z",
  "confidence": 0.81,
  "inputs": ["engine.torque_nm", "engine.rpm", "engine.boost_psi", "motion.speed_mps", "drivetrain.gear", "inputs.throttle", "wheels.*.combinedSlip", "world.carOrdinal", "world.performanceIndex"],
  "modelVersion": "shift-v1"
}
```

`stage` is `"learned" | "prior" | "fallback"`. `404 not_found`
(`resource: "frame"`) when no hot-cache frame has arrived yet for the
session.

### `GET /api/predict/shift/report?sessionId=live`
Per-session shift report aggregated from `shift_events_clean`.

```json
{
  "sessionId": "s_...",
  "totalShifts": 41,
  "cleanShifts": 41,
  "avgDeltaRpm": -120.4,
  "byGearPair": {
    "1->2": { "n": 7,  "avgDeltaRpm": -80.0,  "avgEstCostS": 0.04, "direction": "up" },
    "3->2": { "n": 4,  "avgDeltaRpm": 50.0,   "avgEstCostS": 0.06, "direction": "down" }
  },
  "estTotalCostS": 1.84,
  "modelVersion": "shift-v1",
  "assistInterventionPct": 0.04
}
```

`assistInterventionPct` is the session-lifetime assist-intervention
fraction in `[0, 1]`, sourced from the in-memory predictor for
`sessionId=live`; `0.0` for historical sessions because the assist
counter is not persisted between process restarts.

### `POST /api/predict/shift/reset`
Drop in-memory + on-disk state for a fingerprint. Body accepts EITHER
`{sessionId}` (resolves the fingerprint from the live frame) OR a full
`{carOrdinal, performanceIndex, numCylinders}` triplet.

```json
// request (either form)
{ "sessionId": "live" }
{ "carOrdinal": 2451, "performanceIndex": 920, "numCylinders": 12 }

// response
{
  "deleted": {
    "engineCurves": 1,
    "gearRatios": 8,
    "shiftEvents": 41,
    "transmissionModes": 1
  }
}
```

`400 validation_failed` if neither form is satisfied.

---

## 7. AI Coach — `/ws/coach` + `/api/coach`

The coach has two modes:

### A. Live push — `/ws/coach`
Server analyzes the telemetry stream and pushes call-outs when it has
something worth saying.

On connect the server sends a hello frame carrying current availability:

```json
{
  "type": "hello",
  "server": "fh6-backend/0.1.0",
  "coach": { "available": true, "reason": null, "model": "claude-haiku-4-5" }
}
```

Then callouts as they're produced:

```json
{
  "type": "callout",
  "id": "c_8e7a3b",
  "atS": 134.9,
  "priority": "tip",
  "lap": 7,
  "corner": "T11",
  "text": "Slid out at 11 a few times now. You're picking up the throttle while the wheel's still cranked over — give it a beat to come straight first.",
  "cites": [
    { "kind": "telemetry_window", "from": 132.4, "to": 132.6, "fields": ["slipRatio.rr","throttle","steer"] }
  ],
  "modelVersion": "coach-haiku-4-5",
  "voice": "friendly_codriver"
}
```

Notes on the callout payload:

- `atS` (was `at` in earlier drafts) — seconds since session start.
- `lap` + `corner` are flat top-level fields, not nested under
  `lapContext`.
- `priority` is `"tip" | "info" | "warn"`.

The connection also receives periodic `{type:"heartbeat", at:…}` frames
during quiet periods (same etiquette as `/ws/live`).

**Cool-down policy** (server enforces):
- Same `kind` of callout: silent for **30s** after a mention.
- Same `corner`: silent for **one lap** after a mention.
- Max **one callout every 8s** of speech mode is enabled.
- Priority order if competing: warn > tip > info.

### B. Q&A — `POST /api/coach/ask`
Used by the chat input in the Coach page.

```json
// request
{ "sessionId": "s_2025-05-14T...", "question": "Why am I slow in sector 2?" }
```

Response: **chunked `text/event-stream`** streaming raw UTF-8 text as
the LLM produces it. The body is the answer text directly — there is no
JSON envelope and no per-chunk delimiter beyond what
`text/event-stream` defines at the transport layer. Citations are not
yet on the wire; once they land they'll arrive on a separate event
type within the stream.

The earlier draft's `{answer, cites}` JSON response is **not** what
ships today — the streaming bare-text shape is. Clients should consume
the stream incrementally and render tokens as they arrive.

`404 not_found` if `sessionId` is unknown.

### `GET /api/coach/status`
Coach availability for the Q&A and live-push surfaces. The service
starts normally even when `claude` is missing/unauthenticated (Q3);
this endpoint exposes the current state:

```json
{ "available": true,  "reason": null,                  "model": "claude-haiku-4-5" }
{ "available": false, "reason": "claude CLI not found", "model": null }
```

Availability is rechecked on **each** call (not cached). The
`/ws/coach` hello carries the same shape; callouts are suppressed
when `available: false`.

### `GET /api/coach/insights?sessionId=...`
The "priority insight cards" view (Coach page V2). Returns the top N
insights for the session, scored.

```json
{
  "insights": [
    {
      "id": "...",
      "sessionId": "s_...",
      "priority": "high",
      "title": "Ease off the throttle stab",
      "body": "...",
      "tone": "warn",
      "actions": ["replay", "dismiss", "explain_more"],
      "deltaIfFixedS": 0.20,
      "replayId": "tc_8e7a3b"
    }
  ]
}
```

- `priority` is `"high" | "medium" | "low"`; `tone` is
  `"tip" | "info" | "warn"`.
- `deltaIfFixedS` is camelCase (was `deltaIfFixed_s` in earlier drafts).
- `replayId` points at a stored telemetry-clip replay; `null` until the
  user has materialised one via `POST /api/coach/insights/:id/replay`.

### `POST /api/coach/insights/:id/dismiss`
User dismissed the card. Returns `204 No Content`. Idempotent —
dismissing an already-dismissed insight is a 204 too.

### `POST /api/coach/insights/:id/replay`
Materialise a telemetry-clip replay for the insight's cited window.
Returns the replay id; the caller follows up with `GET /api/replay/:id`
to fetch the frames.

```json
{ "replayId": "tc_8e7a3b" }
```

**Stub-window caveat:** insight citations don't encode `from_s`/`to_s`
yet, so today the handler builds a fixed `[0.0, 10.0]` clip from the
session origin (`coach_router.py:84-93`). Real citation windows land
when insight generation persists `cites[].from`/`to`.

### `POST /api/coach/insights/:session_id/generate`
Manual trigger for insight generation (used by tests + a "regenerate"
button on the Coach page). Runs the `GenerateInsights` use case for the
session and returns the count of insights produced.

```json
{ "generated": 4 }
```

`201 Created` on success, `404 not_found` if `session_id` is unknown.

---

## 8. Track & line — `/api/track`

### `GET /api/track/current`
The current track / map context. Forza Horizon doesn't ship a track
ID, so the backend infers it from position clustering — be explicit
about that.

```json
{
  "trackId": "open_world",          // or a learned cluster id like "track_inferred_3"
  "displayName": "Mountain pass · NE",
  "inferred": true,
  "confirmedName": null,            // user-provided override (FR-019b); null = use displayName
  "confirmedAt": null,              // ISO timestamp of the override
  "outline": [ [x,y] ],
  "corners": [
    { "id": "T1", "apex": [x,y], "entry": [x,y], "exit": [x,y], "gear_recommended": 3 }
  ]
}
```

`confirmedName` / `confirmedAt` exist for a future "I know what track
this is" override flow; both are `null` today.

### `GET /api/track/optimal-line?sessionId=...`
Returns the recorded line + the AI-computed optimal line for the
session.

```json
{
  "sessionId": "s_...",
  "trackId": "open_world",
  "optimalLine": [
    { "t": 0.0, "x": 12843.6, "y": -5421.9, "speed": 12.4, "throttle": 0.0, "brake": 0.1 }
  ],
  "yourLine": [
    { "t": 0.0, "x": 12843.6, "y": -5421.9, "speed": 12.4, "throttle": 0.0, "brake": 0.1 }
  ],
  "incidents": [
    { "atS": 132.6, "kind": "oversteer", "text": null }
  ],
  "sectorDeltas": [
    { "sector": 0, "deltaS": 0.0 }
  ]
}
```

Shape notes:

- `optimalLine` / `yourLine` are arrays of named-field objects (`t, x,
  y, speed, throttle, brake`), not `[x,y,t]` triplets.
- Today `optimalLine === yourLine` and `sectorDeltas` is a single
  zero-delta sector (`track_router.py:46-50`). Real synthesis lands
  with the lap-residual + corner-detection models (US5/US6); the shape
  above is the binding contract that survives that change.
- `incidents` carries `atS` (session-relative seconds) + `kind` + an
  optional `text`. The earlier `{pos, lap, corner}` shape is **not**
  produced today.
- `sectorDeltas` is a list of `{sector, deltaS}` — `sector` is the
  integer sector index (0-based today). The earlier
  `sectorDeltas_s: {S1: ..., S2: ..., S3: ...}` object form is **not**
  produced; the list form survives variable sector counts.

### `GET /api/track/mistakes?carId=...&trackId=...`
The mistakes heatmap. Aggregated over all sessions on
inferred-same-track. `trackId` is optional — omit it to aggregate
across every track for the car.

```json
{
  "carId": "car_lambo_svj_2025",
  "trackId": null,
  "buckets": [
    { "pos": [12843.6, -5421.9], "kind": "wide_apex", "count": 14, "corner": "T3" }
  ],
  "breakdown": [
    { "kind": "oversteer_exit",  "count": 62 },
    { "kind": "apex_missed_wide", "count": 78 }
  ],
  "trend": [
    { "dayIso": "2026-04-24", "count": 23 },
    { "dayIso": "2026-04-25", "count": 18 }
  ]
}
```

Shape notes:

- `mistakes` was renamed to **`buckets`** (the spec word "mistakes"
  clashed with the route name).
- `breakdown` is a list of `{kind, count}` instead of the earlier
  `{kind: fraction}` object; the count form composes cleanly with
  windowed queries.
- `trend` is a per-day series of `{dayIso, count}` rather than the
  earlier `{perLap_30d_ago, perLap_now, delta}` summary; the UI
  computes deltas client-side.
- **Empty today.** Buckets/breakdown/trend are all `[]` until mistake
  detectors (US3 + event detectors in US1) persist rows.

---

## 9. Replay — `/api/replay/:id`

Counter-factual or cited replays. The dashboard renders these in the
Predictions page (what-if) and on coach bubble "replay" actions.

```json
{
  "id": "cf_8e7a3b",
  "kind": "counter_factual",
  "sessionId": "s_2025-05-14T...",
  "from": 132.0,
  "to": 138.0,
  "frames": [ /* 30Hz time-series with the fields the player UI needs */ ],
  "annotations": [
    { "at": 133.4, "kind": "ghost_brake_earlier", "text": "AI brakes here" }
  ],
  "tweaks": [ { "kind": "brake_point_offset", "delta": 10.0 } ],
  "createdAt": "2025-05-14T14:25:18Z"
}
```

- `kind` is `"counter_factual" | "telemetry_clip"`.
- `sessionId` is required (added so the UI can deep-link back to the
  parent session without a follow-up request).
- `tweaks` is `null` on telemetry-clip replays; populated for
  counter-factuals with the same `WhatIfTweak` shape as
  `POST /api/predict/whatIf`.
- `createdAt` is optional (some legacy replays predate the column).
- `from` / `to` are serialised via Pydantic aliases — the field names
  on the request/response wire are the bare `"from"` / `"to"` strings.

---

## 9b. Telemetry health — `/health/telemetry`

Surfaces the UDP listener's bind status so the UI can explain a silent
live stream (port collision, permission denied, etc.) instead of just
showing "no frames". The server keeps running on bind failure: the rest
of the REST/WS surface stays up.

### `GET /health/telemetry`
```json
{
  "listening": true,
  "host": "127.0.0.1",
  "port": 5302,
  "bind_error": null,
  "last_packet_at": "2026-05-18T14:22:08.812Z"
}
```

On bind failure:
```json
{
  "listening": false,
  "host": "127.0.0.1",
  "port": 5302,
  "bind_error": "[Errno 98] Address already in use",
  "last_packet_at": null
}
```

When `bind_error` is non-null, new subscribers to `/ws/live` also receive
a one-shot `{"type": "udp_bind_failed", "message": "..."}` frame right
after `hello`.

---

## 10. Settings — `/api/settings`

UI-driven config that should persist on the backend (so the same player can use the dashboard from multiple machines if they want).

### `GET /api/settings`
```json
{
  "telemetry": {
    "listenAddr": "127.0.0.1",
    "listenPort": 5302,
    "gameProfile": "fh6",
    "autoDetectCadence": true,
    "preferredFrameRate": 30
  },
  "models": {
    "llmCoach": true,
    "tireWearModel": true,
    "shiftCoach": true,
    "predictions": true,
    "drivingFingerprint": true,
    "voiceCallouts": false,
    "minCoachPriority": "tip"           // "info" | "tip" | "warn"
  },
  "data": {
    "recordSessions": true,
    "storeRawPackets": false,
    "retentionDays": 90,
    "shareAnalytics": false,
    "maxBytesPerCar": 5368709120        // 5 GB default; floor 100 MB; Clarification Q2 / FR-039a
  },
  "display": {
    "speedUnit": "kmh",                  // "kmh" | "mph"
    "tempUnit": "c",                     // "f" | "c"
    "reduceMotion": false,
    "theme": "dark"                      // "dark" | "light" — light wiring is a Phase 6 follow-up
  },
  "worldMap": {
    "calibration": {
      "aWorld": [-119.49, 3888.60],     // FH6 world (X, Z) at reference point A
      "aPix":   [2089486, 2087415],     // tile-pyramid (X, Y) at A's native (max) zoom
      "bWorld": [-7104.77, -1863.08],
      "bPix":   [2086885, 2089556]
    }
  },
  "perCarOverrides": [
    { "carId": "car_lambo_svj_2025", "layoutId": "lambo_live" },
    { "carId": "car_ford_bronco",    "presetId": "offroad" }
  ]
}
```

`PATCH /api/settings` — partial updates. Toggle endpoints in the UI just send the changed keys.

`worldMap.calibration` is `null` until the user runs the `world_map` widget's
in-place calibration tool (capture A's world coords from a live telemetry
frame, click pixel A on the map, repeat for B). The widget derives an
independent per-axis linear transform from the four pairs:
`pixelX = mX·worldX + bX`, `pixelY = mZ·worldZ + bY`, where `mX, bX` come
from the two X-axis pairs and `mZ, bY` from the two Z-axis pairs. The Z
axis carries its own sign so the reflection between world Z (north) and
pixel Y (south) is handled without a rotation term. PATCH replaces the
whole `calibration` sub-object — partial fills are rejected.

---

## 11. Layouts & widgets — `/api/layouts`

The Customize page is a build-your-own-page widget grid. The backend
stores layouts per page per user; the UI is the authority on widget
rendering.

### `GET /api/layouts/:pageId`

`pageId` is a closed set: `live`, `sessions`, `coach`, `predictions`,
`driver`, `track`, `customize`, `settings`. Anything else returns
`400 validation_failed` with `field: "pageId"` and the supported list.

```json
{
  "pageId": "live",
  "name": "My Live",
  "grid": { "cols": 12, "rowHeight": 40 },
  "widgets": [
    { "id": "w_speed",   "kind": "speed_dial",   "x":0,"y":0,"w":3,"h":3, "props":{} },
    { "id": "w_rpm",     "kind": "rpm_tape",     "x":3,"y":0,"w":6,"h":2 },
    { "id": "w_map",     "kind": "world_map",    "x":9,"y":0,"w":4,"h":4 },
    { "id": "w_coach",   "kind": "coach_feed",   "x":0,"y":3,"w":4,"h":3 },
    { "id": "w_predict", "kind": "lap_predict",  "x":4,"y":3,"w":3,"h":2 },
    { "id": "w_tires",   "kind": "tire_heatmap", "x":7,"y":3,"w":3,"h":3 }
  ],
  "updatedAt": "2025-05-14T14:25:18Z"
}
```

`grid` defaults are `{cols: 12, rowHeight: 40}`. `updatedAt` is `null`
on a fresh `pageId` that's never been saved.

`PUT /api/layouts/:pageId` — replace the whole layout. `PATCH` to
update partial fields (any subset of `name`, `grid`, `widgets`). Both
validate `widgets[].kind` against the catalog and reject unknowns with
`400 validation_failed`.

### Widget catalog — removed in Phase 3

`GET /api/widgets/catalog` was deleted in Phase 3 (§1.3 #6). The widget
catalog (kind → title / default size / min size) is a UI concern; the
frontend's `widgetRegistry.jsx` is the authoritative source. The
backend still enforces an allow-list when persisting layouts so a
typo doesn't permanently corrupt a saved page — see
[`interfaces/rest/widget_kinds.py`](src/fh6/interfaces/rest/widget_kinds.py).
If the frontend adds a new kind, append it to that file.

---

## 12. FH6 parsing notes the backend MUST get right

These are gotchas from the FH6 Data Out research, repeated so the backend doesn't drop them:

1. **324-byte packet, but documented fields end at offset 322.** Parse all named fields through 322. Preserve byte at offset 323 as `tailReservedByte` — do not crash if you don't recognize it, do not invent meaning for it.
2. **Little-endian** (inferred from FH4/FH5 lineage; FH6 docs don't say). Isolate this assumption in code so it's easy to flip if Microsoft documents otherwise.
3. **Packet cadence = game frame rate** while actively driving. Do NOT assume 60 Hz — read `TimestampMS` deltas and report effective cadence to the UI.
4. **Packet silence is a first-class state**, not a field. The dashboard depends on `stream-paused` transitions to render the idle state.
5. **WheelInPuddle* is a boolean (S32 0/1)** in FH6, not a float depth like FH4/FH5. Don't normalize it as 0..1 depth.
6. **TireWear is not in the packet.** The backend MUST model it — the dashboard expects `modeled.tireWear.{fl,fr,rl,rr}` in every frame.
7. **TrackOrdinal is not in the packet.** Infer track from position clustering and label inferred tracks honestly (`"inferred": true`).
8. **CarGroup enum is not officially published.** Track your own mapping and expose it via `/api/cars/:id` so the UI can show readable names.
9. **Lap fields use `0.0` as "not applicable"** (free roam, before start line). Convert to nullable `null` before sending — the UI treats `null` and `0` differently.
10. **`LapNumber = 0` can be legitimate** (sprints, before start line). Don't treat as missing data.
11. **Avoid binding to ports 5200–5300** for outbound sockets — FH6 binds its own there.
12. **Tire temp units unspecified** — pass the raw value through verbatim and also compute a normalized 0..1 in the optimal window. Let the user pick units in display settings.

---

## 13. Auth & privacy

- Local-first by default. No auth required on `localhost`.
- If exposed beyond loopback: simple token auth via `Authorization: Bearer ...`. Token generated at first launch, displayed in Settings, regeneratable.
- All telemetry stays on device unless `settings.data.shareAnalytics = true`.
- Wipe endpoints (`DELETE /api/sessions/:id`, `/api/cars/:id/sessions`, `/api/data/all`) must be idempotent and actually delete (not soft-delete) when retention policy says so.

---

## 14. Streaming etiquette (UI expectations)

- `frame` messages may be **batched** if rate > 30 Hz. Use `{ "type": "frames", "batch": [frame, frame, ...] }`.
- The UI is allowed to **back-pressure** by sending `{ "type": "rate", "hz": 10 }` mid-stream.
- The server should NEVER buffer more than ~1s of frames; if the UI is slow, drop intermediate frames rather than backing up.
- Send a `{ "type": "heartbeat", "at": ... }` every 5s when there's no other traffic so the UI can detect a dead connection vs. a paused stream.

---

## 15. Minimum viable subset to ship the dashboard

If you want to bring it up incrementally, here's the order:

1. **`/ws/live`** with `frame` + `state` only → unblocks Live page
2. **`/api/cars` + `/api/cars/:id/aggregate`** → unblocks Live page car aggregates + Garage
3. **`/api/sessions` (list + detail + frames@10Hz)** → unblocks Sessions page
4. **`/api/predict/lap` + `/api/predict/tireFailure`** → unblocks Predictions page (`/api/predict/fuel` is documented but not implemented — see §6)
5. **`/ws/coach` push + `POST /api/coach/ask`** → unblocks Coach page
6. **`/api/driver/profile` + `/api/driver/evolution`** → unblocks Driver page
7. **`/api/track/optimal-line` + `/api/track/mistakes`** → unblocks Track page
8. **`/api/settings` + `/api/layouts`** → unblocks Customize + Settings

Anything in `derived.*` and `modeled.*` can ship with placeholders (constant 0) in the `frame` payload at first — the UI will render gracefully but won't be smart yet.