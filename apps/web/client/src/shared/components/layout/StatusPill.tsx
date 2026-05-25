import { useTelemetryData } from '@/features/dashboard/context/TelemetryContext'

interface LabelArgs {
  wsConnected: boolean
  state: string | null | undefined
  fresh: boolean
  hasFrame: boolean
}

function labelFor({ wsConnected, state, fresh, hasFrame }: LabelArgs): { text: string; color: string } {
  if (!wsConnected) return { text: 'WAITING',    color: 'var(--ink-faint)' }
  if (state === 'stream-lost')   return { text: 'STREAM LOST', color: 'var(--danger)' }
  if (state === 'stream-paused') return { text: 'PAUSED',      color: 'var(--amber)' }
  if (fresh)                     return { text: 'DRIVING',     color: 'var(--mint)' }
  if (hasFrame)                  return { text: 'IDLE',        color: 'var(--baby-blue)' }
  return { text: 'CONNECTED', color: 'var(--lilac)' }
}

export default function StatusPill() {
  const { stream, fresh, hasFrame } = useTelemetryData()
  const { text, color } = labelFor({
    wsConnected: stream.wsConnected,
    state: stream.state,
    fresh,
    hasFrame,
  })
  return (
    <div
      className="flex items-center gap-[6px] px-[9px] py-[3px] rounded-full bg-[rgba(154,247,195,0.07)] border font-mono text-[9px] tracking-[0.18em] whitespace-nowrap"
      style={{
        color,
        borderColor: `color-mix(in srgb, ${color} 33%, transparent)`,
      }}
    >
      <span
        className="w-[6px] h-[6px] rounded-full animate-[pulse_1.4s_ease-in-out_infinite] shrink-0"
        style={{ background: color, boxShadow: `0 0 8px ${color}` }}
      />
      {text}
      {stream.reason && <span className="opacity-70"> · {stream.reason}</span>}
    </div>
  )
}
