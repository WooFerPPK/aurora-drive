// client/src/components/widgets/CoachFeed.tsx
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { CalloutMessage } from '@fh-racer/contract/ws'
import { getCoachClient } from '@/shared/lib/wsClient'
import { MetricLabel } from '@/shared/components/widgetPrimitives'
import { cx } from '@/shared/lib/format'

const MAX_BUFFER = 50

type Priority = CalloutMessage['priority']
const TONE_VAR: Record<Priority, string> = {
  warn: '--pink',
  tip:  '--butter',
  info: '--baby-blue',
}

interface BufferedCallout extends CalloutMessage {
  _id: string
}

const WRAP = 'w-full h-full flex flex-col overflow-hidden'

const WRAP_EMPTY =
  'items-center justify-center gap-3.5 text-ink-faint'

const PULSE_DOT =
  'relative w-2.5 h-2.5 rounded-full bg-mint animate-[coach-pulse_2.4s_ease-in-out_infinite] ' +
  'before:content-[""] before:absolute before:inset-0 before:rounded-full ' +
  'before:border before:border-mint before:opacity-0 before:animate-[coach-ring-out_2.4s_ease-out_infinite] ' +
  'after:content-[""] after:absolute after:inset-0 after:rounded-full ' +
  'after:border after:border-mint after:opacity-0 after:animate-[coach-ring-out_2.4s_ease-out_infinite] ' +
  'after:[animation-delay:1.2s]'

const EMPTY_CAPTION = 'font-ui font-normal text-[10px] text-ink-faint [letter-spacing:0.05em]'

const TOOLBAR =
  'flex flex-row justify-between items-center px-3 py-2 flex-shrink-0 ' +
  'border-b border-[rgba(255,193,220,0.10)]'

const CLEAR_BTN_BASE =
  'font-display font-medium text-[12px] [letter-spacing:0.18em] uppercase ' +
  'text-ink-faint bg-[rgba(255,255,255,0.04)] ' +
  'border border-[rgba(253,233,255,0.12)] rounded-full ' +
  'px-2.5 py-px cursor-pointer ' +
  '[transition:color_120ms,background_120ms,border-color_120ms] ' +
  'hover:text-cream hover:bg-[rgba(255,255,255,0.08)] hover:border-[rgba(253,233,255,0.25)] ' +
  'active:text-pink active:border-pink'
const CLEAR_BTN_STANDARD = 'text-[14px]'
const CLEAR_BTN_HERO     = 'text-[16px]'

// .coach-list kept as marker for the vendor-pseudo scrollbar skin in index.css.
const LIST = 'coach-list list-none m-0 px-2 py-1.5 flex-1 overflow-y-auto flex flex-col gap-1.5'

const CARD_BASE = 'flex gap-0 overflow-hidden bg-[rgba(255,255,255,0.04)] rounded-[10px] flex-shrink-0'
const CARD_COMPACT = 'items-center'

const STRIPE =
  'w-[3px] flex-shrink-0 bg-[color:var(--tone,var(--mint))] ' +
  '[box-shadow:0_0_8px_var(--tone,var(--mint))] rounded-l-[10px]'

const BODY_WRAP = 'flex-1 px-2 py-1.5 flex flex-col justify-center gap-px min-w-0'

const PRIORITY_BASE =
  'font-display font-medium text-[12px] [letter-spacing:0.2em] ' +
  'text-[color:var(--tone,var(--mint))] opacity-80'
const PRIORITY_STANDARD = 'text-[14px]'
const PRIORITY_HERO     = 'text-[16px]'

const TEXT_BASE =
  'font-ui font-medium text-[14px] text-cream whitespace-nowrap overflow-hidden text-ellipsis'
const TEXT_COMPACT = 'text-[14px]'
const TEXT_HERO    = 'text-[16px] whitespace-normal'

const META_BASE = 'font-mono font-normal text-[12px] text-ink-faint'
const META_HERO = 'text-[16px]'

export interface CoachFeedProps {
  w: number
  h: number
}

export default function CoachFeed({ w, h }: CoachFeedProps) {
  const tier  = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'
  const seqRef = useRef(0)
  const [items, setItems] = useState<BufferedCallout[]>([])

  useEffect(() => {
    let alive  = true
    const coach = getCoachClient()
    const off   = coach.subscribe('callout', (msg) => {
      if (!msg) return
      const id = msg.id ?? `${msg.atS ?? Date.now()}-${seqRef.current++}`
      if (alive) {
        setItems(prev => [{ ...msg, _id: String(id) }, ...prev].slice(0, MAX_BUFFER))
      }
    })
    return () => { alive = false; off?.() }
  }, [])

  const clear = (): void => setItems([])

  if (items.length === 0) {
    return (
      <div className={cx(WRAP, WRAP_EMPTY)}>
        <div className={PULSE_DOT} />
        <div className={EMPTY_CAPTION}>Listening for callouts…</div>
      </div>
    )
  }

  const clearCls = cx(CLEAR_BTN_BASE, tier === 'standard' && CLEAR_BTN_STANDARD, tier === 'hero' && CLEAR_BTN_HERO)
  const priorityCls = cx(PRIORITY_BASE, tier === 'standard' && PRIORITY_STANDARD, tier === 'hero' && PRIORITY_HERO)
  const textCls = cx(TEXT_BASE, tier === 'compact' && TEXT_COMPACT, tier === 'hero' && TEXT_HERO)
  const metaCls = cx(META_BASE, tier === 'hero' && META_HERO)
  const cardCls = cx(CARD_BASE, tier === 'compact' && CARD_COMPACT)

  return (
    <div className={WRAP}>
      <div className={TOOLBAR}>
        <MetricLabel text={`${items.length} CALLOUT${items.length === 1 ? '' : 'S'}`} tier={tier} />
        <button className={clearCls} onClick={clear} title="Clear feed">CLEAR</button>
      </div>
      <ul className={LIST}>
        {items.map(c => {
          const toneVar = TONE_VAR[c.priority] ?? '--mint'
          const meta    = [c.lap > 0 && `L${c.lap}`, c.corner].filter(Boolean).join(' · ')
          const style = { '--tone': `var(${toneVar})` } as CSSProperties
          return (
            <li key={c._id} className={cardCls} style={style}>
              <div className={STRIPE} />
              <div className={BODY_WRAP}>
                {tier !== 'compact' && <div className={priorityCls}>{c.priority?.toUpperCase()}</div>}
                <div className={textCls}>{c.text}</div>
                {tier === 'hero' && meta && <div className={metaCls}>{meta}</div>}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
