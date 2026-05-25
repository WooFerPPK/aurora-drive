import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from '@/shared/lib/format'

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode
  sub?: ReactNode
  children?: ReactNode
}

const CARD = 'relative bg-card-gradient border border-card-border rounded-[14px] shadow-card-glow backdrop-blur-[14px] backdrop-saturate-[1.4] overflow-hidden min-w-0 min-h-0 shrink-0'
const HEAD = 'flex items-center justify-between gap-2 px-[14px] pt-2 pb-1'
const TITLE = 'flex items-center gap-2 whitespace-nowrap font-display text-[10px] font-medium uppercase tracking-[0.2em] text-bubblegum [text-shadow:0_0_8px_rgba(255,193,220,0.4)]'
const DOT = 'w-[7px] h-[7px] rounded-full bg-pink shadow-[0_0_8px_var(--pink)] animate-[pulse_1.6s_ease-in-out_infinite]'
const SUB = 'font-mono text-[9px] tracking-[0.14em] text-ink-faint whitespace-nowrap'
const BODY = 'pt-[10px] px-[14px] pb-[14px]'

export function Card({ className, title, sub, children, ...rest }: CardProps) {
  return (
    <div className={cx(CARD, className)} {...rest}>
      {(title || sub) && (
        <div className={HEAD}>
          {title && (
            <div className={TITLE}>
              <span className={DOT} />
              {title}
            </div>
          )}
          {sub && <div className={SUB}>{sub}</div>}
        </div>
      )}
      <div className={BODY}>{children}</div>
    </div>
  )
}
