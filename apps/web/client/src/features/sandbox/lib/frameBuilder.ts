// client/src/lib/sandbox/frameBuilder.ts
//
// buildFrame(flat) — given a flat key/value map where keys are dotted paths
// (e.g. "engine.rpm": 6200), produce a nested Frame object matching the
// wire contract.
//
// Also fills in canonical defaults for common fields so widgets don't blow
// up reading frame.engine?.maxRpm when only frame.engine.rpm was set.

const DEFAULT_FRAME: Record<string, unknown> = {
  state: 'driving',
  timestamp: Date.now(),
  motion: {
    speed_mps: 0,
    acceleration: { x: 0, y: 0, z: 0 },
    position: { x: 0, y: 0, z: 0 },
  },
  engine: {
    rpm: 1000,
    maxRpm: 8000,
    idleRpm: 900,
    boost_psi: 0,
    fuel: 1.0,
  },
  drivetrain: {
    gear: 1,
    type: 'AWD',
    clutch: 0,
  },
  race: {
    currentLapS: 0,
    lastLapS: null,
    bestLapS: null,
    position: 1,
    wasPosition: 1,
  },
  wheels: {
    fl: { tireTemp_normWindow: 0.4, combinedSlip: 0, suspensionTravel_norm: 0.5 },
    fr: { tireTemp_normWindow: 0.4, combinedSlip: 0, suspensionTravel_norm: 0.5 },
    rl: { tireTemp_normWindow: 0.4, combinedSlip: 0, suspensionTravel_norm: 0.5 },
    rr: { tireTemp_normWindow: 0.4, combinedSlip: 0, suspensionTravel_norm: 0.5 },
  },
  derived: {
    gripBudgetUsed: 0,
    weightFront: 0.5,
    weightLeft: 0.5,
  },
  modeled: {
    tireWearConfidence: 0,
    tireWear: { fl: 0, fr: 0, rl: 0, rr: 0 },
  },
}

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj)) as T
}

function setPath(obj: Record<string, unknown>, path: string, value: unknown): void {
  const parts = path.split('.')
  let cur: Record<string, unknown> = obj
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i]!
    if (cur[key] == null) cur[key] = {}
    cur = cur[key] as Record<string, unknown>
  }
  cur[parts[parts.length - 1]!] = value
}

export function buildFrame(flat: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const frame = deepClone(DEFAULT_FRAME)
  frame.timestamp = Date.now()
  for (const [path, value] of Object.entries(flat ?? {})) {
    if (path.startsWith('mock.')) continue   // mock.* paths feed apiMocks, not the frame
    // Allow configs to use `frame.X.Y` as a clearer namespace marker; strip
    // the prefix so `frame.carId` sets frame.carId (not frame.frame.carId).
    const realPath = path.startsWith('frame.') ? path.slice(6) : path
    setPath(frame, realPath, value)
  }
  return frame
}
