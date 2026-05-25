// client/src/components/widgets/LapPredict.tsx
import type { CSSProperties } from 'react'
import { useSession  } from '@/features/sessions/context/SessionContext'
import { useReplay   } from '@/features/dashboard/context/ReplayContext'
import { cx, formatLapTime } from '@/shared/lib/format'
import { useLapPredictionQuery } from '@/shared/hooks/queries/predictions'

// lap_predict — projected next N laps with confidence bands.

type Tier = 'compact' | 'standard' | 'hero'

const WRAP = 'w-full h-full flex flex-col justify-center gap-1 px-[10px] py-[6px]'
const WRAP_EMPTY = 'justify-start pt-2'

const ROW =
  'relative grid grid-cols-[auto_1fr_auto] items-baseline gap-2 px-[6px] py-[4px] rounded-md overflow-hidden'

const CONF_FILL =
  'absolute inset-0 rounded-md pointer-events-none ' +
  '[background:linear-gradient(90deg,color-mix(in_srgb,var(--mint)_25%,transparent)_0%,transparent_100%)] ' +
  '[width:calc(var(--conf,0)*100%)]'

const LAP_BASE = 'relative font-mono font-medium text-[12px] text-lilac'
const LAP_STANDARD = 'text-[14px]'
const LAP_HERO = 'text-[16px]'

const VAL_BASE =
  'relative font-mono font-bold text-[14px] text-ink-faint [font-variant-numeric:tabular-nums]'
const VAL_HERO = 'text-[16px]'

const VAL_FIRST_BASE =
  'text-[18px] text-cream ' +
  '[text-shadow:0_0_10px_color-mix(in_srgb,var(--mint)_50%,transparent)]'
const VAL_FIRST_HERO = 'text-[20px]'

const BAND_BASE = 'relative font-mono font-normal text-[12px] text-ink-faint'
const BAND_STANDARD = 'text-[14px]'
const BAND_HERO = 'text-[16px]'

const LIMITER_BASE =
  'font-display font-medium text-[8px] tracking-[0.12em] text-butter text-center mt-1'
const LIMITER_HERO = 'text-[13px]'

const SKELETON_ROW =
  'grid grid-cols-[24px_1fr_36px] items-center gap-2 px-[6px] h-5 rounded-md mb-1 ' +
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_35%,rgba(255,94,167,0.05)_70%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite]'

const SKELETON_SPAN_ALL = 'h-2 rounded bg-[rgba(253,233,255,0.18)]'

const EMPTY_CAPTION =
  'font-ui font-normal text-[9px] text-ink-faint text-center mt-1 tracking-[0.05em]'

function SkeletonRow({ delay }: { delay: number }) {
  return (
    <div className={SKELETON_ROW} style={{ animationDelay: `${delay}s` }}>
      <span className={cx(SKELETON_SPAN_ALL, 'w-4')} />
      <span className={cx(SKELETON_SPAN_ALL, 'h-2.5 w-[60%] justify-self-start')} />
      <span className={cx(SKELETON_SPAN_ALL, 'w-6 justify-self-end')} />
    </div>
  )
}

function renderEmpty(tier: Tier, caption: string) {
  const skeletonCount = tier === 'compact' ? 1 : tier === 'standard' ? 3 : 5
  const rows = []
  for (let i = 0; i < skeletonCount; i++) {
    rows.push(<SkeletonRow key={i} delay={i * 0.12} />)
  }
  return (
    <div className={cx(WRAP, WRAP_EMPTY)}>
      {rows}
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

export interface LapPredictProps {
  w: number
  h: number
}

export default function LapPredict({ w, h }: LapPredictProps) {
  const { active: inReplay } = useReplay()
  const tier: Tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'
  const nWanted = tier === 'compact' ? 1 : tier === 'standard' ? 3 : 5

  const { currentSession } = useSession()
  const sessionId = currentSession?.id ?? null

  const { data, error } = useLapPredictionQuery(sessionId, nWanted, { enabled: !inReplay })

  if (inReplay)                  return renderEmpty(tier, 'Hidden during replay')
  if (!sessionId)                return renderEmpty(tier, 'No active session')
  if (error)                     return renderEmpty(tier, '—')
  if (!data)                     return renderEmpty(tier, 'Predicting…')
  if (!data.predictions?.length) return renderEmpty(tier, 'Need a lap to predict')

  const lapCls   = cx(LAP_BASE, tier === 'standard' && LAP_STANDARD, tier === 'hero' && LAP_HERO)
  const bandCls  = cx(BAND_BASE, tier === 'standard' && BAND_STANDARD, tier === 'hero' && BAND_HERO)

  return (
    <div className={WRAP}>
      {data.predictions.slice(0, nWanted).map((p, i) => {
        const conf = Math.max(0, Math.min(1, p.confidence))
        const band = (p.upper_s - p.time_s).toFixed(2)
        const style = { '--conf': conf } as CSSProperties
        const isFirst = i === 0
        const valCls = cx(
          VAL_BASE,
          tier === 'hero' && VAL_HERO,
          isFirst && VAL_FIRST_BASE,
          isFirst && tier === 'hero' && VAL_FIRST_HERO,
        )
        return (
          <div className={ROW} key={p.lap}>
            <div className={CONF_FILL} style={style} />
            <span className={lapCls}>L{p.lap}</span>
            <span className={valCls} {...(isFirst ? { 'data-first': '' } : {})}>
              {formatLapTime(p.time_s)}
            </span>
            {tier !== 'compact' && <span className={bandCls}>±{band}s</span>}
          </div>
        )
      })}
      {tier === 'hero' && data.limiter && (
        <div className={cx(LIMITER_BASE, LIMITER_HERO)}>LIMITED BY {data.limiter}</div>
      )}
    </div>
  )
}
