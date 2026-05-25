// client/src/components/widgets/CrashRisk.tsx
import { useRef } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useReplay  } from '@/features/dashboard/context/ReplayContext'
import { ease } from '@/shared/lib/canvasUtils'
import {
  drawRadialGauge, drawSparkline,
  BigNumber,
  EASE_VALUE, EASE_STALE,
} from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'
import { useCrashRiskQuery } from '@/shared/hooks/queries/predictions'

type CrashResp = components['schemas']['CrashRiskPredictionResponse']
type Tier = 'compact' | 'standard' | 'hero'

// crash_risk — half-arc risk gauge (0..1) backed by /api/predict/crashRisk.

const START_RAD = (180 * Math.PI) / 180
const SWEEP_RAD = (180 * Math.PI) / 180
const WAVE_LEN  = 120

const EMPTY_WRAP = 'w-full h-full flex flex-col items-center justify-center gap-2.5 p-3'

const SKELETON =
  'w-3/5 h-6 rounded-lg ' +
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_50%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite]'

const EMPTY_CAPTION = 'font-ui font-normal text-[12px] text-ink-faint'

function renderEmpty(_tier: Tier, caption: string) {
  return (
    <div className={EMPTY_WRAP}>
      <div className={SKELETON} />
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

export interface CrashRiskProps {
  w: number
  h: number
}

export default function CrashRisk({ w, h }: CrashRiskProps) {
  const { active: inReplay } = useReplay()
  const tier: Tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const { currentSession } = useSession()
  const sessionId = currentSession?.id ?? null

  const enabled = !inReplay && !!sessionId
  const { data, error } = useCrashRiskQuery(30, { enabled })

  const valueEaseRef = useRef(0)
  const staleFadeRef = useRef(0)
  const waveRef      = useRef(new Float32Array(WAVE_LEN))
  const waveHeadRef  = useRef(0)
  const dataRef      = useRef<CrashResp | null>(null)
  dataRef.current = data ?? null

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, dt }) => {
    const d = dataRef.current
    if (!d || d.value == null) return

    staleFadeRef.current = ease(staleFadeRef.current, 0, dt, EASE_STALE)
    const target = Math.max(0, Math.min(1, d.value))
    valueEaseRef.current = ease(valueEaseRef.current, target, dt, EASE_VALUE)
    const v = valueEaseRef.current

    waveRef.current[waveHeadRef.current] = v
    waveHeadRef.current = (waveHeadRef.current + 1) % WAVE_LEN

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    if (tier === 'compact') {
      const cx = cw / 2, cy = ch / 2
      const r  = Math.min(cw, ch) * 0.36
      drawRadialGauge(ctx, {
        cx, cy, r, startRad: START_RAD, sweepRad: SWEEP_RAD,
        value: v, tier: 'compact',
      })
    } else {
      const cx = cw / 2
      const cy = tier === 'hero' ? ch * 0.40 : ch * 0.55
      const r  = Math.min(cw, tier === 'hero' ? ch * 0.55 : ch) * 0.36
      drawRadialGauge(ctx, {
        cx, cy, r, startRad: START_RAD, sweepRad: SWEEP_RAD,
        value: v, tier,
      })

      if (tier === 'hero') {
        drawSparkline(ctx, {
          x: 12, y: ch * 0.74, w: cw - 24, h: ch * 0.22,
          buf: waveRef.current, head: waveHeadRef.current,
          baselineRgba: 'rgba(253,233,255,0.06)',
        })
      }
    }

    ctx.globalAlpha = 1
  })

  if (inReplay)                     return renderEmpty(tier, 'Hidden during replay')
  if (!sessionId)                   return renderEmpty(tier, 'No active session')
  if (error)                        return renderEmpty(tier, '—')
  if (!data || data.value == null)  return renderEmpty(tier, 'Analysing risk…')

  const numberGetter = (): BigNumberValueOut => {
    const d = dataRef.current
    if (!d || d.value == null) return { display: '—' }
    const r = Math.max(0, Math.min(1, d.value))
    return { display: `${Math.round(r * 100)}%`, normalized: r }
  }

  return (
    <div className="radial-gauge-wrap crash-risk-wrap">
      <canvas ref={canvasRef} className="widget-canvas" />
      <BigNumber tier={tier} getValue={numberGetter} ignoreStale />
    </div>
  )
}
