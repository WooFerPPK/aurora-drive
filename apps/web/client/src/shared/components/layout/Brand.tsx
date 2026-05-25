// Aurora Drive brand mark — the spinning conic-gradient orb with the
// counter-spinning heart. Shared between the AppHeader (orb only) and
// the Sidebar (orb + AURORA DRIVE shimmer wordmark).
//
// The wordmark hides on narrow viewports (≤ 980 px) per the original
// `.brand span { display: none }` rule.

import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from '@/shared/lib/format'

export interface BrandProps extends HTMLAttributes<HTMLDivElement> {
  /** Wordmark to show next to the orb. Omit for orb-only. */
  text?: ReactNode
}

export default function Brand({ text, className, ...rest }: BrandProps) {
  return (
    <div
      className={cx(
        'flex items-center gap-[7px] font-display font-semibold tracking-[0.14em] text-[11px] text-cream uppercase shrink-0',
        className,
      )}
      {...rest}
    >
      <div
        className="relative w-[22px] h-[22px] rounded-full shrink-0 bg-[radial-gradient(circle_at_30%_30%,#fff7f0,transparent_50%),conic-gradient(from_220deg,#ffc1dc,#ffe082,#caa6ff,#ff5ea7,#ffc1dc)] shadow-[0_0_10px_rgba(255,193,220,0.7),0_0_22px_rgba(202,166,255,0.4),inset_0_0_6px_rgba(255,255,255,0.6)] animate-[brand-spin_14s_linear_infinite] after:content-['♡'] after:absolute after:inset-0 after:flex after:items-center after:justify-center after:text-[11px] after:text-white after:[text-shadow:0_0_8px_rgba(255,94,167,0.9)] after:animate-[brand-spin_14s_linear_infinite_reverse]"
      />
      {text && (
        <span className="max-[980px]:hidden bg-[linear-gradient(90deg,#ffafd1_0%,#ff5ea7_25%,#ffe082_50%,#caa6ff_75%,#ffafd1_100%)] bg-[length:200%_100%] bg-clip-text text-transparent animate-[shimmer_5s_linear_infinite]">{text}</span>
      )}
    </div>
  )
}
