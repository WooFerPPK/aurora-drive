// client/src/components/widgets/SpeedTrace.tsx
import { useEffect, useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { liveClient } from '@/shared/lib/wsClient'
import { useSettings } from '@/features/settings/context/SettingsContext'
import { mpsToKph, mpsToMph } from '@/shared/lib/format'
import {
  C, valueColour, toRgb, toRgba, ease,
  drawWidgetBg,
} from '@/shared/lib/canvasUtils'

const LAP_BUF_LEN = 1800

export interface SpeedTraceProps {
  w: number
  h: number
}

export default function SpeedTrace({ w, h }: SpeedTraceProps) {
  const { settings } = useSettings()
  const unit = settings?.display?.speedUnit === 'mph' ? 'mph' : 'kmh'
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const bufRef   = useRef(new Float32Array(LAP_BUF_LEN))
  const headRef  = useRef(0)
  const lenRef   = useRef(0)
  const peakRef  = useRef(0)
  const sumRef   = useRef(0)
  const staleFadeRef = useRef(0)

  useEffect(() => {
    const off = liveClient.subscribe('event', (evt) => {
      if (evt?.kind === 'lap_completed') {
        bufRef.current.fill(0)
        headRef.current = 0
        lenRef.current  = 0
        peakRef.current = 0
        sumRef.current  = 0
      }
    })
    return off
  }, [])

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const mps   = stale ? 0 : (frame!.motion?.speed_mps ?? 0)
    const spd   = unit === 'mph' ? mpsToMph(mps) : mpsToKph(mps)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    if (!stale) {
      bufRef.current[headRef.current] = spd
      headRef.current = (headRef.current + 1) % LAP_BUF_LEN
      if (lenRef.current < LAP_BUF_LEN) lenRef.current++
      if (spd > peakRef.current) peakRef.current = spd
      sumRef.current = sumRef.current + spd
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad = tier === 'compact' ? 6 : 10
    const headerH = tier === 'compact' ? 0 : 14
    const footerH = tier === 'hero' ? 14 : 0
    const traceTop = pad + headerH
    const traceBottom = ch - pad - footerH
    const traceLeft = pad
    const traceRight = cw - pad
    const traceW = traceRight - traceLeft
    const traceH = traceBottom - traceTop

    const peakSpd = Math.max(50, peakRef.current)
    const scaleMax = Math.ceil(peakSpd / 50) * 50

    if (tier !== 'compact') {
      ctx.strokeStyle = 'rgba(253,233,255,0.06)'
      ctx.lineWidth = 0.6
      ctx.setLineDash([2, 3])
      const refs = tier === 'hero' ? [0.25, 0.5, 0.75] : [0.5]
      for (const ref of refs) {
        const ry = traceBottom - ref * traceH
        ctx.beginPath(); ctx.moveTo(traceLeft, ry); ctx.lineTo(traceRight, ry); ctx.stroke()
      }
      ctx.setLineDash([])
    }

    const len = lenRef.current
    if (len > 0) {
      const head = headRef.current
      const buf  = bufRef.current
      const startIdx = (head - len + LAP_BUF_LEN) % LAP_BUF_LEN

      ctx.beginPath()
      for (let i = 0; i < len; i++) {
        const sample = buf[(startIdx + i) % LAP_BUF_LEN] ?? 0
        const x = traceLeft + (i / Math.max(1, len - 1)) * traceW
        const y = traceBottom - Math.min(1, sample / scaleMax) * traceH
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      }

      const liveCol = valueColour(Math.min(1, spd / scaleMax))
      ctx.strokeStyle = toRgb(liveCol)
      ctx.lineWidth = 1.5
      ctx.shadowColor = toRgb(liveCol); ctx.shadowBlur = 8
      ctx.stroke()
      ctx.shadowBlur = 0

      ctx.lineTo(traceRight, traceBottom)
      ctx.lineTo(traceLeft, traceBottom)
      ctx.closePath()
      const fg = ctx.createLinearGradient(0, traceTop, 0, traceBottom)
      fg.addColorStop(0, toRgba(liveCol, 0.25))
      fg.addColorStop(1, toRgba(liveCol, 0.01))
      ctx.fillStyle = fg
      ctx.fill()
    }

    if (tier !== 'compact') {
      ctx.font = `700 14px "JetBrains Mono", monospace`
      ctx.fillStyle = C.cream
      ctx.textAlign = 'left'
      ctx.textBaseline = 'top'
      const unitLbl = unit === 'mph' ? 'MPH' : 'KM/H'
      ctx.fillText(`${Math.round(spd)} ${unitLbl}`, traceLeft, pad - 1)
      ctx.font = `400 9px "Unbounded", system-ui, sans-serif`
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'right'
      ctx.fillText('CURRENT LAP', traceRight, pad)
    }

    if (tier === 'hero' && len > 0) {
      const avg = sumRef.current / len
      const unitLbl = unit === 'mph' ? 'mph' : 'km/h'
      ctx.font = `400 8px "JetBrains Mono", monospace`
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'left'
      ctx.textBaseline = 'bottom'
      ctx.fillText(`AVG ${Math.round(avg)} ${unitLbl}`, traceLeft, ch - 4)
      ctx.textAlign = 'right'
      ctx.fillText(`PEAK ${Math.round(peakRef.current)} ${unitLbl}`, traceRight, ch - 4)
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
