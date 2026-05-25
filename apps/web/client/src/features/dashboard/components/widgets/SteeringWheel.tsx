// client/src/components/widgets/SteeringWheel.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, valueColour, toRgb, toRgba, ease,
  drawWidgetBg,
} from '@/shared/lib/canvasUtils'

// steering_wheel — visual steering wheel rotated by frame.inputs.steer.

const MAX_ROTATION = (270 * Math.PI) / 180
const TRAIL_LEN = 80

export interface SteeringWheelProps {
  w: number
  h: number
}

export default function SteeringWheel({ w, h }: SteeringWheelProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const valueRef     = useRef(0)
  const staleFadeRef = useRef(0)
  const trailRef     = useRef(new Float32Array(TRAIL_LEN))
  const trailHeadRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const target = stale ? 0 : Math.max(-1, Math.min(1, frame!.inputs?.steer ?? 0))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)
    valueRef.current     = ease(valueRef.current, target, dt, 9)
    const v = valueRef.current

    if (tier === 'hero') {
      trailRef.current[trailHeadRef.current] = v
      trailHeadRef.current = (trailHeadRef.current + 1) % TRAIL_LEN
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const cx = cw / 2
    const cy = ch / 2 + (tier === 'hero' ? 6 : 0)
    const r  = Math.min(cw, ch - (tier === 'hero' ? 26 : 0)) * 0.40

    const intensity = Math.min(1, Math.abs(v))
    const auraCol = valueColour(intensity)
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 1.4)
    g.addColorStop(0, toRgba(auraCol, 0.14))
    g.addColorStop(1, 'transparent')
    ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch)

    if (tier === 'hero') {
      const trail = trailRef.current
      const head  = trailHeadRef.current
      const arcR  = r * 1.20
      const baseA = -Math.PI / 2
      const arcSpan = (90 * Math.PI) / 180
      for (let i = 0; i < TRAIL_LEN; i++) {
        const idx = (head - 1 - i + TRAIL_LEN) % TRAIL_LEN
        const tv  = trail[idx] ?? 0
        if (tv === 0) continue
        const age = i / TRAIL_LEN
        const a   = baseA + tv * arcSpan
        ctx.fillStyle = toRgba(valueColour(Math.abs(tv)), (1 - age) * 0.5)
        ctx.beginPath()
        ctx.arc(cx + arcR * Math.cos(a), cy + arcR * Math.sin(a), 1.5, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(v * MAX_ROTATION)

    ctx.lineWidth = Math.max(4, r * 0.13)
    ctx.lineCap   = 'butt'
    ctx.strokeStyle = toRgba([253, 233, 255], 0.18)
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.stroke()

    ctx.strokeStyle = toRgb(auraCol)
    ctx.shadowColor = toRgb(auraCol); ctx.shadowBlur = 16
    ctx.lineWidth = Math.max(2, r * 0.07)
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.stroke()
    ctx.shadowBlur = 0

    ctx.strokeStyle = 'rgba(253,233,255,0.32)'
    ctx.lineWidth = Math.max(2, r * 0.08)
    ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.moveTo(-r * 0.85, 0); ctx.lineTo(-r * 0.18, 0)
    ctx.moveTo( r * 0.18, 0); ctx.lineTo( r * 0.85, 0)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(0, r * 0.18); ctx.lineTo(0, r * 0.85)
    ctx.stroke()
    ctx.lineCap = 'butt'

    ctx.fillStyle = C.cream
    ctx.shadowColor = toRgb(auraCol); ctx.shadowBlur = 8
    ctx.beginPath()
    ctx.moveTo(0, -r + 4)
    ctx.lineTo(-r * 0.10, -r * 0.78)
    ctx.lineTo( r * 0.10, -r * 0.78)
    ctx.closePath(); ctx.fill()
    ctx.shadowBlur = 0

    const hubR = r * 0.22
    const hubG = ctx.createRadialGradient(0, 0, 0, 0, 0, hubR)
    hubG.addColorStop(0, C.cream)
    hubG.addColorStop(1, toRgba(auraCol, 0.4))
    ctx.fillStyle = hubG
    ctx.beginPath(); ctx.arc(0, 0, hubR, 0, Math.PI * 2); ctx.fill()

    ctx.restore()

    if (tier !== 'compact') {
      const deg = Math.round(v * 270)
      ctx.font         = `600 ${tier === 'hero' ? 14 : 12}px "JetBrains Mono", monospace`
      ctx.fillStyle    = C.cream
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'top'
      ctx.shadowColor  = toRgb(auraCol); ctx.shadowBlur = 8
      ctx.fillText(`${deg > 0 ? '+' : ''}${deg}°`, cx, cy + r + 8)
      ctx.shadowBlur = 0
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
