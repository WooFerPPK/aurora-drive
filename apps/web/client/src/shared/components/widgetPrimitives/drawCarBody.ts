// client/src/lib/widgetPrimitives/drawCarBody.ts
import { toRgb, toRgba, roundRectPath } from '@/shared/lib/canvasUtils'
import type { Rgb } from '@/shared/lib/canvasUtils'

export interface BorderPulse {
  colourRgb: Rgb
  intensity: number
}

export interface DrawCarBodyOpts {
  cx: number
  cy: number
  cw?: number
  ch?: number
  carW: number
  carH: number
  bodyR?: number
  showArrow?: boolean
  showCenterLine?: boolean
  tireOffsetX?: number
  tireOffsetY?: number
  borderPulse?: BorderPulse | null
}

export interface DrawCarBodyResult {
  corners: Array<{ x: number; y: number }>
  body: { x: number; y: number; w: number; h: number; r: number }
}

export function drawCarBody(ctx: CanvasRenderingContext2D, opts: DrawCarBodyOpts): DrawCarBodyResult {
  const {
    cx, cy, cw, ch, carW, carH,
    bodyR = Math.min(carW, carH) * 0.25,
    showArrow = true,
    showCenterLine = true,
    tireOffsetX = carW * 0.55,
    tireOffsetY = carH * 0.32,
    borderPulse = null,
  } = opts

  const bodyX = cx - carW / 2
  const bodyY = cy - carH / 2

  // Body — lilac translucent gradient + outline
  const bodyG = ctx.createLinearGradient(0, bodyY, 0, bodyY + carH)
  bodyG.addColorStop(0,   'rgba(202,166,255,0.10)')
  bodyG.addColorStop(0.5, 'rgba(202,166,255,0.04)')
  bodyG.addColorStop(1,   'rgba(202,166,255,0.08)')
  ctx.fillStyle = bodyG
  roundRectPath(ctx, bodyX, bodyY, carW, carH, bodyR); ctx.fill()

  ctx.strokeStyle = 'rgba(202,166,255,0.22)'
  ctx.lineWidth = 1
  roundRectPath(ctx, bodyX, bodyY, carW, carH, bodyR); ctx.stroke()

  if (showArrow) {
    const arrowSize = Math.min(carW, carH) * 0.12
    ctx.strokeStyle = 'rgba(202,166,255,0.40)'
    ctx.lineWidth = 1.2; ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.moveTo(cx - arrowSize, bodyY + carH * 0.18)
    ctx.lineTo(cx,             bodyY + carH * 0.10)
    ctx.lineTo(cx + arrowSize, bodyY + carH * 0.18)
    ctx.stroke()
    ctx.lineCap = 'butt'
  }

  if (showCenterLine) {
    ctx.strokeStyle = 'rgba(202,166,255,0.10)'
    ctx.lineWidth = 0.6
    ctx.setLineDash([2, 3])
    ctx.beginPath()
    ctx.moveTo(cx, bodyY + carH * 0.30)
    ctx.lineTo(cx, bodyY + carH * 0.85)
    ctx.stroke()
    ctx.setLineDash([])
  }

  if (borderPulse && borderPulse.intensity > 0 && cw != null && ch != null) {
    const { colourRgb, intensity } = borderPulse
    ctx.strokeStyle = toRgba(colourRgb, intensity * 0.8)
    ctx.shadowColor = toRgb(colourRgb); ctx.shadowBlur = 20
    ctx.lineWidth = 3
    roundRectPath(ctx, 2, 2, cw - 4, ch - 4, 10)
    ctx.stroke()
    ctx.shadowBlur = 0
  }

  const corners = [
    { x: cx - tireOffsetX, y: cy - tireOffsetY }, // FL
    { x: cx + tireOffsetX, y: cy - tireOffsetY }, // FR
    { x: cx - tireOffsetX, y: cy + tireOffsetY }, // RL
    { x: cx + tireOffsetX, y: cy + tireOffsetY }, // RR
  ]

  return { corners, body: { x: bodyX, y: bodyY, w: carW, h: carH, r: bodyR } }
}
