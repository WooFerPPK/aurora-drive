// client/src/components/widgets/DynoPlot.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, BUTTER_RGB, toRgb, toRgba, ease,
  drawWidgetBg,
} from '@/shared/lib/canvasUtils'

// dyno_plot — live power + torque curves vs RPM. The widget builds the
// dyno graph by sampling peak power/torque at each RPM bin as you rev
// through. After a few minutes of driving you see your actual car's
// power band emerge.

const RPM_BINS = 80     // 80 bins from idle → maxRpm
const HORSEPOWER_W = 745.7

export interface DynoPlotProps {
  w: number
  h: number
}

export default function DynoPlot({ w, h }: DynoPlotProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const staleFadeRef    = useRef(0)
  const powerCurveRef   = useRef(new Float32Array(RPM_BINS))
  const torqueCurveRef  = useRef(new Float32Array(RPM_BINS))
  const maxHpRef        = useRef(0)
  const maxTqRef        = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale   = !frame || (frameAgeMs ?? 0) > 1500
    const maxRpm  = stale ? 8000 : (frame!.engine?.maxRpm  ?? 8000)
    const idleRpm = stale ? 900  : (frame!.engine?.idleRpm ?? 900)
    const rpm     = stale ? 0    : (frame!.engine?.rpm     ?? 0)
    const powerW  = stale ? 0    : (frame!.engine?.power_w   ?? 0)
    const torqueN = stale ? 0    : (frame!.engine?.torque_nm ?? 0)
    const hp      = powerW / HORSEPOWER_W
    const tq      = torqueN * 0.7376

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    if (!stale && rpm > idleRpm && rpm < maxRpm) {
      const bin = Math.min(RPM_BINS - 1, Math.floor((rpm - idleRpm) / (maxRpm - idleRpm) * RPM_BINS))
      if (hp > (powerCurveRef.current[bin] ?? 0)) powerCurveRef.current[bin] = hp
      if (tq > (torqueCurveRef.current[bin] ?? 0)) torqueCurveRef.current[bin] = tq
      if (hp > maxHpRef.current) maxHpRef.current = hp
      if (tq > maxTqRef.current) maxTqRef.current = tq
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const peakHp = Math.max(50, maxHpRef.current)
    const peakTq = Math.max(50, maxTqRef.current)
    const rpmFrac = Math.max(0, Math.min(1, (rpm - idleRpm) / Math.max(1, maxRpm - idleRpm)))

    if (tier === 'compact') {
      const barW = cw - 32
      const barX = 16
      const barY = 22
      ctx.strokeStyle = 'rgba(202,166,255,0.20)'
      ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(barX, barY); ctx.lineTo(barX + barW, barY); ctx.stroke()
      const mx = barX + barW * rpmFrac
      ctx.fillStyle = toRgb(MINT_RGB)
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 6
      ctx.beginPath(); ctx.arc(mx, barY, 3, 0, Math.PI * 2); ctx.fill()
      ctx.shadowBlur = 0

      const cx = cw / 2
      const cy = ch / 2 + 8

      ctx.font = '700 22px "JetBrains Mono", monospace'
      ctx.fillStyle = toRgb(MINT_RGB)
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 10
      ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'
      ctx.fillText(String(Math.round(hp)), cx, cy - 2)
      ctx.shadowBlur = 0
      ctx.font = '600 11px "JetBrains Mono", monospace'
      ctx.fillStyle = toRgba(MINT_RGB, 0.7)
      ctx.fillText('HP', cx, cy + 12)

      ctx.font = '700 14px "JetBrains Mono", monospace'
      ctx.fillStyle = toRgb(BUTTER_RGB)
      ctx.textBaseline = 'bottom'
      ctx.fillText(`${Math.round(tq)} LB·FT`, cx, ch - 6)
    } else {
      const pad = 10
      const labelH = 16
      const chartTop = labelH + 4
      const chartBot = ch - 8
      const chartLeft = pad + 8
      const chartRight = cw - pad
      const chartW = chartRight - chartLeft
      const chartH = chartBot - chartTop

      ctx.strokeStyle = 'rgba(253,233,255,0.06)'
      ctx.lineWidth = 0.6
      ctx.setLineDash([2, 3])
      for (const ref of [0.25, 0.5, 0.75]) {
        const y = chartBot - ref * chartH
        ctx.beginPath(); ctx.moveTo(chartLeft, y); ctx.lineTo(chartRight, y); ctx.stroke()
      }
      ctx.setLineDash([])

      drawCurve(ctx, powerCurveRef.current, peakHp, chartLeft, chartTop, chartW, chartH, MINT_RGB, 1.5)
      if (tier === 'hero') {
        drawCurve(ctx, torqueCurveRef.current, peakTq, chartLeft, chartTop, chartW, chartH, BUTTER_RGB, 1.2)
      }

      const curX = chartLeft + rpmFrac * chartW
      const curHpY = chartBot - Math.min(1, hp / peakHp) * chartH
      ctx.fillStyle = C.cream
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 10
      ctx.beginPath(); ctx.arc(curX, curHpY, 4, 0, Math.PI * 2); ctx.fill()
      ctx.shadowBlur = 0

      ctx.font = '700 14px "JetBrains Mono", monospace'
      ctx.fillStyle = toRgb(MINT_RGB)
      ctx.textAlign = 'right'; ctx.textBaseline = 'top'
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 6
      ctx.fillText(`${Math.round(hp)} HP`, chartRight, 4)
      ctx.shadowBlur = 0

      if (tier === 'hero') {
        ctx.font = '600 10px "JetBrains Mono", monospace'
        ctx.fillStyle = toRgb(BUTTER_RGB)
        ctx.fillText(`${Math.round(tq)} LB·FT`, chartRight, 20)
      }

      if (tier === 'hero' && maxHpRef.current > 0) {
        ctx.font = '400 12px "JetBrains Mono", monospace'
        ctx.fillStyle = C.inkFaint
        ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'
        ctx.fillText(`PEAK ${Math.round(maxHpRef.current)} HP`, chartRight, ch - 4)
        ctx.textAlign = 'left'
        ctx.fillText(`@ ${Math.round(idleRpm + rpmFrac * (maxRpm - idleRpm))} RPM`, chartLeft, ch - 4)
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawCurve(
  ctx: CanvasRenderingContext2D,
  samples: Float32Array,
  peak: number,
  x: number, y: number, w: number, h: number,
  colRgb: Rgb,
  lineWidth: number,
): void {
  let firstBin = -1
  for (let i = 0; i < samples.length; i++) {
    if ((samples[i] ?? 0) > 0) { firstBin = i; break }
  }
  if (firstBin < 0) return

  ctx.strokeStyle = toRgb(colRgb)
  ctx.lineWidth = lineWidth
  ctx.shadowColor = toRgb(colRgb); ctx.shadowBlur = 5
  ctx.beginPath()
  let started = false
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i] ?? 0
    if (v <= 0) continue
    const px = x + (i / (samples.length - 1)) * w
    const py = y + h - (v / peak) * h
    if (!started) { ctx.moveTo(px, py); started = true }
    else           ctx.lineTo(px, py)
  }
  ctx.stroke(); ctx.shadowBlur = 0

  ctx.beginPath()
  started = false
  let lastX = x
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i] ?? 0
    if (v <= 0) continue
    const px = x + (i / (samples.length - 1)) * w
    const py = y + h - (v / peak) * h
    if (!started) { ctx.moveTo(px, py); started = true }
    else           ctx.lineTo(px, py)
    lastX = px
  }
  ctx.lineTo(lastX, y + h)
  ctx.lineTo(x + (firstBin / (samples.length - 1)) * w, y + h)
  ctx.closePath()
  const fg = ctx.createLinearGradient(0, y, 0, y + h)
  fg.addColorStop(0, toRgba(colRgb, 0.20)); fg.addColorStop(1, toRgba(colRgb, 0.01))
  ctx.fillStyle = fg
  ctx.fill()
}
