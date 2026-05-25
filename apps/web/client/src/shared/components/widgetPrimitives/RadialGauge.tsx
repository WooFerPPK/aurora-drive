// client/src/lib/widgetPrimitives/RadialGauge.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { ease, valueColour, drawSparks } from '@/shared/lib/canvasUtils'
import type { ColourRamp, TickTier } from '@/shared/lib/canvasUtils'
import { drawRadialGauge } from './drawRadialGauge'
import { stepThresholdFlash, useThresholdFlash } from './useThresholdFlash'
import BigNumber from './BigNumber'
import type { BigNumberValueOut } from './BigNumber'
import { EASE_VALUE, EASE_STALE } from './easeConstants'

const DEFAULT_START = (135 * Math.PI) / 180
const DEFAULT_SWEEP = (270 * Math.PI) / 180

export interface RadialGaugeProps {
  getValue: (frame: Frame) => number
  max: number
  min?: number
  format?: (raw: number) => BigNumberValueOut
  unit?: string
  tier?: TickTier
  startRad?: number
  sweepRad?: number
  tickMax?: number | null
  redlinePct?: number | null
  showPeak?: boolean
  showRedlineFlash?: boolean
  ramp?: ColourRamp
  className?: string
}

export default function RadialGauge({
  getValue,
  max,
  min = 0,
  format,
  unit,
  tier = 'standard',
  startRad = DEFAULT_START,
  sweepRad = DEFAULT_SWEEP,
  tickMax,
  redlinePct,
  showPeak = false,
  showRedlineFlash = false,
  ramp = 'intensity',
  className = '',
}: RadialGaugeProps) {
  const valueEaseRef = useRef(0)
  const staleFadeRef = useRef(0)
  const peakValueRef = useRef(0)
  const peakPulseRef = useRef(0)
  const flashRef     = useThresholdFlash({ decayMs: 400 })

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const raw   = stale ? min : getValue(frame!)
    const v01   = Math.max(0, Math.min(1, (raw - min) / Math.max(1e-6, max - min)))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    valueEaseRef.current = ease(valueEaseRef.current, v01,           dt, EASE_VALUE)
    const cur = valueEaseRef.current

    if (showPeak && !stale && v01 > peakValueRef.current) {
      peakValueRef.current = v01
      peakPulseRef.current = 1
    }
    peakPulseRef.current = Math.max(0, peakPulseRef.current - dt / 0.6) // ~0.6s decay

    const overRedline = showRedlineFlash && redlinePct != null && cur > redlinePct
    stepThresholdFlash(flashRef, overRedline, dt)

    const cx = cw / 2
    const cy = ch / 2 + 2
    const r  = Math.min(cw, ch) * 0.40 - 10

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    drawRadialGauge(ctx, {
      cx, cy, r,
      startRad, sweepRad,
      value: cur,
      tier,
      tickMax: tickMax ?? null,
      redlinePct: redlinePct ?? null,
      peak: showPeak ? { value: peakValueRef.current, pulse: peakPulseRef.current } : null,
      ramp,
    })

    if (flashRef.current.intensity > 0) {
      drawSparks(ctx, cx, cy, flashRef.current.intensity, valueColour(cur, ramp), {
        innerR: r + 8, outerR: r + 28, count: 14,
      })
    }

    ctx.globalAlpha = 1
  })

  // BigNumber pulls the raw value separately each frame for crisp DOM text.
  // Default formatter mirrors the existing widgets — caller can override.
  const fmt = format ?? ((raw: number): BigNumberValueOut => ({
    display: String(Math.round(raw)),
    normalized: Math.max(0, Math.min(1, (raw - min) / Math.max(1e-6, max - min))),
  }))
  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => frame ? fmt(getValue(frame)) : null

  return (
    <div className={`radial-gauge-wrap ${className}`}>
      <canvas ref={canvasRef} className="widget-canvas" />
      <BigNumber getValue={numberGetter} tier={tier} {...(unit !== undefined ? { unit } : {})} />
    </div>
  )
}
