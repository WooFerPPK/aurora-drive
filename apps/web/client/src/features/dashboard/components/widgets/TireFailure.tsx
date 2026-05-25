// client/src/components/widgets/TireFailure.tsx
import { useSession } from '@/features/sessions/context/SessionContext'
import { useReplay  } from '@/features/dashboard/context/ReplayContext'
import { useTireFailureQuery } from '@/shared/hooks/queries/predictions'
import { cx } from '@/shared/lib/format'

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'

const CORNERS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']
const CORNER_LABELS: Record<CornerKey, string> = { fl: 'FL', fr: 'FR', rl: 'RL', rr: 'RR' }

type Tier = 'compact' | 'standard' | 'hero'

const WRAP = 'relative w-full h-full flex flex-col px-2.5 py-1.5 gap-1'
const WRAP_COMPACT = 'items-center justify-center'
const WRAP_EMPTY = 'justify-start pt-2'

const COMPACT_CORNER =
  'font-display font-bold text-cream [font-size:clamp(28px,14cqi,56px)] ' +
  '[text-shadow:0_0_18px_color-mix(in_srgb,var(--pink)_50%,transparent)]'

const COMPACT_LAP = 'font-mono font-semibold text-[11px] text-pink [letter-spacing:0.1em]'

const COMPACT_HEALTHY =
  'font-display font-bold text-[22px] text-mint [letter-spacing:0.18em] ' +
  '[text-shadow:0_0_14px_color-mix(in_srgb,var(--mint)_45%,transparent)]'

const ROW_BASE =
  'grid grid-cols-[28px_1fr_44px] items-center gap-2 px-1.5 py-1.5 rounded-md [transition:background_200ms]'
const ROW_HERO = 'grid-cols-[28px_1fr_44px_40px]'
const ROW_LIMITING = 'bg-[color:color-mix(in_srgb,var(--pink)_12%,transparent)]'

const LBL_BASE = 'font-display font-bold text-[12px] [letter-spacing:0.12em] text-cream'
const LBL_STANDARD = 'text-[14px]'
const LBL_HERO = 'text-[16px]'

const BAR_WRAP = 'h-2 rounded bg-[rgba(255,193,220,0.08)] overflow-hidden'
const BAR_FILL =
  'h-full ' +
  '[background:linear-gradient(90deg,var(--mint)_0%,var(--butter)_50%,var(--pink)_100%)] ' +
  '[box-shadow:0_0_6px_color-mix(in_srgb,var(--pink)_35%,transparent)]'

const LAP_BASE =
  'font-mono font-semibold text-[11px] text-cream text-right [font-variant-numeric:tabular-nums]'
const LAP_STANDARD = 'text-[13px]'
const LAP_HERO = 'text-[15px]'

const CONF_BASE = 'font-mono font-normal text-[10px] text-ink-faint text-right [font-variant-numeric:tabular-nums]'
const CONF_HERO = 'text-[12px]'

const SKELETON_ROWS = 'flex flex-col gap-1 pt-1'
const SKELETON_ROW =
  'h-5 ' +
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_50%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite] rounded-md'

const EMPTY_CAPTION = 'font-ui font-normal text-[12px] text-ink-faint text-center mt-1'

function renderEmpty(tier: Tier, caption: string) {
  const rowCount = tier === 'compact' ? 1 : 4
  const rows = []
  for (let i = 0; i < rowCount; i++) {
    rows.push(<div key={i} className={SKELETON_ROW} style={{ animationDelay: `${i * 0.12}s` }} />)
  }
  return (
    <div className={cx(WRAP, WRAP_EMPTY)}>
      <div className={SKELETON_ROWS}>{rows}</div>
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

export interface TireFailureProps {
  w: number
  h: number
}

export default function TireFailure({ w, h }: TireFailureProps) {
  const { active: inReplay } = useReplay()
  const tier: Tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const { currentSession } = useSession()
  const sessionId = currentSession?.id ?? null

  const { data, error } = useTireFailureQuery(sessionId, { enabled: !inReplay })

  if (inReplay)        return renderEmpty(tier, 'Hidden during replay')
  if (!sessionId)      return renderEmpty(tier, 'No active session')
  if (error)           return renderEmpty(tier, '—')
  if (!data)           return renderEmpty(tier, 'Analysing tires…')
  if (!data.perCorner) return renderEmpty(tier, 'Need data')

  if (tier === 'compact') {
    const lim = data.limitingCorner as CornerKey | null | undefined
    if (!lim) {
      return (
        <div className={cx(WRAP, WRAP_COMPACT)}>
          <div className={COMPACT_HEALTHY}>HEALTHY</div>
        </div>
      )
    }
    const pc = data.perCorner[lim]
    return (
      <div className={cx(WRAP, WRAP_COMPACT)}>
        <div className={COMPACT_CORNER}>{CORNER_LABELS[lim]}</div>
        <div className={COMPACT_LAP}>
          {pc?.failureAtLap != null ? `FAILS @ L${pc.failureAtLap}` : `${Math.round((pc?.wear ?? 0) * 100)}% WORN`}
        </div>
      </div>
    )
  }

  const lblCls = cx(LBL_BASE, tier === 'standard' && LBL_STANDARD, tier === 'hero' && LBL_HERO)
  const lapCls = cx(LAP_BASE, tier === 'standard' && LAP_STANDARD, tier === 'hero' && LAP_HERO)
  const confCls = cx(CONF_BASE, tier === 'hero' && CONF_HERO)

  return (
    <div className={WRAP}>
      {CORNERS.map((k) => {
        const pc = data.perCorner[k]
        const wear = Math.max(0, Math.min(1, pc?.wear ?? 0))
        const isLimiting = data.limitingCorner === k
        return (
          <div key={k} className={cx(ROW_BASE, tier === 'hero' && ROW_HERO, isLimiting && ROW_LIMITING)}>
            <span className={lblCls}>{CORNER_LABELS[k]}</span>
            <div className={BAR_WRAP}>
              <div className={BAR_FILL} style={{ width: `${wear * 100}%` }} />
            </div>
            <span className={lapCls}>
              {pc?.failureAtLap != null ? `L${pc.failureAtLap}` : '—'}
            </span>
            {tier === 'hero' && (
              <span className={confCls}>{Math.round((pc?.confidence ?? 0) * 100)}%</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
