// client/src/components/widgets/ShiftReport.tsx
import type { components } from '@fh-racer/contract/api'
import { useShiftReportQuery } from '@/shared/hooks/queries/predictions'
import { cx } from '@/shared/lib/format'

type ShiftReportResp = components['schemas']['ShiftReportResponse']
type PairAgg = components['schemas']['ShiftReportPairAgg']
type PairEntry = [string, PairAgg]

const EMPTY_REPORT: ShiftReportResp = {
  assistInterventionPct: 0,
  avgDeltaRpm: 0,
  byGearPair: {},
  cleanShifts: 0,
  estTotalCostS: 0,
  modelVersion: '',
  sessionId: 'live',
  totalShifts: 0,
}

const WRAP = 'relative w-full h-full flex flex-col px-3 py-2 gap-1.5 box-border'

const HEADLINE = 'flex items-baseline gap-1'

const CLEAN_BASE =
  'font-display font-bold text-[24px] text-cream [font-variant-numeric:tabular-nums] ' +
  '[text-shadow:0_0_12px_color-mix(in_srgb,var(--mint)_35%,transparent)]'
const CLEAN_HERO = 'text-[32px]'

const OF = 'font-display font-normal text-[14px] text-ink-faint'
const TOTAL = 'font-display font-semibold text-[18px] text-ink-faint [font-variant-numeric:tabular-nums]'
const HEADLINE_LABEL = 'font-mono font-normal text-[9px] text-ink-faint [letter-spacing:0.16em] uppercase ml-1.5'

const COST_ROW = 'flex items-baseline gap-1.5'
const COST_VAL = 'font-mono font-bold text-[14px] text-cream [font-variant-numeric:tabular-nums]'
const COST_LABEL = 'font-mono font-normal text-[9px] text-ink-faint [letter-spacing:0.14em] uppercase'
const ASSIST_PCT =
  'font-mono font-normal text-[10px] [letter-spacing:0.08em] ml-1 ' +
  'text-[color:color-mix(in_srgb,var(--pink)_85%,var(--cream))]'

const BARS = 'flex flex-col gap-[3px] mt-1'
const BARS_EMPTY = 'font-mono font-normal text-[10px] text-ink-faint [letter-spacing:0.08em] mt-1'

const BARS_GROUP_LABEL_BASE =
  'font-mono font-semibold text-[9px] [letter-spacing:0.14em] uppercase mt-[3px]'
const BARS_GROUP_LABEL_UP = 'text-mint'
const BARS_GROUP_LABEL_DOWN = 'text-butter'

const BAR_ROW = 'grid grid-cols-[36px_1fr_44px] gap-1.5 items-center'
const BAR_LABEL = 'font-mono font-normal text-[10px] text-ink-faint [font-variant-numeric:tabular-nums]'

const BAR_TRACK =
  'relative h-1.5 rounded-[3px] overflow-hidden ' +
  '[background:color-mix(in_srgb,var(--ink-faint)_8%,transparent)]'
const BAR_FILL_BASE = 'absolute top-0 left-0 bottom-0 rounded-[3px]'
const BAR_FILL_UP   = 'bg-[color:color-mix(in_srgb,var(--mint)_70%,transparent)]'
const BAR_FILL_DOWN = 'bg-[color:color-mix(in_srgb,var(--butter)_70%,transparent)]'

const BAR_VAL = 'font-mono font-semibold text-[10px] text-cream [font-variant-numeric:tabular-nums] text-right'

const CALLOUT =
  'mt-1.5 pt-1.5 flex flex-col gap-[3px] ' +
  'border-t border-[color:color-mix(in_srgb,var(--ink-faint)_18%,transparent)]'

const CALLOUT_ROW =
  'grid grid-cols-[40px_36px_1fr] gap-1.5 items-baseline ' +
  'font-mono font-normal text-[10px] [font-variant-numeric:tabular-nums]'

const CALLOUT_LABEL_BASE = 'font-semibold [letter-spacing:0.08em] uppercase'
const CALLOUT_LABEL_BEST  = 'text-mint'
const CALLOUT_LABEL_WORST = 'text-pink'

const CALLOUT_PAIR = 'text-ink-faint'
const CALLOUT_VAL  = 'text-cream text-right'

const EMPTY_CAPTION = 'font-ui font-normal text-[9px] text-ink-faint text-center mt-1'

function formatSecondsCost(s: number | null | undefined): string {
  if (s == null) return '0.00s'
  const v = Math.abs(s)
  if (v >= 10) return `${s.toFixed(0)}s`
  return `${s.toFixed(2)}s`
}

function sortByFromGear(a: PairEntry, b: PairEntry): number {
  const ax = a[0].split('->')[0]
  const bx = b[0].split('->')[0]
  return Number(ax) - Number(bx)
}

interface PerPairBarsProps {
  byGearPair: Record<string, PairAgg>
  max: number
}

function PerPairBars({ byGearPair, max }: PerPairBarsProps) {
  const all = Object.entries(byGearPair) as PairEntry[]
  if (!all.length) {
    return <div className={BARS_EMPTY}>No clean shifts yet</div>
  }
  const ups: PairEntry[] = []
  const downs: PairEntry[] = []
  for (const e of all) {
    const dir = e[1]?.direction === 'down' ? 'down' : 'up'
    if (dir === 'down') downs.push(e)
    else ups.push(e)
  }
  ups.sort(sortByFromGear)
  downs.sort(sortByFromGear)

  const renderRow = (pair: string, agg: PairAgg, group: 'up' | 'down') => {
    const dr = agg.avgDeltaRpm
    const pct = Math.max(0, Math.min(1, Math.abs(dr) / Math.max(1, max)))
    return (
      <div key={`${group}-${pair}`} className={BAR_ROW}>
        <span className={BAR_LABEL}>{pair}</span>
        <div className={BAR_TRACK}>
          <div
            className={cx(BAR_FILL_BASE, group === 'up' ? BAR_FILL_UP : BAR_FILL_DOWN)}
            style={{ width: `${pct * 100}%` }}
          />
        </div>
        <span className={BAR_VAL}>
          {dr >= 0 ? '+' : ''}{Math.round(dr)}
        </span>
      </div>
    )
  }

  return (
    <div className={BARS}>
      {ups.length > 0 && (
        <>
          <div className={cx(BARS_GROUP_LABEL_BASE, BARS_GROUP_LABEL_UP)}>Upshifts</div>
          {ups.map(([pair, agg]) => renderRow(pair, agg, 'up'))}
        </>
      )}
      {downs.length > 0 && (
        <>
          <div className={cx(BARS_GROUP_LABEL_BASE, BARS_GROUP_LABEL_DOWN)}>Downshifts</div>
          {downs.map(([pair, agg]) => renderRow(pair, agg, 'down'))}
        </>
      )}
    </div>
  )
}

function pickBestWorst(byGearPair: Record<string, PairAgg>): { best: PairEntry | null; worst: PairEntry | null } {
  const entries = (Object.entries(byGearPair) as PairEntry[]).filter(([, agg]) => agg != null)
  if (entries.length === 0) return { best: null, worst: null }
  const score = (agg: PairAgg): number => (
    agg.avgEstCostS != null ? agg.avgEstCostS : Math.abs(agg.avgDeltaRpm ?? 0) / 1000
  )
  let best = entries[0]!
  let worst = entries[0]!
  for (const e of entries) {
    if (score(e[1]) < score(best[1])) best = e
    if (score(e[1]) > score(worst[1])) worst = e
  }
  return { best, worst }
}

export interface ShiftReportProps {
  w: number
  h: number
}

export default function ShiftReport({ w, h }: ShiftReportProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const { data: queryData, error } = useShiftReportQuery('live')
  const data: ShiftReportResp | null = queryData ?? (error ? EMPTY_REPORT : null)

  const cleanCls = cx(CLEAN_BASE, tier === 'hero' && CLEAN_HERO)

  if (data == null) {
    return (
      <div className={WRAP}>
        <div className={HEADLINE}>
          <span className={cleanCls}>—</span>
          <span className={OF}>/</span>
          <span className={TOTAL}>—</span>
        </div>
        <div className={EMPTY_CAPTION}>Awaiting live session…</div>
      </div>
    )
  }

  const total = data.totalShifts ?? 0
  const clean = data.cleanShifts ?? 0
  const cost  = data.estTotalCostS ?? 0
  const assistPct = data.assistInterventionPct ?? null
  const byPair = data.byGearPair || {}
  let maxDelta = 0
  for (const k in byPair) {
    const d = Math.abs(byPair[k]!.avgDeltaRpm)
    if (d > maxDelta) maxDelta = d
  }
  const { best, worst } = pickBestWorst(byPair)

  const formatCostSecs = (s: number | null | undefined): string => (
    s == null ? '—' : `${s >= 0 ? '+' : ''}${s.toFixed(2)}s`
  )

  return (
    <div className={WRAP}>
      <div className={HEADLINE}>
        <span className={cleanCls}>{clean}</span>
        <span className={OF}>/</span>
        <span className={TOTAL}>{total}</span>
        <span className={HEADLINE_LABEL}>clean</span>
      </div>
      <div className={COST_ROW}>
        <span className={COST_VAL}>{formatSecondsCost(cost)}</span>
        <span className={COST_LABEL}>est cost</span>
        {assistPct != null && (
          <span className={ASSIST_PCT} title="Share of recent frames with traction-control intervention">
            ({Math.round(assistPct * 100)}% TCS)
          </span>
        )}
      </div>
      {tier !== 'compact' && (
        <PerPairBars byGearPair={byPair} max={maxDelta} />
      )}
      {tier === 'hero' && (best || worst) && (
        <div className={CALLOUT}>
          {best && (
            <div className={CALLOUT_ROW}>
              <span className={cx(CALLOUT_LABEL_BASE, CALLOUT_LABEL_BEST)}>Best</span>
              <span className={CALLOUT_PAIR}>{best[0]}</span>
              <span className={CALLOUT_VAL}>
                {best[1].avgEstCostS != null
                  ? formatCostSecs(best[1].avgEstCostS)
                  : `${best[1].avgDeltaRpm >= 0 ? '+' : ''}${Math.round(best[1].avgDeltaRpm)} RPM`}
              </span>
            </div>
          )}
          {worst && worst[0] !== (best && best[0]) && (
            <div className={CALLOUT_ROW}>
              <span className={cx(CALLOUT_LABEL_BASE, CALLOUT_LABEL_WORST)}>Worst</span>
              <span className={CALLOUT_PAIR}>{worst[0]}</span>
              <span className={CALLOUT_VAL}>
                {worst[1].avgEstCostS != null
                  ? formatCostSecs(worst[1].avgEstCostS)
                  : `${worst[1].avgDeltaRpm >= 0 ? '+' : ''}${Math.round(worst[1].avgDeltaRpm)} RPM`}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
