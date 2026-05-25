// client/src/lib/widgetPrimitives/drawLinearGauge.ts
import {
  C, valueColour, toRgb,
  roundRectPath,
} from '@/shared/lib/canvasUtils'
import type { ColourRamp } from '@/shared/lib/canvasUtils'

export interface LinearGaugeOpts {
  x: number
  y: number
  w: number
  h: number
  value: number              // 0..1
  orientation?: 'h' | 'v'
  ramp?: ColourRamp
  trackColour?: string
}

// drawLinearGauge(ctx, opts) — single rounded-rect bar with track + filled
// portion + glow.
export function drawLinearGauge(ctx: CanvasRenderingContext2D, opts: LinearGaugeOpts): void {
  const { x, y, w, h, value, orientation = 'h', ramp = 'intensity', trackColour } = opts
  const v = Math.max(0, Math.min(1, value))
  const col = valueColour(v, ramp)
  const radius = Math.min(w, h) / 2

  // Track
  ctx.fillStyle = trackColour ?? C.track
  roundRectPath(ctx, x, y, w, h, radius); ctx.fill()

  // Fill
  if (v <= 0) return
  ctx.fillStyle   = toRgb(col)
  ctx.shadowColor = toRgb(col)
  ctx.shadowBlur  = 8
  if (orientation === 'h') {
    roundRectPath(ctx, x, y, w * v, h, radius)
  } else {
    const fh = h * v
    roundRectPath(ctx, x, y + (h - fh), w, fh, radius)
  }
  ctx.fill()
  ctx.shadowBlur = 0
}
