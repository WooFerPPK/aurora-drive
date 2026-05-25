import { useEffect, useState } from 'react'
import type { State as StreamStateName, StateMessage } from '@fh-racer/contract/ws'
import { liveClient } from '@/shared/lib/wsClient'

// Server publishes stream-state transitions on /ws/live:
//   {type:"state", state:"driving"}
//   {type:"state", state:"stream-paused", reason:"menu"}
//   {type:"state", state:"stream-resumed"}
//   {type:"state", state:"stream-lost"}
//
// We keep the canonical state string here. UI consumers can derive
// labels (DRIVING / PAUSED / LOST / CONNECTED / WAITING) from it.

export type ClientStreamState = StreamStateName | 'waiting'

export interface StreamStateView {
  state: ClientStreamState
  reason: string | null
  at: number
  lastFrameAt: number | null
  wsConnected: boolean
}

const INITIAL: StreamStateView = {
  state: 'waiting',
  reason: null,
  at: 0,
  lastFrameAt: null,
  wsConnected: false,
}

export function useStreamState(): StreamStateView {
  const [s, setS] = useState<StreamStateView>(INITIAL)

  useEffect(() => {
    const offState = liveClient.subscribe('state', (msg: StateMessage) => {
      setS({
        state: msg.state ?? 'waiting',
        reason: msg.reason ?? null,
        at: msg.at ?? 0,
        lastFrameAt: msg.lastFrameAt ?? null,
        wsConnected: true,
      })
    })
    const offConn = liveClient.onConnectionChange((connected: boolean) => {
      setS((cur) => ({
        ...cur,
        wsConnected: connected,
        // When the socket itself drops, fall back to waiting until the
        // backend re-publishes a state transition.
        state: connected ? cur.state : 'waiting',
      }))
    })
    return () => { offState(); offConn() }
  }, [])

  return s
}
