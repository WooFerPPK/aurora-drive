// client/src/lib/widgetPrimitives/drawSparkline.ts
import { valueColour, toRgb, toRgba } from '@/shared/lib/canvasUtils'
import type { ColourRamp, Rgb } from '@/shared/lib/canvasUtils'

export interface SparklineOpts {
  x: number
  y: number
  w: number
  h: number
  buf: Float32Array              // values ∈ [0, 1]
  head: number                   // index AFTER newest sample
  ramp?: ColourRamp
  fill?: boolean
  baselineRgba?: string | null
  strokeAlpha?: number
  strokeColour?: Rgb
}

export function drawSparkline(ctx: CanvasRenderingContext2D, opts: SparklineOpts): void {
  const { x, y, w, h, buf, head, ramp = 'intensity', fill = true, baselineRgba, strokeAlpha = 0.75, strokeColour } = opts
  const n = buf.length
  if (n < 2) return

  const latest = buf[(head - 1 + n) % n] ?? 0
  const colRgb: Rgb = strokeColour ?? valueColour(latest, ramp)

  if (baselineRgba) {
    ctx.strokeStyle = baselineRgba
    ctx.lineWidth   = 0.6
    ctx.setLineDash([2, 3])
    ctx.beginPath()
    ctx.moveTo(x, y + h / 2); ctx.lineTo(x + w, y + h / 2)
    ctx.stroke()
    ctx.setLineDash([])
  }

  // Stroke the line
  ctx.strokeStyle = toRgba(colRgb, strokeAlpha)
  ctx.lineWidth   = 1.5
  ctx.shadowColor = toRgb(colRgb); ctx.shadowBlur = 5
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const idx = (head - 1 - i + n) % n
    const px  = (x + w) - (i / (n - 1)) * w
    const py  = y + h - (buf[idx] ?? 0) * h
    if (i === 0) ctx.moveTo(px, py)
    else         ctx.lineTo(px, py)
  }
  ctx.stroke()
  ctx.shadowBlur = 0

  // Fill under the curve
  if (fill) {
    ctx.beginPath()
    for (let i = 0; i < n; i++) {
      const idx = (head - 1 - i + n) % n
      const px  = (x + w) - (i / (n - 1)) * w
      const py  = y + h - (buf[idx] ?? 0) * h
      if (i === 0) ctx.moveTo(px, py)
      else         ctx.lineTo(px, py)
    }
    ctx.lineTo(x,     y + h)
    ctx.lineTo(x + w, y + h)
    ctx.closePath()
    const fg = ctx.createLinearGradient(0, y, 0, y + h)
    fg.addColorStop(0, toRgba(colRgb, 0.22))
    fg.addColorStop(1, toRgba(colRgb, 0.01))
    ctx.fillStyle = fg
    ctx.fill()
  }
}
