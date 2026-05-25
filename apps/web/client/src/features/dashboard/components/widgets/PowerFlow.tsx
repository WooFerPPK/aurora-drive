// client/src/components/widgets/PowerFlow.tsx
import { useRef } from 'react'
import type { Rgb } from '@/shared/lib/canvasUtils'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB, toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

// power_flow — animated engine → drivetrain → wheels visualization.

const HORSEPOWER_W = 745.7
const PARTICLE_COUNT = 24

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNER_KEYS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']

const ENGINE_X = 0.20
const TRANS_X  = 0.50
const WHEEL_X  = 0.78
const WHEEL_Y = [0.30, 0.30, 0.70, 0.70]

export interface PowerFlowProps {
  w: number
  h: number
}

export default function PowerFlow({ w, h }: PowerFlowProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const partProgressRef = useRef(new Float32Array(PARTICLE_COUNT))
  const partWheelRef    = useRef(new Int8Array(PARTICLE_COUNT))
  const partScatterRef  = useRef(new Float32Array(PARTICLE_COUNT))
  const powerRef        = useRef(0)
  const slipsRef        = useRef(new Float32Array(4))

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const powerW = stale ? 0 : (frame!.engine?.power_w ?? 0)
    const torqueN = stale ? 0 : (frame!.engine?.torque_nm ?? 0)
    const rawDt: unknown = stale ? 'AWD' : (frame!.drivetrain?.type ?? 'AWD')
    // Backend sends strings; some sandbox/test paths pass 0/1/2.
    const drivetrain = rawDt === 0 || rawDt === '0' ? 'FWD'
                     : rawDt === 1 || rawDt === '1' ? 'RWD'
                     : rawDt === 2 || rawDt === '2' ? 'AWD'
                     : typeof rawDt === 'string' ? rawDt
                     : 'AWD'
    const wheels = stale ? null : (frame!.wheels ?? null)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)
    powerRef.current = ease(powerRef.current, powerW, dt, 4)

    for (let i = 0; i < 4; i++) {
      const k = CORNER_KEYS[i]!
      const s = stale ? 0 : Math.min(1, Math.abs(wheels?.[k]?.combinedSlip ?? 0))
      slipsRef.current[i] = ease(slipsRef.current[i] ?? 0, s, dt, 6)
    }

    const driveWheels: number[] = drivetrain === 'FWD' ? [0, 1]
                                : drivetrain === 'RWD' ? [2, 3]
                                : [0, 1, 2, 3]

    const hp = powerRef.current / HORSEPOWER_W
    const particleSpeed = Math.max(0.05, Math.min(3, hp / 200))

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      partProgressRef.current[i] = (partProgressRef.current[i] ?? 0) + dt * particleSpeed * (0.7 + (i % 3) * 0.15)
      partScatterRef.current[i] = Math.max(0, (partScatterRef.current[i] ?? 0) - dt * 2)
      if ((partProgressRef.current[i] ?? 0) >= 1) {
        partProgressRef.current[i] = 0
        const wheelChoice = driveWheels[i % driveWheels.length]!
        partWheelRef.current[i] = wheelChoice
        if ((slipsRef.current[wheelChoice] ?? 0) > 0.40) {
          partScatterRef.current[i] = 1
        }
      }
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const ex = cw * ENGINE_X
    const ey = ch / 2
    const tx = cw * TRANS_X
    const ty = ch / 2
    const wx = cw * WHEEL_X
    const wheelPositions = WHEEL_Y.map(yf => ({ x: wx, y: ch * yf }))

    ctx.strokeStyle = 'rgba(202,166,255,0.10)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(ex, ey); ctx.lineTo(tx, ty)
    ctx.stroke()
    for (const wi of driveWheels) {
      const wp = wheelPositions[wi]!
      ctx.beginPath()
      ctx.moveTo(tx, ty)
      ctx.lineTo(wp.x, wp.y)
      ctx.stroke()
    }

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const progress = partProgressRef.current[i] ?? 0
      const wheelIdx = partWheelRef.current[i] ?? 0
      if (!driveWheels.includes(wheelIdx)) continue

      let px: number, py: number
      if (progress < 0.5) {
        const t = progress / 0.5
        px = ex + (tx - ex) * t
        py = ey + (ty - ey) * t
      } else {
        const t = (progress - 0.5) / 0.5
        const wp = wheelPositions[wheelIdx]!
        px = tx + (wp.x - tx) * t
        py = ty + (wp.y - ty) * t
      }

      const scatter = partScatterRef.current[i] ?? 0
      const colRgb: Rgb = scatter > 0.1 ? PINK_RGB : (hp > 250 ? BUTTER_RGB : MINT_RGB)
      ctx.fillStyle = toRgba(colRgb, 0.85)
      ctx.shadowColor = toRgb(colRgb); ctx.shadowBlur = 6
      ctx.beginPath()
      ctx.arc(px, py, 2.5, 0, Math.PI * 2)
      ctx.fill()
      ctx.shadowBlur = 0
    }

    drawEngine(ctx, ex, ey, 22, hp)
    drawTransmission(ctx, tx, ty, 18)
    for (let i = 0; i < 4; i++) {
      const wp = wheelPositions[i]!
      const isDrive = driveWheels.includes(i)
      const slip = slipsRef.current[i] ?? 0
      drawWheelNode(ctx, wp.x, wp.y, 12, isDrive, slip)
    }

    if (tier !== 'compact') {
      ctx.font = '500 10px "Unbounded", system-ui, sans-serif'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'left'; ctx.textBaseline = 'top'
      ctx.fillText(drivetrain, 8, 6)

      ctx.font = '700 14px "JetBrains Mono", monospace'
      ctx.fillStyle = hp > 250 ? toRgb(BUTTER_RGB) : toRgb(MINT_RGB)
      ctx.textAlign = 'right'
      ctx.shadowColor = ctx.fillStyle as string; ctx.shadowBlur = 6
      ctx.fillText(`${Math.round(hp)} HP`, cw - 8, 4)
      ctx.shadowBlur = 0
      if (tier === 'hero') {
        ctx.font = '500 9px "JetBrains Mono", monospace'
        ctx.fillStyle = toRgb(BUTTER_RGB)
        ctx.fillText(`${Math.round(torqueN * 0.7376)} LB·FT`, cw - 8, 22)
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawEngine(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, hp: number): void {
  ctx.fillStyle = '#0a0314'
  roundRectPath(ctx, cx - r, cy - r * 0.7, r * 2, r * 1.4, 4); ctx.fill()
  const glow = Math.min(1, hp / 400)
  ctx.strokeStyle = toRgba(BUTTER_RGB, 0.5 + glow * 0.4)
  ctx.shadowColor = toRgb(BUTTER_RGB); ctx.shadowBlur = 6 + glow * 8
  ctx.lineWidth = 1.5
  roundRectPath(ctx, cx - r, cy - r * 0.7, r * 2, r * 1.4, 4); ctx.stroke()
  ctx.shadowBlur = 0
  for (let i = 0; i < 4; i++) {
    const x = cx - r + 4 + i * ((r * 2 - 8) / 3.5)
    ctx.fillStyle = toRgba(BUTTER_RGB, 0.25)
    ctx.fillRect(x, cy - r * 0.5, 3, r * 1.0)
  }
}

function drawTransmission(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number): void {
  ctx.fillStyle = '#0a0314'
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = toRgba([202, 166, 255], 0.6)
  ctx.shadowColor = '#caa6ff'; ctx.shadowBlur = 6
  ctx.lineWidth = 1.5
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()
  ctx.shadowBlur = 0
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2
    const x1 = cx + (r - 2) * Math.cos(a)
    const y1 = cy + (r - 2) * Math.sin(a)
    const x2 = cx + (r + 3) * Math.cos(a)
    const y2 = cy + (r + 3) * Math.sin(a)
    ctx.strokeStyle = 'rgba(202,166,255,0.4)'
    ctx.lineWidth = 1.5
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
  }
  ctx.fillStyle = C.cream
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.25, 0, Math.PI * 2); ctx.fill()
}

function drawWheelNode(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, r: number,
  isDrive: boolean, slip: number,
): void {
  let ringCol: string
  if (!isDrive)        ringCol = 'rgba(253,233,255,0.20)'
  else if (slip > 0.4) ringCol = toRgb(PINK_RGB)
  else if (slip > 0.15) ringCol = toRgb(BUTTER_RGB)
  else                  ringCol = toRgb(MINT_RGB)

  ctx.fillStyle = '#0a0314'
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = ringCol
  if (isDrive) { ctx.shadowColor = ringCol; ctx.shadowBlur = 6 }
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()
  ctx.shadowBlur = 0
  ctx.fillStyle = ringCol
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.35, 0, Math.PI * 2); ctx.fill()
}
