// client/src/components/widgets/RpmTape.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB, valueColour, toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

// rpm_tape — horizontal tape gauge.
//
// Tiers (height-driven via declared sizes 4×1 / 6×2 / 8×3):
//   compact  h ≤ 1 : thin bar (10px) + number above
//   standard h = 2 : bar (16px) + zone tints + redline dashed + number
//   hero     h ≥ 3 : waveform panel + separator + bar (22px) + zones + SHIFT flash

const REDLINE_PCT = 0.875
const WAVE_LEN    = 200   // samples in the rolling waveform

export interface RpmTapeProps {
  w: number
  h: number
}

export default function RpmTape({ h }: RpmTapeProps) {
  const tier = h <= 1 ? 'compact' : h <= 2 ? 'standard' : 'hero'

  const valueRef     = useRef(0)
  const staleFadeRef = useRef(0)
  const waveRef      = useRef(new Float32Array(WAVE_LEN))
  const waveHeadRef  = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale   = !frame || (frameAgeMs ?? 0) > 1500
    const maxRpm  = stale ? 8000 : (frame!.engine?.maxRpm  ?? 8000)
    const idleRpm = stale ? 900  : (frame!.engine?.idleRpm ?? 900)
    const rpm     = stale ? 0    : (frame!.engine?.rpm     ?? 0)
    const v       = Math.max(0, Math.min(1, (rpm - idleRpm) / Math.max(1, maxRpm - idleRpm)))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)
    valueRef.current     = ease(valueRef.current, v, dt, 8)
    const cur = valueRef.current
    const col = valueColour(cur)

    // Push to waveform buffer
    waveRef.current[waveHeadRef.current] = cur
    waveHeadRef.current = (waveHeadRef.current + 1) % WAVE_LEN

    drawWidgetBg(ctx, cw, ch)

    const pad = 10
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const barH      = tier === 'compact' ? 10 : tier === 'standard' ? 16 : 22
    const lblH      = tier === 'compact' ? 0  : 14
    const wavePanel = tier === 'hero'    ? Math.floor(ch * 0.42) : 0
    const sepH      = tier === 'hero'    ? 1  : 0
    const barTop    = tier === 'hero'
      ? wavePanel + sepH + 10
      : tier === 'compact'
      ? Math.floor((ch - barH) / 2) + 2
      : Math.floor((ch - barH - lblH) / 2) + 6
    const barW = cw - pad * 2

    // ── Zone tints (standard / hero) ────────────────────────────────────
    if (tier !== 'compact') {
      const zones: Array<[number, number, string]> = [
        [0,             0.50, toRgba(MINT_RGB,   0.06)],
        [0.50,          0.75, toRgba(BUTTER_RGB, 0.06)],
        [0.75,          0.875,toRgba(PINK_RGB,   0.08)],
        [REDLINE_PCT,   1.00, toRgba(PINK_RGB,   0.18)],
      ]
      zones.forEach(([s, e, c]) => {
        const x  = pad + barW * s
        const bw = barW * (e - s)
        ctx.fillStyle = c
        roundRectPath(ctx, x, barTop, bw, barH, 2); ctx.fill()
      })
    }

    // ── Track ────────────────────────────────────────────────────────────
    ctx.fillStyle = C.track
    roundRectPath(ctx, pad, barTop, barW, barH, 5); ctx.fill()

    // ── Gradient fill ────────────────────────────────────────────────────
    const g = ctx.createLinearGradient(pad, 0, pad + barW, 0)
    g.addColorStop(0,    C.mint)
    g.addColorStop(0.5,  C.butter)
    g.addColorStop(0.85, C.pink)
    ctx.fillStyle   = g
    ctx.shadowColor = toRgb(col); ctx.shadowBlur = tier === 'hero' ? 18 : 12
    roundRectPath(ctx, pad, barTop, barW * cur, barH, 5); ctx.fill()
    ctx.shadowBlur = 0

    // ── Redline dashed marker (standard / hero) ──────────────────────────
    if (tier !== 'compact') {
      const rx = pad + barW * REDLINE_PCT
      ctx.strokeStyle = toRgba(PINK_RGB, 0.55)
      ctx.lineWidth   = 1.5
      ctx.setLineDash([4, 3])
      ctx.beginPath(); ctx.moveTo(rx, barTop - 5); ctx.lineTo(rx, barTop + barH + 5); ctx.stroke()
      ctx.setLineDash([])
      ctx.font         = `400 7px "JetBrains Mono", monospace`
      ctx.fillStyle    = toRgba(PINK_RGB, 0.55)
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'top'
      ctx.fillText('REDLINE', rx, barTop + barH + 6)
    }

    // ── RPM number ────────────────────────────────────────────────────────
    const numY     = tier === 'compact' ? barTop - 4 : barTop - 6
    const numSize  = tier === 'compact' ? 13 : tier === 'standard' ? 22 : 28
    const numAlign: CanvasTextAlign = tier === 'hero' ? 'left' : 'center'
    const numX     = tier === 'hero' ? pad : cw / 2

    ctx.font         = `700 ${numSize}px "JetBrains Mono", monospace`
    ctx.fillStyle    = C.cream
    ctx.textAlign    = numAlign
    ctx.textBaseline = 'bottom'
    ctx.shadowColor  = toRgb(col); ctx.shadowBlur = numSize * 0.4
    ctx.fillText(String(Math.round(rpm)), numX, numY)
    ctx.shadowBlur = 0

    ctx.font      = `400 ${Math.max(7, numSize * 0.36)}px "JetBrains Mono", monospace`
    ctx.fillStyle = C.inkFaint
    if (tier === 'hero') {
      ctx.fillText('RPM', numX + numSize * 2.4, numY)
    } else if (tier !== 'compact') {
      ctx.fillText('RPM', cw / 2, numY)
    }

    // ── Hero SHIFT flash ──────────────────────────────────────────────────
    if (tier === 'hero' && cur > REDLINE_PCT) {
      ctx.font         = `700 9px "Unbounded", system-ui, sans-serif`
      ctx.fillStyle    = C.pink
      ctx.textAlign    = 'right'
      ctx.textBaseline = 'bottom'
      ctx.shadowColor  = C.pink; ctx.shadowBlur = 10
      ctx.fillText('SHIFT', cw - pad, numY)
      ctx.shadowBlur = 0
    }

    // ── Hero waveform ─────────────────────────────────────────────────────
    if (tier === 'hero') {
      const waveTop = 8
      const waveH   = wavePanel - 16
      const wave    = waveRef.current
      const head    = waveHeadRef.current

      // Separator
      ctx.strokeStyle = 'rgba(253,233,255,0.08)'
      ctx.lineWidth   = 1
      ctx.beginPath(); ctx.moveTo(pad, wavePanel + 2); ctx.lineTo(cw - pad, wavePanel + 2); ctx.stroke()

      // Reference lines at 25/50/75%
      ctx.lineWidth   = 0.7
      ctx.setLineDash([3, 4])
      for (const ref of [0.25, 0.5, 0.75]) {
        const ry = waveTop + waveH - ref * waveH
        ctx.strokeStyle = `rgba(253,233,255,0.08)`
        ctx.beginPath(); ctx.moveTo(pad, ry); ctx.lineTo(cw - pad, ry); ctx.stroke()
      }
      ctx.setLineDash([])

      // Waveform stroke
      ctx.strokeStyle = toRgba(col, 0.75)
      ctx.lineWidth   = 1.5
      ctx.shadowColor = toRgb(col); ctx.shadowBlur = 5
      ctx.beginPath()
      for (let i = 0; i < WAVE_LEN; i++) {
        const idx = (head - 1 - i + WAVE_LEN) % WAVE_LEN
        const x   = cw - pad - (i * (cw - pad * 2)) / WAVE_LEN
        const y   = waveTop + waveH - (wave[idx] ?? 0) * waveH
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      }
      ctx.stroke(); ctx.shadowBlur = 0

      // Fill under waveform
      ctx.beginPath()
      for (let i = 0; i < WAVE_LEN; i++) {
        const idx = (head - 1 - i + WAVE_LEN) % WAVE_LEN
        const x   = cw - pad - (i * (cw - pad * 2)) / WAVE_LEN
        const y   = waveTop + waveH - (wave[idx] ?? 0) * waveH
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      }
      ctx.lineTo(pad, waveTop + waveH)
      ctx.lineTo(cw - pad, waveTop + waveH)
      ctx.closePath()
      const fg = ctx.createLinearGradient(0, waveTop, 0, waveTop + waveH)
      fg.addColorStop(0, toRgba(col, 0.22)); fg.addColorStop(1, toRgba(col, 0.01))
      ctx.fillStyle = fg; ctx.fill()
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas rpm-tape" />
}
