// client/src/components/widgets/FinishPredict.tsx
import { useEffect, useRef } from 'react'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useReplay  } from '@/features/dashboard/context/ReplayContext'
import { ConfettiBurst } from '@/shared/components/widgetPrimitives'
import type { ConfettiBurstHandle } from '@/shared/components/widgetPrimitives/ConfettiBurst'
import { useFinishPredictionQuery } from '@/shared/hooks/queries/predictions'
import { cx } from '@/shared/lib/format'

type Tier = 'compact' | 'standard' | 'hero'

const WRAP =
  'relative w-full h-full flex flex-col items-center justify-center gap-1 ' +
  'pt-3 px-2 pb-2 overflow-hidden [container-type:inline-size] ' +
  'before:content-[""] before:absolute before:inset-0 before:rounded-[inherit] before:pointer-events-none ' +
  'before:[background:radial-gradient(ellipse_at_50%_50%,color-mix(in_srgb,var(--mint)_12%,transparent),transparent_60%)]'

const WRAP_EMPTY = 'justify-center gap-3'

const POS =
  'relative z-[1] font-display font-bold text-cream [font-variant-numeric:tabular-nums] ' +
  'max-w-full [font-size:clamp(32px,22cqi,72px)] ' +
  '[text-shadow:0_0_24px_color-mix(in_srgb,var(--mint)_50%,transparent)]'

const CONTEXT =
  'relative z-[1] font-mono font-normal text-[9px] text-ink-faint'

const SKELETON_POS =
  'w-1/2 h-8 rounded-lg ' +
  '[background:linear-gradient(90deg,rgba(168,243,208,0.04)_0%,rgba(202,166,255,0.12)_50%,rgba(168,243,208,0.04)_100%)] ' +
  '[background-size:250%_100%] animate-[shimmer_2.2s_linear_infinite]'

const EMPTY_CAPTION =
  'font-ui font-normal text-[12px] text-ink-faint'

function renderEmpty(_tier: Tier, caption: string) {
  return (
    <div className={cx(WRAP, WRAP_EMPTY)}>
      <div className={SKELETON_POS} />
      <div className={EMPTY_CAPTION}>{caption}</div>
    </div>
  )
}

function ordinal(n: number | null | undefined): string {
  if (n == null) return '—'
  const v = Math.abs(n) % 100
  const last = v % 10
  if (v >= 11 && v <= 13) return n + 'th'
  if (last === 1) return n + 'st'
  if (last === 2) return n + 'nd'
  if (last === 3) return n + 'rd'
  return n + 'th'
}

export interface FinishPredictProps {
  w: number
  h: number
}

export default function FinishPredict({ w, h }: FinishPredictProps) {
  const { active: inReplay } = useReplay()
  const tier: Tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const { currentSession } = useSession()
  const sessionId = currentSession?.id ?? null

  const enabled = !inReplay && !!sessionId
  const { data, error } = useFinishPredictionQuery({ enabled })

  const confettiRef = useRef<ConfettiBurstHandle>(null)
  const lastPosRef  = useRef<number | null>(null)
  const pos = data?.value != null ? Math.round(data.value) : null

  useEffect(() => {
    if (pos == null) return
    if (lastPosRef.current != null && pos < lastPosRef.current) {
      confettiRef.current?.fire()
    }
    lastPosRef.current = pos
  }, [pos])

  if (inReplay)           return renderEmpty(tier, 'Hidden during replay')
  if (!sessionId)         return renderEmpty(tier, 'No active session')
  if (error)              return renderEmpty(tier, '—')
  if (!data)              return renderEmpty(tier, 'Predicting…')
  if (data.value == null) return renderEmpty(tier, 'Need race data')

  const conf = data.confidence

  return (
    <div className={WRAP}>
      <ConfettiBurst ref={confettiRef} colour="mint" />
      <div className={POS}>{ordinal(pos)}</div>
      {tier === 'hero' && (
        <div className={CONTEXT}>confidence {Math.round(conf * 100)}%</div>
      )}
    </div>
  )
}
