// client/src/lib/widgetPrimitives/MetricLabel.tsx
//
// <MetricLabel> — small uppercase caption with the brand .dot.
// One render path for every widget's secondary caption. Honours §3 floors:
//   compact ≥ 12px, standard ≥ 14px, hero ≥ 16px.

import type { TickTier } from '@/shared/lib/canvasUtils'

export interface MetricLabelProps {
  text: string
  colour?: string
  tier?: TickTier
  className?: string
}

export default function MetricLabel({ text, colour, tier = 'standard', className = '' }: MetricLabelProps) {
  const size = tier === 'hero' ? 16 : tier === 'standard' ? 14 : 12
  return (
    <span
      className={`metric-label ${className}`}
      style={{ fontSize: `${size}px`, color: colour ?? undefined }}
    >
      <span className="dot" />
      {text}
    </span>
  )
}
