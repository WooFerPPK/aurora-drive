import { useEffect, useRef, useState } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { liveClient } from '@/shared/lib/wsClient'
import { TELEMETRY_STALE_MS } from '@/shared/lib/constants'

// Default frame, structured to match api-contract.md §2 so widgets can
// read it the same way before any frame has arrived.
export const EMPTY_FRAME: Frame = {
  t: 0,
  sessionId: '',
  carId: '',
  isRaceOn: false,
  race: { lap: 0, position: 0, currentLapS: 0, lastLapS: 0, bestLapS: 0, raceTimeS: 0 },
  engine: { rpm: 0, idleRpm: 800, maxRpm: 8000, power_w: 0, torque_nm: 0, boost_psi: 0, fuel: 0 },
  drivetrain: { gear: 0, clutch: 0, type: 'AWD' },
  motion: {
    speed_mps: 0,
    velocity:     { x: 0, y: 0, z: 0 },
    acceleration: { x: 0, y: 0, z: 0 },
    angularVelocity: { x: 0, y: 0, z: 0 },
    orientation: { yaw: 0, pitch: 0, roll: 0 },
    position:    { x: 0, y: 0, z: 0 },
  },
  inputs: { throttle: 0, brake: 0, clutch: 0, handbrake: 0, steer: 0, drivingLine: 0, aiBrakeDelta: 0 },
  wheels: {
    fl: { slipRatio: 0, slipAngle: 0, combinedSlip: 0, rotation_rad_s: 0, suspensionTravel_norm: 0.5, suspensionTravel_m: 0, tireTemp_c: 0, tireTemp_normWindow: 0, onRumble: 0, inPuddle: 0, surfaceRumble: 0 },
    fr: { slipRatio: 0, slipAngle: 0, combinedSlip: 0, rotation_rad_s: 0, suspensionTravel_norm: 0.5, suspensionTravel_m: 0, tireTemp_c: 0, tireTemp_normWindow: 0, onRumble: 0, inPuddle: 0, surfaceRumble: 0 },
    rl: { slipRatio: 0, slipAngle: 0, combinedSlip: 0, rotation_rad_s: 0, suspensionTravel_norm: 0.5, suspensionTravel_m: 0, tireTemp_c: 0, tireTemp_normWindow: 0, onRumble: 0, inPuddle: 0, surfaceRumble: 0 },
    rr: { slipRatio: 0, slipAngle: 0, combinedSlip: 0, rotation_rad_s: 0, suspensionTravel_norm: 0.5, suspensionTravel_m: 0, tireTemp_c: 0, tireTemp_normWindow: 0, onRumble: 0, inPuddle: 0, surfaceRumble: 0 },
  },
  world: { carOrdinal: 0, carClass: 'D', performanceIndex: 0, numCylinders: 0, carGroup: 0, smashableVelDiff: 0, smashableMass: 0 },
  derived: { balance: 0, weightFront: 0.5, weightLeft: 0.5, bodyControl: 1, gripBudgetUsed: 0, powerBandOccupancy: 0, throttleSmoothness: 1 },
  modeled: { tireWear: { fl: 0, fr: 0, rl: 0, rr: 0 }, tireWearConfidence: 0, modeledByVersion: '' },
}

export interface UseTelemetryResult {
  frame: Frame
  hasFrame: boolean
  fresh: boolean
}

// useTelemetry subscribes to `frame` and `heartbeat` and tracks whether
// frames have been arriving recently. State-channel transitions
// (driving / paused / lost) are split off into useStreamState so this
// hook stays focused on the actual frame payload.
export function useTelemetry(): UseTelemetryResult {
  const [frame, setFrame] = useState<Frame>(EMPTY_FRAME)
  const [hasFrame, setHasFrame] = useState(false)
  const [fresh, setFresh] = useState(false)
  const lastAtRef = useRef(0)

  useEffect(() => {
    const offFrame = liveClient.subscribe('frame', (msg: Frame) => {
      lastAtRef.current = Date.now()
      setFrame(msg)
      setHasFrame(true)
      setFresh(true)
    })
    const offHeartbeat = liveClient.subscribe('heartbeat', () => {
      // heartbeats are server-side keepalives — do not mark fresh
    })
    const id = setInterval(() => {
      if (Date.now() - lastAtRef.current > TELEMETRY_STALE_MS) {
        setFresh((cur) => (cur ? false : cur))
      }
    }, 500)
    return () => { offFrame(); offHeartbeat(); clearInterval(id) }
  }, [])

  return { frame, hasFrame, fresh }
}
