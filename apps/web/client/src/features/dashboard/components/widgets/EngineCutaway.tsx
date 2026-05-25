// client/src/components/widgets/EngineCutaway.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, BUTTER_RGB, PINK_RGB, valueColour, toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

// engine_cutaway — stylised engine cross-section with cylinders firing
// in sequence at a rate proportional to RPM.

const REDLINE_PCT = 0.875
const MAX_CYL     = 12

export interface EngineCutawayProps {
  w: number
  h: number
}

export default function EngineCutaway({ w, h }: EngineCutawayProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const staleFadeRef  = useRef(0)
  const rpmRef        = useRef(0)
  const angleRef      = useRef(0)
  const valueRef      = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale   = !frame || (frameAgeMs ?? 0) > 1500
    const maxRpm  = stale ? 8000 : (frame!.engine?.maxRpm  ?? 8000)
    const idleRpm = stale ? 900  : (frame!.engine?.idleRpm ?? 900)
    const rpm     = stale ? 0    : (frame!.engine?.rpm     ?? 0)
    const boost   = stale ? 0    : (frame!.engine?.boost_psi ?? 0)
    const rawCyl  = stale ? 4 : (frame!.world?.numCylinders ?? 4)
    const numCyl  = Math.max(1, Math.min(MAX_CYL, rawCyl || 4))
    const v       = Math.max(0, Math.min(1, (rpm - idleRpm) / Math.max(1, maxRpm - idleRpm)))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)
    rpmRef.current       = ease(rpmRef.current, rpm, dt, 8)
    valueRef.current     = ease(valueRef.current, v, dt, 8)

    const isRunning = !stale && rpm > 50
    const visualRpm = isRunning ? Math.sqrt(rpm) * 3 : 0
    const degPerSec = (visualRpm / 60) * 360
    angleRef.current = (angleRef.current + dt * degPerSec) % 720

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad = 8
    const topPad = tier === 'compact' ? 6 : 22
    const botPad = 12
    const cylAreaW = cw - pad * 2
    const cylAreaH = ch - topPad - botPad
    const cylGap = numCyl > 6 ? 3 : 5
    const cylW = (cylAreaW - cylGap * (numCyl - 1)) / numCyl
    const cylTop = topPad

    const blockX = pad - 4
    const blockY = topPad - 2
    const blockW = cylAreaW + 8
    const blockH = cylAreaH + 4
    const blockGrad = ctx.createLinearGradient(0, blockY, 0, blockY + blockH)
    blockGrad.addColorStop(0,    'rgba(202,166,255,0.08)')
    blockGrad.addColorStop(0.5,  'rgba(202,166,255,0.03)')
    blockGrad.addColorStop(1,    'rgba(202,166,255,0.06)')
    ctx.fillStyle = blockGrad
    roundRectPath(ctx, blockX, blockY, blockW, blockH, 8); ctx.fill()
    ctx.strokeStyle = 'rgba(202,166,255,0.18)'
    ctx.lineWidth   = 1
    roundRectPath(ctx, blockX, blockY, blockW, blockH, 8); ctx.stroke()

    if (valueRef.current > REDLINE_PCT) {
      const redIntensity = (valueRef.current - REDLINE_PCT) / (1 - REDLINE_PCT)
      ctx.strokeStyle = toRgba(PINK_RGB, redIntensity * 0.8)
      ctx.shadowColor = toRgb(PINK_RGB); ctx.shadowBlur = 16 * redIntensity
      ctx.lineWidth = 1.5
      roundRectPath(ctx, blockX, blockY, blockW, blockH, 8); ctx.stroke()
      ctx.shadowBlur = 0
    }

    for (let i = 0; i < numCyl; i++) {
      const x = pad + i * (cylW + cylGap)
      const offset = (i * 720 / numCyl) % 720
      const localAngle = (angleRef.current - offset + 720) % 720

      const inPowerStroke = localAngle >= 360 && localAngle < 540
      const powerProgress = inPowerStroke ? (localAngle - 360) / 180 : 1
      const fireIntensity = isRunning && inPowerStroke ? (1 - powerProgress) : 0

      const pistonNorm = -Math.cos(localAngle * Math.PI / 180)
      const pistonRange = cylAreaH * 0.5
      const pistonTopOffset = cylAreaH * 0.18
      const pistonY = cylTop + pistonTopOffset + (pistonNorm + 1) / 2 * pistonRange

      drawCylinder(ctx, x, cylTop, cylW, cylAreaH, fireIntensity, pistonY, valueRef.current)
    }

    if (tier !== 'compact') {
      ctx.font = '400 9px "Unbounded", system-ui, sans-serif'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'left'; ctx.textBaseline = 'top'
      ctx.fillText(`${numCyl}-CYL`, pad, 6)

      ctx.textAlign = 'right'
      const col = valueColour(valueRef.current)
      ctx.font = '700 13px "JetBrains Mono", monospace'
      ctx.fillStyle = toRgb(col)
      ctx.shadowColor = toRgb(col); ctx.shadowBlur = 6
      ctx.fillText(`${Math.round(rpm).toLocaleString()} RPM`, cw - pad, 4)
      ctx.shadowBlur = 0
    }

    if (tier === 'hero') {
      ctx.font = '500 9px "JetBrains Mono", monospace'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'
      ctx.fillText(`${boost.toFixed(1)} PSI BOOST`, pad, ch - 2)
      ctx.textAlign = 'right'
      const realFires = isRunning ? (rpm / 120) * numCyl : 0
      ctx.fillText(`${Math.round(realFires)} FIRES/S`, cw - pad, ch - 2)
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawCylinder(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  fireIntensity: number, pistonY: number, rpmFrac: number,
): void {
  ctx.fillStyle = '#0a0314'
  roundRectPath(ctx, x, y, w, h, 3); ctx.fill()
  ctx.strokeStyle = 'rgba(253,233,255,0.18)'
  ctx.lineWidth = 1
  roundRectPath(ctx, x, y, w, h, 3); ctx.stroke()

  const pistonH = h * 0.18
  ctx.fillStyle = 'rgba(202,166,255,0.55)'
  roundRectPath(ctx, x + 2, pistonY, w - 4, pistonH, 1.5); ctx.fill()
  ctx.fillStyle = 'rgba(253,233,255,0.30)'
  ctx.fillRect(x + 2, pistonY, w - 4, 1)
  ctx.strokeStyle = 'rgba(202,166,255,0.4)'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(x + w / 2, pistonY + pistonH)
  ctx.lineTo(x + w / 2, y + h - 2)
  ctx.stroke()

  if (fireIntensity > 0) {
    const fireCol: Rgb = rpmFrac > 0.85 ? PINK_RGB : BUTTER_RGB
    const flashGrad = ctx.createLinearGradient(0, y, 0, pistonY)
    flashGrad.addColorStop(0, toRgba(fireCol, 0.0))
    flashGrad.addColorStop(1, toRgba(fireCol, 0.75 * fireIntensity))
    ctx.fillStyle = flashGrad
    roundRectPath(ctx, x + 2, y + 2, w - 4, Math.max(2, pistonY - y - 2), 2); ctx.fill()
    ctx.fillStyle = toRgba([255, 247, 240], fireIntensity)
    ctx.shadowColor = toRgb(fireCol); ctx.shadowBlur = 8 * fireIntensity
    ctx.beginPath(); ctx.arc(x + w / 2, y + 4, 1.5 + fireIntensity, 0, Math.PI * 2); ctx.fill()
    ctx.shadowBlur = 0
  }
}
