// client/src/components/widgets/SpeedDial.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { useSettings } from '@/features/settings/context/SettingsContext'
import { mpsToKph, mpsToMph } from '@/shared/lib/format'
import {
  ease, valueColour, toRgba, BUTTER_RGB,
  drawAmbientBloom,
} from '@/shared/lib/canvasUtils'
import {
  drawRadialGauge,
  BigNumber,
  EASE_VALUE, EASE_STALE,
} from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'

// speed_dial — animated speedometer with peak marker + hero trail.

const START_RAD = (135 * Math.PI) / 180
const SWEEP_RAD = (270 * Math.PI) / 180
const TRAIL_LEN = 80
const TWO_PI    = Math.PI * 2
const SCALE_KMH = 350
const SCALE_MPH = 220

export interface SpeedDialProps {
  w: number
  h: number
}

export default function SpeedDial({ w, h }: SpeedDialProps) {
  const { settings } = useSettings()
  const unit  = settings?.display?.speedUnit === 'mph' ? 'mph' : 'kmh'
  const scale = unit === 'mph' ? SCALE_MPH : SCALE_KMH
  const tier  = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const valueEaseRef = useRef(0)
  const staleFadeRef = useRef(0)
  const peakRef      = useRef(0)
  const peakPulseRef = useRef(0)
  const trailRef     = useRef(new Float32Array(TRAIL_LEN))
  const trailHeadRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const mps   = stale ? 0 : (frame!.motion?.speed_mps ?? 0)
    const spd   = unit === 'mph' ? mpsToMph(mps) : mpsToKph(mps)
    const v01   = Math.max(0, Math.min(1, spd / scale))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    valueEaseRef.current = ease(valueEaseRef.current, v01,           dt, EASE_VALUE)
    const cur = valueEaseRef.current

    if (!stale && spd > peakRef.current) {
      peakRef.current      = spd
      peakPulseRef.current = 1
    }
    peakPulseRef.current = Math.max(0, peakPulseRef.current - dt * 1.6)

    if (tier === 'hero') {
      trailRef.current[trailHeadRef.current] = cur
      trailHeadRef.current = (trailHeadRef.current + 1) % TRAIL_LEN
    }

    const cx = cw / 2, cy = ch / 2 + 2
    const r  = Math.min(cw, ch) * (tier === 'hero' ? 0.46 : 0.40) - 10

    // Clear the canvas ourselves (we draw the trail before drawRadialGauge,
    // and drawRadialGauge with skipBg won't clear).
    ctx.clearRect(0, 0, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    // Re-add the bloom that drawRadialGauge would have drawn (skipBg suppresses it).
    drawAmbientBloom(ctx, cw, ch, cx, cy, r, valueColour(cur), cur)

    // Hero trail dots — drawn before the arc so the live arc reads on top.
    if (tier === 'hero') {
      const trail = trailRef.current
      const head  = trailHeadRef.current
      for (let i = 0; i < TRAIL_LEN; i++) {
        const idx = (head - 1 - i + TRAIL_LEN) % TRAIL_LEN
        const tv  = trail[idx]
        if (!tv) continue
        const age   = i / TRAIL_LEN
        const angle = START_RAD + Math.min(1, tv) * SWEEP_RAD
        ctx.fillStyle = toRgba(valueColour(tv), (1 - age) * 0.45)
        ctx.beginPath()
        ctx.arc(cx + r * Math.cos(angle), cy + r * Math.sin(angle), 1.5, 0, TWO_PI)
        ctx.fill()
      }
    }

    drawRadialGauge(ctx, {
      cx, cy, r,
      startRad: START_RAD, sweepRad: SWEEP_RAD,
      value: cur,
      tier,
      tickMax: scale,
      peak: tier === 'hero' && peakRef.current > 0
        ? { value: Math.min(1, peakRef.current / scale), pulse: peakPulseRef.current }
        : null,
      skipBg: true,   // we already cleared above and drew bloom + trail
    })

    // Hero peak readout (text)
    if (tier === 'hero' && peakRef.current > 0) {
      ctx.font         = `500 9px "JetBrains Mono", monospace`
      ctx.fillStyle    = toRgba(BUTTER_RGB, 0.78)
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(`PEAK  ${Math.round(peakRef.current)}`, cw / 2, ch - 10)
    }

    ctx.globalAlpha = 1
  })

  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => {
    if (!frame) return null
    const mps = frame.motion?.speed_mps ?? 0
    const spd = unit === 'mph' ? mpsToMph(mps) : mpsToKph(mps)
    return {
      display:    String(Math.round(spd)),
      normalized: Math.max(0, Math.min(1, spd / scale)),
    }
  }

  return (
    <div className="radial-gauge-wrap speed-dial-wrap">
      <canvas ref={canvasRef} className="widget-canvas speed-dial" />
      <BigNumber tier={tier} getValue={numberGetter} unit={unit === 'mph' ? 'MPH' : 'KM/H'} />
    </div>
  )
}
