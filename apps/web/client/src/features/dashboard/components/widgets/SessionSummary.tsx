// client/src/components/widgets/SessionSummary.tsx
import type { ReactNode } from 'react'
import { useSession } from '@/features/sessions/context/SessionContext'
import { cx, mpsToKph, formatLapTime } from '@/shared/lib/format'
import { useSessionDetailQuery } from '@/shared/hooks/queries/sessions'
import { REFETCH } from '@/shared/hooks/queries/intervals'

type Tier = 'compact' | 'standard' | 'hero'

const TYPE_LABEL: Record<string, string> = {
  race:           'Race',
  time_trial:     'Time trial',
  drift:          'Drift',
  free_roam:      'Free roam',
  cross_country:  'Cross country',
}

function formatDuration(s: number | null | undefined): string {
  if (s == null || s < 0) return '—'
  const total = Math.floor(s)
  const m = Math.floor(total / 60)
  const sec = total - m * 60
  if (m >= 60) {
    const h = Math.floor(m / 60)
    return `${h}h ${m - h * 60}m`
  }
  return `${m}:${String(sec).padStart(2, '0')}`
}

function formatDistanceKm(m: number | null | undefined): string {
  if (m == null || m < 0) return '—'
  return `${(m / 1000).toFixed(1)} km`
}

const WRAP = 'w-full h-full flex flex-col px-3 py-2 gap-1.5'

const GRID_BASE = 'grid flex-1 gap-1.5 grid-cols-2'
const GRID_HERO = 'grid-cols-3'

const TILE =
  'flex flex-col justify-center px-2 py-1.5 bg-[rgba(255,255,255,0.03)] ' +
  'rounded-lg border-l-2 border-lilac min-w-0'

const LBL_BASE =
  'font-display font-normal text-[12px] [letter-spacing:0.18em] uppercase text-ink-faint'
const LBL_STANDARD = 'text-[14px]'
const LBL_HERO = 'text-[16px]'

const VAL_BASE =
  'font-mono font-semibold text-[13px] text-cream whitespace-nowrap overflow-hidden text-ellipsis ' +
  '[font-variant-numeric:tabular-nums]'
const VAL_STANDARD = 'text-[14px]'
const VAL_HERO = 'text-[16px]'

const SKELETON_TILE =
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_50%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite] rounded-lg'

const EMPTY_CAPTION = 'font-ui font-normal text-[9px] text-ink-faint text-center mt-0.5'

function renderEmpty(tier: Tier, caption: string) {
  const tileCount = tier === 'compact' ? 2 : tier === 'standard' ? 4 : 6
  const tiles = []
  for (let i = 0; i < tileCount; i++) {
    tiles.push(
      <div key={i} className={SKELETON_TILE} style={{ animationDelay: `${i * 0.12}s` }} />,
    )
  }
  return (
    <div className={WRAP}>
      <div className={cx(GRID_BASE, tier === 'hero' && GRID_HERO)}>{tiles}</div>
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

export interface SessionSummaryProps {
  w: number
  h: number
}

export default function SessionSummary({ w, h }: SessionSummaryProps) {
  const tier: Tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'
  const { currentSession, loadedSessionId } = useSession()
  const sessionId = loadedSessionId ?? currentSession?.id ?? null

  const { data, error: err } = useSessionDetailQuery(sessionId, { refetchInterval: REFETCH.sessionSummary })

  if (!sessionId) return renderEmpty(tier, 'No session loaded')
  if (err)        return renderEmpty(tier, '—')
  if (!data)      return renderEmpty(tier, 'Loading…')

  const stats: Array<{ lbl: string; val: ReactNode }> = []
  stats.push({ lbl: 'TYPE',     val: TYPE_LABEL[data.type] ?? data.type ?? '—' })
  stats.push({ lbl: 'DURATION', val: formatDuration(data.durationS) })
  if (tier !== 'compact') {
    stats.push({ lbl: 'LAPS', val: data.lapCount ?? 0 })
    stats.push({ lbl: 'BEST', val: formatLapTime(data.bestLapS) })
  }
  if (tier === 'hero') {
    stats.push({ lbl: 'TOP SPEED',
      val: data.topSpeedMps ? `${Math.round(mpsToKph(data.topSpeedMps))} km/h` : '—' })
    stats.push({ lbl: 'DISTANCE', val: formatDistanceKm(data.distanceM) })
  }

  const lblCls = cx(LBL_BASE, tier === 'standard' && LBL_STANDARD, tier === 'hero' && LBL_HERO)
  const valCls = cx(VAL_BASE, tier === 'standard' && VAL_STANDARD, tier === 'hero' && VAL_HERO)

  return (
    <div className={WRAP}>
      <div className={cx(GRID_BASE, tier === 'hero' && GRID_HERO)}>
        {stats.map((s) => (
          <div className={TILE} key={s.lbl}>
            <div className={lblCls}>{s.lbl}</div>
            <div className={valCls}>{s.val}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
