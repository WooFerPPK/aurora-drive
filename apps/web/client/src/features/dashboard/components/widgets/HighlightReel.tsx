// client/src/components/widgets/HighlightReel.tsx
import type { CSSProperties } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useSession } from '@/features/sessions/context/SessionContext'
import { cx } from '@/shared/lib/format'
import { useSessionDetailQuery } from '@/shared/hooks/queries/sessions'
import { REFETCH } from '@/shared/hooks/queries/intervals'

type SessionEvent = components['schemas']['SessionEventEntry']
type Tier = 'compact' | 'standard' | 'hero'

interface KindMeta { lbl: string; tone: string }
const KIND_META: Record<string, KindMeta> = {
  lap_completed:    { lbl: 'LAP DONE',     tone: '--mint'    },
  sector_completed: { lbl: 'SECTOR',       tone: '--lilac'   },
  oversteer:        { lbl: 'OVERSTEER',    tone: '--pink'    },
  off_track:        { lbl: 'OFF TRACK',    tone: '--pink'    },
  missed_upshift:   { lbl: 'MISSED SHIFT', tone: '--butter'  },
  smashable_hit:    { lbl: 'IMPACT',       tone: '--pink'    },
}

const WRAP = 'w-full h-full flex flex-col px-2.5 py-1.5 gap-1'

const LIST = 'list-none p-0 m-0 flex flex-col gap-1 overflow-hidden flex-1'

const ROW_BASE = 'flex gap-0 overflow-hidden bg-[rgba(255,255,255,0.03)] rounded-lg min-h-[28px]'
const ROW_COMPACT = 'flex-1 items-center'

const STRIPE =
  'w-[3px] flex-shrink-0 bg-[color:var(--tone,var(--mint))] ' +
  '[box-shadow:0_0_6px_var(--tone,var(--mint))] rounded-l-lg'

const BODY = 'flex-1 px-2 py-1 flex flex-col justify-center gap-px min-w-0'

const LINE_1 = 'flex items-baseline justify-between gap-1.5'

const LBL_BASE =
  'font-display font-semibold text-[12px] [letter-spacing:0.14em] text-[color:var(--tone,var(--mint))]'
const LBL_HERO = 'text-[16px]'

const TIME_BASE = 'font-mono font-normal text-[8px] text-ink-faint [font-variant-numeric:tabular-nums]'
const TIME_STANDARD = 'text-[14px]'
const TIME_HERO = 'text-[16px]'

const DETAIL = 'font-mono font-normal text-[9px] text-cream whitespace-nowrap overflow-hidden text-ellipsis'

const SKELETON_ROWS = 'flex flex-col gap-1 flex-1 pt-1'
const SKELETON_ROW =
  'h-6 rounded-md ' +
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_50%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite]'

const EMPTY_CAPTION = 'font-ui font-normal text-[9px] text-ink-faint text-center mt-1'

function formatTime(s: number | null | undefined): string {
  if (s == null || s < 0) return '—'
  const total = Math.floor(s)
  const m = Math.floor(total / 60)
  const sec = total - m * 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

interface Summary extends KindMeta { detail: string }

function summarise(ev: SessionEvent): Summary {
  const meta: KindMeta = KIND_META[ev.kind] || { lbl: ev.kind.toUpperCase(), tone: '--mint' }
  const payload = (ev.payload || {}) as Record<string, unknown>
  const lapRaw = payload['lap'] ?? payload['lapNumber']
  const cornerRaw = payload['corner']
  const lap = typeof lapRaw === 'number' ? lapRaw : null
  const corner = typeof cornerRaw === 'string' ? cornerRaw : null
  const parts: string[] = []
  if (lap != null) parts.push(`L${lap}`)
  if (corner) parts.push(corner)
  if (ev.kind === 'lap_completed' && typeof payload['lastLapS'] === 'number') {
    const ll = payload['lastLapS'] as number
    const m = Math.floor(ll / 60); const r = ll - m * 60
    parts.push(`${m}:${r.toFixed(3).padStart(6, '0')}`)
  }
  return { ...meta, detail: parts.join(' · ') }
}

function renderEmpty(tier: Tier, caption: string) {
  const rowCount = tier === 'compact' ? 1 : tier === 'standard' ? 3 : 5
  const rows = []
  for (let i = 0; i < rowCount; i++) {
    rows.push(<div key={i} className={SKELETON_ROW} style={{ animationDelay: `${i * 0.12}s` }} />)
  }
  return (
    <div className={WRAP}>
      <div className={SKELETON_ROWS}>{rows}</div>
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

export interface HighlightReelProps {
  w: number
  h: number
}

export default function HighlightReel({ w, h }: HighlightReelProps) {
  const tier: Tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'
  const limit = tier === 'compact' ? 1 : tier === 'standard' ? 4 : 10

  const { currentSession, loadedSessionId } = useSession()
  const sessionId = loadedSessionId ?? currentSession?.id ?? null

  const { data, error: err } = useSessionDetailQuery(sessionId, { refetchInterval: REFETCH.highlightReel })
  const events: SessionEvent[] | null = data ? (data.events ?? []) : null

  if (!sessionId)             return renderEmpty(tier, 'No session loaded')
  if (err)                    return renderEmpty(tier, '—')
  if (events == null)         return renderEmpty(tier, 'Loading events…')
  if (events.length === 0)    return renderEmpty(tier, 'No events yet')

  const ordered = [...events].sort((a, b) => (b.atS ?? 0) - (a.atS ?? 0)).slice(0, limit)

  const lblCls = cx(LBL_BASE, tier === 'hero' && LBL_HERO)
  const timeCls = cx(TIME_BASE, tier === 'standard' && TIME_STANDARD, tier === 'hero' && TIME_HERO)

  return (
    <div className={WRAP}>
      <ul className={LIST}>
        {ordered.map((ev, i) => {
          const s = summarise(ev)
          const style = { '--tone': `var(${s.tone})` } as CSSProperties
          return (
            <li key={`${ev.atS}-${i}`} className={cx(ROW_BASE, tier === 'compact' && ROW_COMPACT)} style={style}>
              <div className={STRIPE} />
              <div className={BODY}>
                <div className={LINE_1}>
                  <span className={lblCls}>{s.lbl}</span>
                  {tier !== 'compact' && <span className={timeCls}>{formatTime(ev.atS)}</span>}
                </div>
                {tier !== 'compact' && s.detail && (
                  <div className={DETAIL}>{s.detail}</div>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
