// Forward trajectory predictor — projects where the car will be over
// the next `horizonS` seconds given the current motion state.
//
// Frame conventions (FH6 Data Out spec — see
// fh6-racer-backend/forza-horizon-telemetry-research.md):
//   - `motion.position`  is WORLD-space (X east, Z north — empirically;
//                        spec only says "world-space", the axis sign is
//                        established by the calibration).
//   - `motion.velocity`  is CAR-LOCAL (x=right, y=up, z=forward).
//   - `motion.angularVelocity.y` is the yaw rate, frame-invariant.
//   - `motion.orientation.yaw` is the heading in radians, increasing
//                        clockwise from world +Z.
//
// To project a world path we have to rotate the car-local velocity
// into world space first; otherwise +Z-local always integrates to
// +Z-world ("north") regardless of where the car is pointing.
//
// World-frame velocity from car-local:
//   forward_world = (sin yaw,  cos yaw)
//   right_world   = (cos yaw, -sin yaw)
//   v_world       = right * v.x + forward * v.z
//                 = ( v.x·cos yaw + v.z·sin yaw,
//                    -v.x·sin yaw + v.z·cos yaw )
//
// Approach: slip-aware bicycle integration. Each step, position
// advances by world-velocity × dt, then the world-velocity vector
// rotates by angular-velocity × dt about world Y. That produces a
// smooth curving arc when the driver is turning and stays correct
// during drift (the velocity vector does not have to align with the
// nose).

import type { MotionBlock } from '@fh-racer/contract/ws'

export interface PredictPathOpts {
  horizonS?: number
  stepS?: number
}

export type WorldPoint = [number, number]

function carLocalToWorld(v: { x: number; z: number }, yaw: number): { x: number; z: number } {
  const c = Math.cos(yaw), s = Math.sin(yaw)
  return {
    x:  v.x * c + v.z * s,
    z: -v.x * s + v.z * c,
  }
}

export function predictPath(motion: MotionBlock | null | undefined, { horizonS = 2.0, stepS = 0.05 }: PredictPathOpts = {}): WorldPoint[] {
  const pos = motion?.position
  const vel = motion?.velocity
  if (!pos || !vel) return []

  const yaw = motion?.orientation?.yaw ?? 0
  const angY = motion?.angularVelocity?.y ?? 0

  // Initial world-frame velocity.
  const v0 = carLocalToWorld(vel, yaw)
  let vx = v0.x, vz = v0.z

  // Per-step rotation matrix (world frame). Heading evolves at angY,
  // so the velocity vector rotates by angY·stepS each tick.
  const c = Math.cos(angY * stepS)
  const s = Math.sin(angY * stepS)

  let x = pos.x, z = pos.z
  const steps = Math.ceil(horizonS / stepS)
  const out = new Array<WorldPoint>(steps + 1)
  out[0] = [x, z]
  for (let i = 1; i <= steps; i++) {
    x += vx * stepS
    z += vz * stepS
    const nvx = c * vx + s * vz
    const nvz = -s * vx + c * vz
    vx = nvx; vz = nvz
    out[i] = [x, z]
  }
  return out
}

// Project a single point `distanceM` meters ahead along the current
// world-frame velocity direction. Returns `null` when motion is too
// slow to define a direction. Used by the brake overlay: the endpoint
// is where the car ends up if the current decel sustains.
export function projectAlongMotion(motion: MotionBlock | null | undefined, distanceM: number): WorldPoint | null {
  const pos = motion?.position
  const vel = motion?.velocity
  if (!pos || !vel || !distanceM) return null
  const yaw = motion?.orientation?.yaw ?? 0
  const v = carLocalToWorld(vel, yaw)
  const speed = Math.hypot(v.x, v.z)
  if (speed < 1.0) return null
  const ux = v.x / speed
  const uz = v.z / speed
  return [pos.x + ux * distanceM, pos.z + uz * distanceM]
}
