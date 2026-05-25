// client/src/lib/widgetPrimitives/drawRadialGauge.ts
import {
  C, valueColour, toRgba, PINK_RGB, BUTTER_RGB,
  drawWidgetBg, drawAmbientBloom, drawGaugeArc, drawTicks,
} from '@/shared/lib/canvasUtils'
import type { ColourRamp, TickTier } from '@/shared/lib/canvasUtils'

export interface RadialGaugePeak {
  value: number
  pulse?: number
}

export interface RadialGaugeOpts {
  cx: number
  cy: number
  r: number
  startRad: number
  sweepRad: number
  value: number                  // eased ∈ [0, 1]
  tier: TickTier
  tickMax?: number | null
  redlinePct?: number | null     // 0..1
  peak?: RadialGaugePeak | null
  skipBg?: boolean
  ramp?: ColourRamp
}

export function drawRadialGauge(ctx: CanvasRenderingContext2D, opts: RadialGaugeOpts): void {
  const { cx, cy, r, startRad, sweepRad, value, tier, tickMax, redlinePct, peak, skipBg, ramp = 'intensity' } = opts
  const colRgb = valueColour(value, ramp)

  if (!skipBg) {
    drawWidgetBg(ctx, ctx.canvas.width, ctx.canvas.height)
    drawAmbientBloom(ctx, ctx.canvas.width, ctx.canvas.height, cx, cy, r, colRgb, value)
  }

  // Compact: drop the arc entirely — the dial is too small to read at
  // this size, and the BigNumber overlay carries the value. The ambient
  // bloom still draws (if !skipBg) so the cell keeps its colour pulse.
  if (tier === 'compact') return

  // Standard: BigNumber overlays the arc area. Paint a soft dark disc
  // inside the arc so the number reads against a defined "card" instead
  // of colliding with the arc strokes. Hero skips the disc because the
  // arc is sized to keep the number clear of its strokes.
  if (tier === 'standard') {
    const discR = r * 0.95
    const disc = ctx.createRadialGradient(cx, cy, 0, cx, cy, discR)
    disc.addColorStop(0,    'rgba(13, 5, 32, 0.55)')
    disc.addColorStop(0.55, 'rgba(13, 5, 32, 0.30)')
    disc.addColorStop(1,    'transparent')
    ctx.fillStyle = disc
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height)
  }

  const lw  = tier === 'hero' ? 12 : 10
  const gbl = tier === 'hero' ? 22 : 18

  // Redline zone
  if (redlinePct != null && redlinePct < 1) {
    const redlineStart = startRad + sweepRad * redlinePct
    ctx.lineCap     = 'round'
    ctx.lineWidth   = lw
    ctx.strokeStyle = toRgba(PINK_RGB, tier === 'hero' ? 0.22 : 0.14)
    ctx.beginPath(); ctx.arc(cx, cy, r, redlineStart, startRad + sweepRad); ctx.stroke()
  }

  if (tickMax != null) {
    drawTicks(ctx, cx, cy, r, startRad, sweepRad, tier, tickMax)
  }

  drawGaugeArc(ctx, cx, cy, r, startRad, sweepRad, value, lw, gbl)

  // Peak marker
  if (tier === 'hero' && peak && peak.value > 0) {
    const peakA  = startRad + Math.min(1, peak.value) * sweepRad
    const pulse  = Math.max(0, Math.min(1, peak.pulse ?? 0))
    ctx.strokeStyle = toRgba(BUTTER_RGB, 0.65 + 0.35 * pulse)
    ctx.lineWidth   = 2 + 4 * pulse
    ctx.lineCap     = 'butt'
    ctx.shadowColor = C.butter; ctx.shadowBlur = 8 + 16 * pulse
    ctx.beginPath()
    ctx.moveTo(cx + (r - 4) * Math.cos(peakA),  cy + (r - 4) * Math.sin(peakA))
    ctx.lineTo(cx + (r + 14) * Math.cos(peakA), cy + (r + 14) * Math.sin(peakA))
    ctx.stroke()
    ctx.shadowBlur = 0
  }
}
