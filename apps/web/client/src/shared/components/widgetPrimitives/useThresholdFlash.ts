// client/src/lib/widgetPrimitives/useThresholdFlash.ts
import { useRef } from 'react'
import type { MutableRefObject } from 'react'

// useThresholdFlash — returns a ref that holds a 0..1 intensity ramp.
// The ramp resets to 1.0 whenever `armed === true` transitions from false to
// true. After firing it decays toward 0 at rate `1 / decayMs`.
//
// Usage inside a useCanvas / useFrameLoop callback:
//
//   const flashRef = useThresholdFlash({ decayMs: 400 })
//   // each frame:
//   const armed = value > 0.95
//   stepThresholdFlash(flashRef, armed, dt)
//   drawSparks(ctx, cx, cy, flashRef.current.intensity, col)
//
// This split (hook + step fn) keeps the hot path React-state-free.

export interface ThresholdFlashState {
  intensity: number
  armed: boolean
  decayMs: number
}

export function useThresholdFlash({ decayMs = 400 }: { decayMs?: number } = {}): MutableRefObject<ThresholdFlashState> {
  const ref = useRef<ThresholdFlashState>({ intensity: 0, armed: false, decayMs })
  ref.current.decayMs = decayMs
  return ref
}

// Step the flash given the current armed state and dt (seconds).
// Mutates the ref in place. Call once per frame.
export function stepThresholdFlash(ref: MutableRefObject<ThresholdFlashState>, armed: boolean, dt: number): void {
  const s = ref.current
  // Rising edge: re-arm and pulse to 1.
  if (armed && !s.armed) s.intensity = 1
  s.armed = armed
  // Decay
  if (s.intensity > 0) {
    s.intensity = Math.max(0, s.intensity - (dt * 1000) / s.decayMs)
  }
}
