// client/src/components/widgets/CarSilhouette.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB,
  toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'
import { drawCarBody, EASE_STALE } from '@/shared/components/widgetPrimitives'

// car_silhouette — top-down car ALIVE with slip-blur trails behind tires,
// CoM weight-transfer trail, pulsing border at high lateral g, and (hero)
// aerodynamic flow lines + g readout.

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
interface CornerMeta { k: CornerKey; isLeft: boolean; isFront: boolean }
const CORNERS: readonly CornerMeta[] = [
  { k: 'fl', isLeft: true,  isFront: true  },
  { k: 'fr', isLeft: false, isFront: true  },
  { k: 'rl', isLeft: true,  isFront: false },
  { k: 'rr', isLeft: false, isFront: false },
]

const TRAIL_LEN = 30
const COM_TRAIL_LEN = 40
const G_TO_MS2 = 9.81
const G_THRESHOLD = 1.0

function slipColour(s: number): Rgb {
  if (s < 0.15) return MINT_RGB
  if (s < 0.40) return BUTTER_RGB
  return PINK_RGB
}

export interface CarSilhouetteProps {
  w: number
  h: number
}

export default function CarSilhouette({ w, h }: CarSilhouetteProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const staleFadeRef  = useRef(0)
  const slipsRef      = useRef(new Float32Array(4))
  const balXRef       = useRef(0.5)
  const balYRef       = useRef(0.5)
  const latGRef       = useRef(0)
  const longGRef      = useRef(0)
  const speedRef      = useRef(0)
  const tireTrailsRef = useRef<Float32Array[]>([
    new Float32Array(TRAIL_LEN * 2),
    new Float32Array(TRAIL_LEN * 2),
    new Float32Array(TRAIL_LEN * 2),
    new Float32Array(TRAIL_LEN * 2),
  ])
  const comTrailRef   = useRef(new Float32Array(COM_TRAIL_LEN * 2))
  const trailHeadRef  = useRef(0)
  const comHeadRef    = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, elapsed, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const wheels = stale ? null : (frame!.wheels ?? null)
    const wFront = stale ? 0.5 : (frame!.derived?.weightFront ?? 0.5)
    const wLeft  = stale ? 0.5 : (frame!.derived?.weightLeft  ?? 0.5)
    const latG   = stale ? 0 : ((frame!.motion?.acceleration?.x ?? 0) / G_TO_MS2)
    const longG  = stale ? 0 : ((frame!.motion?.acceleration?.z ?? 0) / G_TO_MS2)
    const speed  = stale ? 0 : (frame!.motion?.speed_mps ?? 0)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    balXRef.current = ease(balXRef.current, Math.max(0, Math.min(1, wLeft)),  dt, 4)
    balYRef.current = ease(balYRef.current, Math.max(0, Math.min(1, wFront)), dt, 4)
    latGRef.current  = ease(latGRef.current,  latG,  dt, 5)
    longGRef.current = ease(longGRef.current, longG, dt, 5)
    speedRef.current = ease(speedRef.current, speed, dt, 4)

    for (let i = 0; i < 4; i++) {
      const k = CORNERS[i]!.k
      const s = stale ? 0 : Math.min(1, Math.abs(wheels?.[k]?.combinedSlip ?? 0))
      slipsRef.current[i] = ease(slipsRef.current[i] ?? 0, s, dt, 6)
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const cx = cw / 2, cy = ch / 2
    const carW = cw * 0.36, carH = ch * 0.66
    const tireW = cw * 0.13, tireH = ch * 0.22

    const totalG = Math.hypot(latGRef.current, longGRef.current)

    if (tier === 'hero' && speedRef.current > 8) {
      const bodyY = cy - carH / 2
      const flowCount = 8
      const speedFactor = Math.min(1, speedRef.current / 60)
      for (let i = 0; i < flowCount; i++) {
        const baseY = bodyY - 20 + (i / flowCount) * (carH + 40)
        const phase = elapsed * 2 * speedFactor + i * 0.5
        const offset = ((phase % 4) / 4)
        const startX = cx - carW * 0.8 + offset * carW * 1.6
        const len = 16 + Math.sin(i) * 4
        ctx.strokeStyle = `rgba(184,212,255,${0.20 * speedFactor * (1 - Math.abs(offset - 0.5) * 2)})`
        ctx.lineWidth = 0.7
        ctx.lineCap = 'round'
        ctx.beginPath(); ctx.moveTo(startX, baseY); ctx.lineTo(startX + len, baseY); ctx.stroke()
      }
      ctx.lineCap = 'butt'
    }

    const borderPulse = (tier !== 'compact' && Math.abs(latGRef.current) > G_THRESHOLD)
      ? {
          colourRgb: PINK_RGB,
          intensity: Math.min(1, (Math.abs(latGRef.current) - G_THRESHOLD) * 1.5)
                     * (0.6 + 0.4 * Math.sin(elapsed * 6)),
        }
      : null

    const { corners } = drawCarBody(ctx, {
      cx, cy, cw, ch, carW, carH,
      tireOffsetX: carW * 0.55,
      tireOffsetY: carH * 0.32,
      borderPulse,
    })

    for (let i = 0; i < 4; i++) {
      const buf = tireTrailsRef.current[i]!
      const c = corners[i]!
      buf[trailHeadRef.current * 2]     = c.x
      buf[trailHeadRef.current * 2 + 1] = c.y
    }
    trailHeadRef.current = (trailHeadRef.current + 1) % TRAIL_LEN

    for (let i = 0; i < 4; i++) {
      const s = slipsRef.current[i] ?? 0
      if (s < 0.15) continue
      const buf = tireTrailsRef.current[i]!
      for (let j = 0; j < TRAIL_LEN; j++) {
        const idx = (trailHeadRef.current - 1 - j + TRAIL_LEN) % TRAIL_LEN
        const tx = buf[idx * 2] ?? 0
        const ty = buf[idx * 2 + 1] ?? 0
        const age = j / TRAIL_LEN
        ctx.fillStyle = toRgba(PINK_RGB, (1 - age) * s * 0.5)
        ctx.beginPath(); ctx.arc(tx, ty, 1.5, 0, Math.PI * 2); ctx.fill()
      }
    }

    for (let i = 0; i < 4; i++) {
      const slip = slipsRef.current[i] ?? 0
      const sc = slipColour(slip)
      const c = corners[i]!
      const tx = c.x - tireW / 2
      const ty = c.y - tireH / 2
      ctx.shadowColor = toRgb(sc); ctx.shadowBlur = tier === 'compact' ? 10 : 16
      ctx.fillStyle = toRgba(sc, 0.75)
      roundRectPath(ctx, tx, ty, tireW, tireH, 4); ctx.fill()
      ctx.shadowBlur = 0
      const ig = ctx.createLinearGradient(tx, ty, tx, ty + tireH)
      ig.addColorStop(0, toRgba(sc, 0.4))
      ig.addColorStop(1, 'transparent')
      ctx.fillStyle = ig
      roundRectPath(ctx, tx, ty, tireW, tireH, 4); ctx.fill()
    }

    if (tier !== 'compact') {
      const bodyX = cx - carW / 2
      const bodyY = cy - carH / 2
      const bx = bodyX + balXRef.current * carW
      const by = bodyY + balYRef.current * carH
      comTrailRef.current[comHeadRef.current * 2]     = bx
      comTrailRef.current[comHeadRef.current * 2 + 1] = by
      comHeadRef.current = (comHeadRef.current + 1) % COM_TRAIL_LEN

      for (let j = 0; j < COM_TRAIL_LEN; j++) {
        const idx = (comHeadRef.current - 1 - j + COM_TRAIL_LEN) % COM_TRAIL_LEN
        const tx = comTrailRef.current[idx * 2] ?? 0
        const ty = comTrailRef.current[idx * 2 + 1] ?? 0
        if (!tx || !ty) continue
        const age = j / COM_TRAIL_LEN
        ctx.fillStyle = `rgba(168,243,208,${(1 - age) * 0.4})`
        ctx.beginPath(); ctx.arc(tx, ty, 2 + (1 - age) * 1.5, 0, Math.PI * 2); ctx.fill()
      }

      ctx.fillStyle = C.cream
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 14
      ctx.beginPath(); ctx.arc(bx, by, 5, 0, Math.PI * 2); ctx.fill()
      ctx.shadowBlur = 0
    }

    if (tier === 'hero') {
      ctx.font = '700 14px "JetBrains Mono", monospace'
      ctx.fillStyle = C.cream
      ctx.textAlign = 'right'; ctx.textBaseline = 'top'
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 6
      ctx.fillText(`${totalG.toFixed(2)} g`, cw - 8, 8)
      ctx.shadowBlur = 0
      ctx.font = '500 11px "Unbounded", system-ui, sans-serif'
      ctx.fillStyle = C.inkFaint
      ctx.fillText('TOTAL', cw - 8, 26)
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
