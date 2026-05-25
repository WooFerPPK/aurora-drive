// client/src/components/widgets/BoostGauge.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { ease, toRgba, BUTTER_RGB } from '@/shared/lib/canvasUtils'
import {
  drawRadialGauge, drawSparkline,
  BigNumber,
  EASE_VALUE, EASE_STALE,
} from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'

// boost_gauge — manifold pressure dial. 0..30 psi.

const START_RAD = (135 * Math.PI) / 180
const SWEEP_RAD = (270 * Math.PI) / 180
const MAX_PSI   = 30
const WAVE_LEN  = 180

export interface BoostGaugeProps {
  w: number
  h: number
}

export default function BoostGauge({ w, h }: BoostGaugeProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const valueEaseRef = useRef(0)
  const staleFadeRef = useRef(0)
  const peakRef      = useRef(0)
  const peakPulseRef = useRef(0)
  const waveRef      = useRef(new Float32Array(WAVE_LEN))
  const waveHeadRef  = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const psi   = stale ? 0 : Math.max(0, frame!.engine?.boost_psi ?? 0)
    const v01   = Math.min(1, psi / MAX_PSI)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    valueEaseRef.current = ease(valueEaseRef.current, v01,           dt, EASE_VALUE)
    const cur = valueEaseRef.current

    if (!stale && psi > peakRef.current) { peakRef.current = psi; peakPulseRef.current = 1 }
    peakPulseRef.current = Math.max(0, peakPulseRef.current - dt * 1.6)

    if (tier === 'hero') {
      waveRef.current[waveHeadRef.current] = cur
      waveHeadRef.current = (waveHeadRef.current + 1) % WAVE_LEN
    }

    const cx = cw / 2
    const cy = tier === 'hero' ? ch * 0.42 : ch / 2 + 2
    const r  = Math.min(cw, tier === 'hero' ? ch * 0.6 : ch) * (tier === 'hero' ? 0.46 : 0.40) - 10

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45
    drawRadialGauge(ctx, {
      cx, cy, r,
      startRad: START_RAD, sweepRad: SWEEP_RAD,
      value: cur,
      tier,
      tickMax: MAX_PSI,
      peak: tier === 'hero' && peakRef.current > 0
        ? { value: Math.min(1, peakRef.current / MAX_PSI), pulse: peakPulseRef.current }
        : null,
    })

    if (tier === 'hero') {
      drawSparkline(ctx, {
        x: 10, y: ch * 0.74, w: cw - 20, h: ch * 0.22,
        buf: waveRef.current, head: waveHeadRef.current,
        fill: true,
      })
      if (peakRef.current > 0) {
        ctx.font         = `500 9px "JetBrains Mono", monospace`
        ctx.fillStyle    = toRgba(BUTTER_RGB, 0.78)
        ctx.textAlign    = 'right'
        ctx.textBaseline = 'bottom'
        ctx.fillText(`PEAK ${peakRef.current.toFixed(1)} PSI`, cw - 8, ch - 4)
      }
    }
    ctx.globalAlpha = 1
  })

  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => {
    if (!frame) return null
    const psi = Math.max(0, frame.engine?.boost_psi ?? 0)
    return { display: psi.toFixed(1), normalized: Math.min(1, psi / MAX_PSI) }
  }

  return (
    <div className="radial-gauge-wrap boost-gauge-wrap">
      <canvas ref={canvasRef} className="widget-canvas" />
      <BigNumber tier={tier} getValue={numberGetter} unit="PSI" />
    </div>
  )
}
