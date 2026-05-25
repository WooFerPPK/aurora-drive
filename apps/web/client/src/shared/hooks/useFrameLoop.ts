import { useEffect, useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { liveClient } from '@/shared/lib/wsClient'

// Run `cb(frame, info)` once per animation frame, where:
//   frame = the latest WS frame (or null if none yet)
//   info  = { dt, elapsed, count, ageMs, frameAgeMs }
//     dt          — seconds since last call
//     elapsed     — seconds since mount
//     count       — call counter
//     frameAgeMs  — ms since the most recent frame was received
//
// Why this exists: React state can't keep up with 60 Hz updates from
// many widgets. This hook decouples render rate from data rate — the
// widget mounts once and then mutates DOM via refs (or draws to canvas)
// inside the rAF loop. No React reconciliation on the hot path.
//
// Rule for callers: do NOT setState inside `cb`. Mutate refs or canvas
// only. If you need React to re-render, use useTelemetryData instead.

export interface FrameLoopInfo {
  dt: number
  elapsed: number
  count: number
  frameAgeMs: number | null
}

export type FrameLoopCallback = (frame: Frame | null, info: FrameLoopInfo) => void

export function useFrameLoop(cb: FrameLoopCallback, deps: readonly unknown[] = []): void {
  const cbRef = useRef<FrameLoopCallback>(cb)
  cbRef.current = cb

  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const t0 = last
    let count = 0
    let stopped = false

    const tick = (now: number): void => {
      if (stopped) return
      const dt = (now - last) / 1000
      last = now
      const frame = liveClient.getLatestFrame() as Frame | null
      try {
        cbRef.current(frame, {
          dt,
          elapsed: (now - t0) / 1000,
          count: count++,
          frameAgeMs: liveClient.getFrameAgeMs(),
        })
      } catch (err) {
        console.warn('[useFrameLoop] callback threw', err)
      }
      raf = requestAnimationFrame(tick)
    }

    raf = requestAnimationFrame(tick)
    return () => {
      stopped = true
      if (raf) cancelAnimationFrame(raf)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
