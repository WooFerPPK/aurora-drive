// client/src/components/widgets/LapTable.tsx
import { useMemo } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useSession } from '@/features/sessions/context/SessionContext'
import { cx, formatLapTime, mpsToKph } from '@/shared/lib/format'
import { useSessionDetailQuery } from '@/shared/hooks/queries/sessions'
import { REFETCH } from '@/shared/hooks/queries/intervals'
import { MetricLabel } from '@/shared/components/widgetPrimitives'

type LapRollup = components['schemas']['LapRollup']
type Tier = 'compact' | 'standard' | 'hero'

const WRAP = 'w-full h-full flex flex-col px-2.5 py-1.5 gap-1 overflow-hidden'
const WRAP_COMPACT = 'justify-center items-center'

const COMPACT_LAP = 'font-mono font-medium text-[14px] text-lilac [letter-spacing:0.1em]'

const COMPACT_TIME =
  'font-mono font-bold text-cream [font-variant-numeric:tabular-nums] ' +
  '[font-size:clamp(22px,9cqi,38px)] ' +
  '[text-shadow:0_0_14px_color-mix(in_srgb,var(--mint)_50%,transparent)]'

const GRID = 'flex flex-col flex-1 min-h-0 overflow-hidden'

const ROW_GRID_BASE = 'grid grid-cols-[32px_1fr_60px] items-center gap-2 px-1.5 py-0.5'
const ROW_GRID_HERO = 'grid-cols-[32px_1fr_60px_50px]'

const HEADROW_BASE =
  'font-display font-normal text-[12px] [letter-spacing:0.18em] text-ink-faint ' +
  'border-b border-[rgba(253,233,255,0.08)]'
const HEADROW_STANDARD = 'text-[14px]'
const HEADROW_HERO     = 'text-[16px]'

// .lt2-rows kept as marker for the vendor-pseudo scrollbar skin in index.css.
const ROWS = 'lt2-rows flex-1 overflow-y-auto min-h-0'

const ROW = 'rounded [transition:background_150ms]'
const ROW_BEST = 'bg-[color:color-mix(in_srgb,var(--mint)_10%,transparent)]'
const ROW_HERO = 'px-1.5 py-0.5'

const LAP_BASE = 'font-mono font-medium text-[9px] text-lilac'
const LAP_STANDARD = 'text-[14px]'
const LAP_HERO = 'text-[16px]'

const TIME_BASE = 'font-mono font-semibold text-[12px] text-cream [font-variant-numeric:tabular-nums]'
const TIME_HERO = 'text-[16px]'

const DELTA_BASE =
  'font-mono font-medium text-[9px] text-right [font-variant-numeric:tabular-nums] text-ink-faint ' +
  'data-[sign=best]:text-mint data-[sign=best]:font-bold ' +
  'data-[sign=down]:text-pink'
const DELTA_STANDARD = 'text-[14px]'
const DELTA_HERO = 'text-[16px]'

const TOP_BASE = 'font-mono font-medium text-[9px] text-butter text-right [font-variant-numeric:tabular-nums]'
const TOP_HERO = 'text-[16px]'

const SKELETON_ROWS = 'flex flex-col gap-1 flex-1 pt-1'
const SKELETON_ROW =
  'h-[18px] rounded ' +
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_50%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite]'

const EMPTY_CAPTION = 'font-ui font-normal text-[9px] text-ink-faint text-center mt-1'

function renderEmpty(tier: Tier, caption: string) {
  const rows = []
  const rc = tier === 'compact' ? 1 : tier === 'standard' ? 4 : 6
  for (let i = 0; i < rc; i++) {
    rows.push(<div key={i} className={SKELETON_ROW} style={{ animationDelay: `${i * 0.10}s` }} />)
  }
  return (
    <div className={WRAP}>
      <div className={SKELETON_ROWS}>{rows}</div>
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

export interface LapTableProps {
  w: number
  h: number
}

export default function LapTable({ w, h }: LapTableProps) {
  const tier: Tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const { currentSession, loadedSessionId } = useSession()
  const sessionId = loadedSessionId ?? currentSession?.id ?? null

  const { data, error: err } = useSessionDetailQuery(sessionId, { refetchInterval: REFETCH.lapTable })
  const rollups: LapRollup[] | null = data ? (data.lapRollups ?? []) : null

  const bestLap = useMemo<LapRollup | null>(() => {
    if (!rollups) return null
    let best: LapRollup | null = null
    for (const r of rollups) {
      if (r.timeS != null && r.timeS > 0 && (best == null || r.timeS < (best.timeS ?? Infinity))) {
        best = r
      }
    }
    return best
  }, [rollups])

  if (!sessionId)         return renderEmpty(tier, 'No session loaded')
  if (err)                return renderEmpty(tier, '—')
  if (rollups == null)    return renderEmpty(tier, 'Loading laps…')
  if (rollups.length === 0) return renderEmpty(tier, 'No completed laps')

  if (tier === 'compact') {
    return (
      <div className={cx(WRAP, WRAP_COMPACT)}>
        <div><MetricLabel text="BEST LAP" tier={tier} /></div>
        <div className={COMPACT_LAP}>L{bestLap?.lap ?? '—'}</div>
        <div className={COMPACT_TIME}>{formatLapTime(bestLap?.timeS)}</div>
      </div>
    )
  }

  const ordered = [...rollups].sort((a, b) => (b.lap ?? 0) - (a.lap ?? 0))
  const visible = tier === 'standard' ? ordered.slice(0, 5) : ordered

  const headCls  = cx(ROW_GRID_BASE, tier === 'hero' && ROW_GRID_HERO,
                      HEADROW_BASE, tier === 'standard' && HEADROW_STANDARD, tier === 'hero' && HEADROW_HERO)
  const lapCls   = cx(LAP_BASE, tier === 'standard' && LAP_STANDARD, tier === 'hero' && LAP_HERO)
  const timeCls  = cx(TIME_BASE, tier === 'hero' && TIME_HERO)
  const deltaCls = cx(DELTA_BASE, tier === 'standard' && DELTA_STANDARD, tier === 'hero' && DELTA_HERO)
  const topCls   = cx(TOP_BASE, tier === 'hero' && TOP_HERO)

  return (
    <div className={WRAP}>
      <div className={GRID}>
        <div className={headCls}>
          <span>#</span>
          <span>TIME</span>
          <span>Δ</span>
          {tier === 'hero' && <span>TOP</span>}
        </div>
        <div className={ROWS}>
          {visible.map((r) => {
            const delta = (r.timeS != null && bestLap?.timeS != null && r.timeS > 0)
              ? r.timeS - bestLap.timeS
              : null
            const isBest = bestLap && r.lap === bestLap.lap
            const rowCls = cx(ROW_GRID_BASE, tier === 'hero' && ROW_GRID_HERO,
                              ROW, tier === 'hero' && ROW_HERO, isBest && ROW_BEST)
            return (
              <div key={r.lap} className={rowCls}>
                <span className={lapCls}>L{r.lap}</span>
                <span className={timeCls}>{formatLapTime(r.timeS)}</span>
                <span className={deltaCls} data-sign={delta == null ? '' : delta < 0.001 ? 'best' : 'down'}>
                  {delta == null ? '—' : delta < 0.001 ? 'best' : `+${delta.toFixed(3)}`}
                </span>
                {tier === 'hero' && (
                  <span className={topCls}>
                    {r.topSpeedMps ? `${Math.round(mpsToKph(r.topSpeedMps))}` : '—'}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
