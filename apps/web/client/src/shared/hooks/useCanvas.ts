import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { liveClient } from '@/shared/lib/wsClient'

// Canvas + rAF loop for widgets that draw imperatively. The hook
// handles devicePixelRatio scaling and ResizeObserver-based backing-
// store resizing so widget code can pretend the canvas is `w × h` CSS
// pixels regardless of the screen.
//
// Usage:
//
//   function SpeedDial({ w, h }) {
//     const canvasRef = useCanvas(({ ctx, w, h, frame, dt }) => {
//       ctx.clearRect(0, 0, w, h)
//       const speed = frame?.motion?.speed_mps ?? 0
//       // ...draw the dial at `speed`
//     })
//     return <canvas ref={canvasRef} className="widget-canvas" />
//   }
//
// Rules:
// - Draw function runs every animation frame regardless of WS rate.
//   If no frame has arrived yet, `frame === null`.
// - Do NOT setState inside the draw function. Use refs if you need
//   widget-local state (selected lap, hover target, etc).

export interface CanvasDrawContext {
  ctx: CanvasRenderingContext2D
  w: number
  h: number
  dpr: number
  frame: Frame | null
  dt: number
  elapsed: number
  count: number
  frameAgeMs: number | null
}

export type CanvasDrawFn = (ctx: CanvasDrawContext) => void

export function useCanvas(drawFn: CanvasDrawFn, deps: readonly unknown[] = []): RefObject<HTMLCanvasElement> {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fnRef = useRef<CanvasDrawFn>(drawFn)
  fnRef.current = drawFn

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    let cssW = 0, cssH = 0, dpr = window.devicePixelRatio || 1

    const resize = (): void => {
      const rect = canvas.getBoundingClientRect()
      cssW = Math.max(1, Math.round(rect.width))
      cssH = Math.max(1, Math.round(rect.height))
      dpr  = window.devicePixelRatio || 1
      // Backing store sized in device pixels; transform makes drawing
      // coordinates CSS pixels.
      canvas.width  = Math.round(cssW * dpr)
      canvas.height = Math.round(cssH * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    let raf = 0
    let last = performance.now()
    const t0 = last
    let count = 0
    let stopped = false

    const tick = (now: number): void => {
      if (stopped) return
      const dt = (now - last) / 1000
      last = now
      try {
        fnRef.current({
          ctx,
          w: cssW,
          h: cssH,
          dpr,
          frame: liveClient.getLatestFrame() as Frame | null,
          dt,
          elapsed: (now - t0) / 1000,
          count: count++,
          frameAgeMs: liveClient.getFrameAgeMs(),
        })
      } catch (err) {
        console.warn('[useCanvas] draw threw', err)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      stopped = true
      if (raf) cancelAnimationFrame(raf)
      ro.disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return canvasRef
}
