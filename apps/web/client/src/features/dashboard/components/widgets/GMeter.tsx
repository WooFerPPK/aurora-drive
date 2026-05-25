// client/src/components/widgets/GMeter.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, valueColour, toRgb, ease,
  drawWidgetBg, drawAmbientBloom, drawSparks,
} from '@/shared/lib/canvasUtils'
import {
  BigNumber,
  useThresholdFlash, stepThresholdFlash,
  EASE_STALE,
} from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'

const G_TO_MS2 = 9.81
const SCALE_G  = 1.6
const TRAIL_LEN = 90
const GUIDE_CIRCLES = [0.5, 1.0, 1.5]

const TRAIL_COLOURS: string[] = Array.from({ length: TRAIL_LEN }, (_, i) => {
  const age = i / TRAIL_LEN
  const alpha = ((1 - age) * 0.55).toFixed(3)
  return `rgba(168,243,208,${alpha})`
})

export interface GMeterProps {
  w: number
  h: number
}

export default function GMeter({ w, h }: GMeterProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const trailXRef    = useRef(new Float32Array(TRAIL_LEN))
  const trailZRef    = useRef(new Float32Array(TRAIL_LEN))
  const trailHeadRef = useRef(0)
  const flashRef     = useThresholdFlash({ decayMs: 500 })

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const ax    = stale ? 0 : ((frame!.motion?.acceleration?.x ?? 0) / G_TO_MS2)
    const az    = stale ? 0 : ((frame!.motion?.acceleration?.z ?? 0) / G_TO_MS2)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)

    if (tier === 'hero' && !stale) {
      trailXRef.current[trailHeadRef.current] = ax
      trailZRef.current[trailHeadRef.current] = az
      trailHeadRef.current = (trailHeadRef.current + 1) % TRAIL_LEN
    }

    drawWidgetBg(ctx, cw, ch)

    const cx   = cw / 2
    const cy   = ch / 2
    const half = Math.min(cw, ch) / 2 - 12

    const dotX = cx + Math.max(-half, Math.min(half, (ax / SCALE_G) * half))
    const dotY = cy - Math.max(-half, Math.min(half, (az / SCALE_G) * half))

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const totalG = Math.min(SCALE_G, Math.hypot(ax, az))
    const dotCol = valueColour(totalG / SCALE_G)
    drawAmbientBloom(ctx, cw, ch, dotX, dotY, half * 0.5, dotCol, totalG / SCALE_G)

    // Threshold flash at >1.0g
    stepThresholdFlash(flashRef, totalG > 1.0, dt)

    // Guide circles — brighter at compact since there's less context.
    const numCircles = tier === 'compact' ? 1 : tier === 'standard' ? 2 : 3
    const guideAlpha = tier === 'compact' ? 0.32 : 0.15
    const guideAlphaFaint = tier === 'compact' ? 0.18 : 0.07
    for (let i = 0; i < numCircles; i++) {
      const gVal = GUIDE_CIRCLES[i] ?? 0
      const pr   = half * (gVal / SCALE_G)
      ctx.strokeStyle = gVal === 1.0
        ? `rgba(253,233,255,${guideAlpha})`
        : `rgba(253,233,255,${guideAlphaFaint})`
      ctx.lineWidth   = gVal === 1.0 ? 1.2 : 0.7
      ctx.beginPath(); ctx.arc(cx, cy, pr, 0, Math.PI * 2); ctx.stroke()
      if (tier !== 'compact' && gVal <= 1.5) {
        ctx.font         = `500 9px "JetBrains Mono", monospace`
        ctx.fillStyle    = 'rgba(253,233,255,0.3)'
        ctx.textAlign    = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(`${gVal}g`, cx + pr + 4, cy)
      }
    }

    // Crosshair
    ctx.strokeStyle = tier === 'compact'
      ? 'rgba(253,233,255,0.22)' : 'rgba(253,233,255,0.10)'
    ctx.lineWidth   = 0.8
    ctx.beginPath(); ctx.moveTo(cx - half, cy); ctx.lineTo(cx + half, cy); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(cx, cy - half); ctx.lineTo(cx, cy + half); ctx.stroke()

    // Hero trail
    if (tier === 'hero') {
      const tx   = trailXRef.current
      const tz   = trailZRef.current
      const head = trailHeadRef.current
      for (let i = 0; i < TRAIL_LEN; i++) {
        const idx = (head - 1 - i + TRAIL_LEN) % TRAIL_LEN
        const tvx = tx[idx] ?? 0
        const tvz = tz[idx] ?? 0
        if (!tvx && !tvz) continue
        const age = i / TRAIL_LEN
        const tdx = cx + (tvx / SCALE_G) * half
        const tdy = cy - (tvz / SCALE_G) * half
        ctx.fillStyle = TRAIL_COLOURS[i] ?? 'rgba(168,243,208,0)'
        ctx.beginPath(); ctx.arc(tdx, tdy, Math.max(0.5, 2.5 - age * 1.5), 0, Math.PI * 2); ctx.fill()
      }
    }

    // Live dot
    ctx.fillStyle    = C.cream
    ctx.shadowColor  = toRgb(dotCol); ctx.shadowBlur = 18
    ctx.beginPath(); ctx.arc(dotX, dotY, tier === 'hero' ? 7 : 6, 0, Math.PI * 2); ctx.fill()
    ctx.shadowBlur = 0

    // Threshold sparks from the live dot when over 1g
    if (flashRef.current.intensity > 0) {
      drawSparks(ctx, dotX, dotY, flashRef.current.intensity, dotCol, {
        innerR: 12, outerR: 36, count: 12,
      })
    }

    // Hero only: LAT/LON breakdown text (Total G is now in <BigNumber>)
    if (tier === 'hero') {
      ctx.font         = '500 11px "JetBrains Mono", monospace'
      ctx.fillStyle    = C.inkFaint
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(`LAT ${ax.toFixed(2)}  LON ${az.toFixed(2)}`, cx, ch - 6)
    }

    ctx.globalAlpha = 1
  })

  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => {
    if (!frame) return null
    const ax = (frame.motion?.acceleration?.x ?? 0) / G_TO_MS2
    const az = (frame.motion?.acceleration?.z ?? 0) / G_TO_MS2
    const totalG = Math.min(SCALE_G, Math.hypot(ax, az))
    return {
      display: `${totalG.toFixed(2)} g`,
      normalized: Math.max(0, Math.min(1, totalG / SCALE_G)),
    }
  }

  return (
    <div className="radial-gauge-wrap g-meter-wrap">
      <canvas ref={canvasRef} className="widget-canvas" />
      <BigNumber tier={tier} getValue={numberGetter} />
    </div>
  )
}
