// client/src/components/widgets/SuspensionViz.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { C, toRgba, ease, drawWidgetBg } from '@/shared/lib/canvasUtils'
import { EASE_STALE } from '@/shared/components/widgetPrimitives'

// suspension_viz — side and back profile of the car body riding on
// visible springs that compress per corner.

const PITCH_SCALE = 0.30
const ROLL_SCALE  = 0.30
const SAG_PX_MAX  = 8

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNER_KEYS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']

export interface SuspensionVizProps {
  w: number
  h: number
}

export default function SuspensionViz({ w, h }: SuspensionVizProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const travelsRef   = useRef(new Float32Array(4))
  const pitchRef     = useRef(0)
  const rollRef      = useRef(0)
  const airtimeRef   = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const wheels = stale ? null : (frame!.wheels ?? null)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)

    let allExtended = !stale
    for (let i = 0; i < 4; i++) {
      const k = CORNER_KEYS[i]!
      const tv = stale ? 0 : Math.min(1, Math.max(0, wheels?.[k]?.suspensionTravel_norm ?? 0))
      travelsRef.current[i] = ease(travelsRef.current[i] ?? 0, tv, dt, 8)
      if ((travelsRef.current[i] ?? 0) > 0.05) allExtended = false
    }
    if (allExtended) airtimeRef.current += dt
    else             airtimeRef.current = 0

    const fl = travelsRef.current[0] ?? 0, fr = travelsRef.current[1] ?? 0
    const rl = travelsRef.current[2] ?? 0, rr = travelsRef.current[3] ?? 0
    const frontAvg = (fl + fr) / 2
    const rearAvg  = (rl + rr) / 2
    const leftAvg  = (fl + rl) / 2
    const rightAvg = (fr + rr) / 2
    pitchRef.current = ease(pitchRef.current, (frontAvg - rearAvg) * PITCH_SCALE, dt, 6)
    rollRef.current  = ease(rollRef.current,  (rightAvg - leftAvg) * ROLL_SCALE,  dt, 6)

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const avgComp = (fl + fr + rl + rr) / 4
    const showSprings = tier !== 'compact'

    if (tier === 'compact') {
      drawSideProfile(ctx, cw / 2, ch / 2 + 8, Math.min(cw, ch) / 200, pitchRef.current, false, frontAvg, rearAvg, avgComp)
      ctx.font = '600 11px "JetBrains Mono", monospace'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'right'; ctx.textBaseline = 'top'
      ctx.fillText(`${(pitchRef.current * 180 / Math.PI).toFixed(1)}°`, cw - 8, 8)
    } else {
      drawSideProfile(ctx, cw / 2, ch * 0.30, Math.min(cw, ch) / 220, pitchRef.current, showSprings, frontAvg, rearAvg, avgComp)
      drawBackProfile(ctx, cw / 2, ch * 0.72, Math.min(cw, ch) / 240, rollRef.current,  showSprings, leftAvg, rightAvg, avgComp)
      ctx.strokeStyle = 'rgba(202,166,255,0.10)'
      ctx.lineWidth = 0.6
      ctx.beginPath(); ctx.moveTo(10, ch * 0.50); ctx.lineTo(cw - 10, ch * 0.50); ctx.stroke()
      ctx.font = '500 11px "Unbounded", system-ui, sans-serif'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'left'; ctx.textBaseline = 'top'
      ctx.fillText('SIDE · PITCH', 8, 6)
      ctx.fillText('BACK · ROLL', 8, ch * 0.50 + 4)
      if (tier === 'hero') {
        ctx.font = '600 12px "JetBrains Mono", monospace'
        ctx.fillStyle = C.cream
        ctx.textAlign = 'right'
        ctx.fillText(`${(pitchRef.current * 180 / Math.PI).toFixed(1)}°`, cw - 8, 6)
        ctx.fillText(`${(rollRef.current  * 180 / Math.PI).toFixed(1)}°`, cw - 8, ch * 0.50 + 4)
      }
      if (airtimeRef.current > 0.15) {
        ctx.font = '700 16px "Unbounded", system-ui, sans-serif'
        ctx.fillStyle = C.butter
        ctx.shadowColor = C.butter; ctx.shadowBlur = 14
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
        ctx.fillText(`AIRTIME ${airtimeRef.current.toFixed(2)}s`, cw / 2, ch * 0.50)
        ctx.shadowBlur = 0
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawSideProfile(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, scale: number,
  pitch: number, withSprings: boolean,
  frontComp: number, rearComp: number, avgComp: number,
): void {
  const bodyW = 100 * scale, bodyH = 30 * scale
  const wheelR = 11 * scale
  const wheelY = cy + 26 * scale
  const groundY = wheelY + wheelR + 4 * scale
  const sag = (avgComp ?? 0) * SAG_PX_MAX * scale * 0.6
  const bodyCy = cy + sag

  ctx.save()
  ctx.translate(cx, bodyCy)
  ctx.rotate(pitch)

  ctx.fillStyle = 'rgba(202,166,255,0.05)'
  ctx.strokeStyle = 'rgba(202,166,255,0.30)'
  ctx.lineWidth = 1.2
  ctx.shadowColor = 'rgba(202,166,255,0.5)'; ctx.shadowBlur = 8
  ctx.beginPath()
  ctx.moveTo(-bodyW / 2 + 4 * scale, 0)
  ctx.lineTo(-bodyW / 2 + 22 * scale, -bodyH * 0.55)
  ctx.lineTo(-bodyW / 2 + 50 * scale, -bodyH * 0.95)
  ctx.lineTo( bodyW / 2 - 22 * scale, -bodyH * 0.65)
  ctx.lineTo( bodyW / 2 - 8  * scale, -bodyH * 0.20)
  ctx.lineTo( bodyW / 2, 0)
  ctx.lineTo( bodyW / 2 - 4  * scale, bodyH * 0.30)
  ctx.lineTo(-bodyW / 2 + 4  * scale, bodyH * 0.30)
  ctx.closePath()
  ctx.fill(); ctx.stroke()
  ctx.shadowBlur = 0

  ctx.fillStyle = 'rgba(184,212,255,0.18)'
  ctx.beginPath()
  ctx.moveTo(-bodyW / 2 + 24 * scale, -bodyH * 0.55)
  ctx.lineTo(-bodyW / 2 + 50 * scale, -bodyH * 0.92)
  ctx.lineTo( bodyW / 2 - 24 * scale, -bodyH * 0.62)
  ctx.lineTo( bodyW / 2 - 10 * scale, -bodyH * 0.20)
  ctx.closePath(); ctx.fill()

  ctx.restore()

  const wheelXLeft  = cx - bodyW / 2 + 22 * scale
  const wheelXRight = cx + bodyW / 2 - 16 * scale
  drawWheel(ctx, wheelXLeft,  wheelY, wheelR)
  drawWheel(ctx, wheelXRight, wheelY, wheelR)

  if (withSprings) {
    const archYWorld = bodyCy + Math.cos(pitch) * (bodyH * 0.30) - 2 * scale
    const archDxRear  = -bodyW / 2 + 22 * scale
    const archDxFront =  bodyW / 2 - 16 * scale
    const topRearX  = cx + Math.cos(pitch) * archDxRear
    const topRearY  = bodyCy + Math.sin(pitch) * archDxRear + (archYWorld - bodyCy)
    const topFrontX = cx + Math.cos(pitch) * archDxFront
    const topFrontY = bodyCy + Math.sin(pitch) * archDxFront + (archYWorld - bodyCy)
    drawSpring(ctx, wheelXLeft,  wheelY - wheelR, topRearX,  topRearY,  rearComp)
    drawSpring(ctx, wheelXRight, wheelY - wheelR, topFrontX, topFrontY, frontComp)
  }

  ctx.strokeStyle = 'rgba(202,166,255,0.18)'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath(); ctx.moveTo(cx - bodyW * 0.8, groundY); ctx.lineTo(cx + bodyW * 0.8, groundY); ctx.stroke()
  ctx.setLineDash([])
}

function drawBackProfile(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, scale: number,
  roll: number, withSprings: boolean,
  leftComp: number, rightComp: number, avgComp: number,
): void {
  const bodyW = 90 * scale, bodyH = 38 * scale
  const wheelR = 10 * scale
  const wheelY = cy + 30 * scale
  const groundY = wheelY + wheelR + 4 * scale
  const sag = (avgComp ?? 0) * SAG_PX_MAX * scale * 0.6
  const bodyCy = cy + sag

  ctx.save()
  ctx.translate(cx, bodyCy)
  ctx.rotate(roll)

  ctx.fillStyle = 'rgba(202,166,255,0.05)'
  ctx.strokeStyle = 'rgba(202,166,255,0.30)'
  ctx.lineWidth = 1.2
  ctx.shadowColor = 'rgba(202,166,255,0.5)'; ctx.shadowBlur = 8
  ctx.beginPath()
  ctx.moveTo(-bodyW / 2,           bodyH * 0.30)
  ctx.lineTo(-bodyW / 2 + 5,       -bodyH * 0.20)
  ctx.lineTo(-bodyW / 2 + 18 * scale, -bodyH * 0.70)
  ctx.lineTo( bodyW / 2 - 18 * scale, -bodyH * 0.70)
  ctx.lineTo( bodyW / 2 - 5,       -bodyH * 0.20)
  ctx.lineTo( bodyW / 2,            bodyH * 0.30)
  ctx.closePath()
  ctx.fill(); ctx.stroke()
  ctx.shadowBlur = 0

  ctx.fillStyle = 'rgba(184,212,255,0.18)'
  ctx.beginPath()
  ctx.moveTo(-bodyW / 2 + 22 * scale, -bodyH * 0.65)
  ctx.lineTo( bodyW / 2 - 22 * scale, -bodyH * 0.65)
  ctx.lineTo( bodyW / 2 - 18 * scale, -bodyH * 0.25)
  ctx.lineTo(-bodyW / 2 + 18 * scale, -bodyH * 0.25)
  ctx.closePath(); ctx.fill()

  ctx.fillStyle = toRgba([255, 94, 167], 0.7)
  ctx.shadowColor = '#ff5ea7'; ctx.shadowBlur = 6
  ctx.fillRect(-bodyW / 2 + 10 * scale, bodyH * 0.05, 12 * scale, 4 * scale)
  ctx.fillRect( bodyW / 2 - 22 * scale, bodyH * 0.05, 12 * scale, 4 * scale)
  ctx.shadowBlur = 0

  ctx.restore()

  const wheelXLeft  = cx - bodyW / 2 + 6 * scale
  const wheelXRight = cx + bodyW / 2 - 6 * scale
  drawWheel(ctx, wheelXLeft,  wheelY, wheelR)
  drawWheel(ctx, wheelXRight, wheelY, wheelR)

  if (withSprings) {
    const archDxLeft  = -bodyW / 2 + 6 * scale
    const archDxRight =  bodyW / 2 - 6 * scale
    const archDy      = bodyH * 0.30 - 2 * scale
    const topLeftX  = cx + Math.cos(roll) * archDxLeft  - Math.sin(roll) * archDy
    const topLeftY  = bodyCy + Math.sin(roll) * archDxLeft  + Math.cos(roll) * archDy
    const topRightX = cx + Math.cos(roll) * archDxRight - Math.sin(roll) * archDy
    const topRightY = bodyCy + Math.sin(roll) * archDxRight + Math.cos(roll) * archDy
    drawSpring(ctx, wheelXLeft,  wheelY - wheelR, topLeftX,  topLeftY,  leftComp)
    drawSpring(ctx, wheelXRight, wheelY - wheelR, topRightX, topRightY, rightComp)
  }

  ctx.strokeStyle = 'rgba(202,166,255,0.18)'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath(); ctx.moveTo(cx - bodyW * 0.9, groundY); ctx.lineTo(cx + bodyW * 0.9, groundY); ctx.stroke()
  ctx.setLineDash([])
}

function drawWheel(ctx: CanvasRenderingContext2D, x: number, y: number, r: number): void {
  ctx.fillStyle = '#0a0314'
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = 'rgba(253,233,255,0.40)'
  ctx.lineWidth = 1.5
  ctx.stroke()
  ctx.fillStyle = C.cream
  ctx.beginPath(); ctx.arc(x, y, r * 0.35, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = 'rgba(253,233,255,0.25)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(x - r * 0.7, y); ctx.lineTo(x + r * 0.7, y)
  ctx.moveTo(x, y - r * 0.7); ctx.lineTo(x, y + r * 0.7)
  ctx.stroke()
}

function drawSpring(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number, x2: number, y2: number,
  compression: number,
): void {
  const dx = x2 - x1, dy = y2 - y1
  const len = Math.hypot(dx, dy)
  if (len < 2) return
  const coils = 7
  const segments = coils * 2
  const c = Math.max(0, Math.min(1, compression))
  const amp = 2.2 + c * 2.6
  ctx.save()
  ctx.translate(x1, y1)
  ctx.rotate(Math.atan2(dy, dx))
  ctx.fillStyle = 'rgba(202,166,255,0.45)'
  ctx.fillRect(-2, -1, 4, 2)
  ctx.fillRect(len - 2, -1, 4, 2)
  ctx.strokeStyle = `rgba(202,166,255,${0.55 + c * 0.35})`
  ctx.lineWidth = 1.3
  ctx.beginPath()
  ctx.moveTo(2, 0)
  for (let i = 1; i < segments; i++) {
    const t = i / segments
    const x = 2 + t * (len - 4)
    const y = (i % 2 === 0) ? -amp : amp
    ctx.lineTo(x, y)
  }
  ctx.lineTo(len - 2, 0)
  ctx.stroke()
  ctx.restore()
}
