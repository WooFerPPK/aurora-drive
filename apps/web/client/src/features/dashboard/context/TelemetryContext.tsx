import { createContext, useContext, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useTelemetry, EMPTY_FRAME } from '@/features/dashboard/hooks/useTelemetry'
import type { UseTelemetryResult } from '@/features/dashboard/hooks/useTelemetry'
import { useStreamState } from '@/features/dashboard/hooks/useStreamState'
import type { StreamStateView } from '@/features/dashboard/hooks/useStreamState'

// Single context bundling latest frame + stream state. Pages can pick
// the slice they need; we deliberately keep both behind one provider so
// the WebSocket lifecycle is owned in one place.

export interface TelemetryContextValue extends UseTelemetryResult {
  stream: StreamStateView
}

const DEFAULT_STREAM: StreamStateView = {
  state: 'waiting', reason: null, at: 0, lastFrameAt: null, wsConnected: false,
}

const TelemetryCtx = createContext<TelemetryContextValue>({
  frame: EMPTY_FRAME, hasFrame: false, fresh: false,
  stream: DEFAULT_STREAM,
})

export function TelemetryProvider({ children, value }: { children: ReactNode; value?: TelemetryContextValue }) {
  const live = useTelemetry()
  const stream = useStreamState()
  const ctx = useMemo<TelemetryContextValue>(
    () => value ?? { ...live, stream },
    [value, live.frame, live.hasFrame, live.fresh, stream]
  )
  return <TelemetryCtx.Provider value={ctx}>{children}</TelemetryCtx.Provider>
}

export function useTelemetryData(): TelemetryContextValue {
  return useContext(TelemetryCtx)
}
