// client/src/components/widgets/StyleDrift.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, MINT_RGB, PINK_RGB, toRgb, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'
import { useDriverProfileQuery } from '@/shared/hooks/queries/driver'

const TRAITS = ['smooth', 'brave', 'early', 'patient', 'precise', 'consist'] as const
const TRAIT_LABELS = ['SMOOTH', 'BRAVE', 'EARLY', 'PATIENT', 'PRECISE', 'CONSIST'] as const
const SCALE = 0.5

interface TraitDatum { idx: number; label: string; drift: number }

const WRAP = 'relative w-full h-full'

const OVERLAY =
  'absolute inset-0 flex items-center justify-center rounded-lg pointer-events-none ' +
  '[background:linear-gradient(180deg,rgba(20,18,30,0.6)_0%,rgba(20,18,30,0.85)_100%)]'

const OVERLAY_CAPTION = 'font-ui font-normal text-[12px] text-ink-faint'

export interface StyleDriftProps {
  w: number
  h: number
}

export default function StyleDrift({ w, h }: StyleDriftProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const { data: profile, error: err } = useDriverProfileQuery()
  const driftRef = useRef(new Float32Array(6))

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, dt }) => {
    if (!profile?.fingerprint || !profile?.fingerprintBaseline90d) return
    drawWidgetBg(ctx, cw, ch)

    const fp   = profile.fingerprint as Record<string, number>
    const base = profile.fingerprintBaseline90d as Record<string, number>

    const traitData: TraitDatum[] = []
    for (let i = 0; i < 6; i++) {
      const t = TRAITS[i]!
      const d = (fp[t] ?? 0) - (base[t] ?? 0)
      driftRef.current[i] = ease(driftRef.current[i] ?? 0, Math.max(-SCALE, Math.min(SCALE, d)), dt, 4)
      traitData.push({ idx: i, label: TRAIT_LABELS[i]!, drift: driftRef.current[i] ?? 0 })
    }

    const visible = tier === 'compact'
      ? [...traitData].sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift)).slice(0, 3)
      : traitData

    const pad = 10
    const headerH = 6
    const rowGap = 4
    const availH = ch - headerH - pad
    const rowH = Math.min(28, (availH - (visible.length - 1) * rowGap) / visible.length)
    const labelW = tier === 'hero' ? 60 : 50
    const valueW = tier === 'hero' ? 40 : 0
    const barX = pad + labelW
    const barW = cw - barX - pad - valueW
    const barMid = barX + barW / 2

    ctx.strokeStyle = 'rgba(253,233,255,0.12)'
    ctx.lineWidth = 0.7
    ctx.beginPath()
    ctx.moveTo(barMid, headerH)
    ctx.lineTo(barMid, headerH + visible.length * (rowH + rowGap))
    ctx.stroke()

    for (let i = 0; i < visible.length; i++) {
      const td = visible[i]!
      const y = headerH + i * (rowH + rowGap)
      const barCY = y + rowH / 2

      ctx.font = `500 ${tier === 'hero' ? 9 : 8}px "Unbounded", system-ui, sans-serif`
      ctx.fillStyle = C.cream
      ctx.textAlign = 'right'
      ctx.textBaseline = 'middle'
      ctx.fillText(td.label, barX - 6, barCY)

      ctx.fillStyle = 'rgba(255,193,220,0.06)'
      const trackY = barCY - 3
      roundRectPath(ctx, barX, trackY, barW, 6, 3)
      ctx.fill()

      const driftMag = Math.abs(td.drift)
      const fillW = (driftMag / SCALE) * (barW / 2)
      const isPositive = td.drift > 0
      const fillCol = isPositive ? MINT_RGB : PINK_RGB
      const fx = isPositive ? barMid : barMid - fillW
      ctx.fillStyle = toRgb(fillCol)
      ctx.shadowColor = toRgb(fillCol); ctx.shadowBlur = 6
      roundRectPath(ctx, fx, trackY, fillW, 6, 3)
      ctx.fill()
      ctx.shadowBlur = 0

      if (tier === 'hero') {
        const sign = td.drift >= 0 ? '+' : ''
        ctx.font = `600 9px "JetBrains Mono", monospace`
        ctx.fillStyle = toRgb(fillCol)
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(`${sign}${td.drift.toFixed(2)}`, barX + barW + 4, barCY)
      }
    }
  })

  const showEmpty = err || !profile || !profile.fingerprintBaseline90d
  const emptyCaption = err ? '—' : !profile ? 'Loading profile…' : 'No baseline yet'

  return (
    <div className={WRAP}>
      <canvas ref={canvasRef} className="widget-canvas" />
      {showEmpty && (
        <div className={OVERLAY}>
          <div className={OVERLAY_CAPTION}>{emptyCaption}</div>
        </div>
      )}
    </div>
  )
}
