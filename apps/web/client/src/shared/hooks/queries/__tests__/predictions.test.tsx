import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

// Same pattern as useTelemetry.test.tsx: vi.hoisted gives the mock
// factory access to a stable controllable object.
const handlers = vi.hoisted(() => {
  const byType = new Map<string, Set<(msg: unknown) => void>>()
  return {
    byType,
    subscribe(type: string, fn: (msg: unknown) => void): () => void {
      let set = byType.get(type)
      if (!set) { set = new Set(); byType.set(type, set) }
      set.add(fn)
      return () => { set!.delete(fn) }
    },
    emit(type: string, payload: unknown): void {
      byType.get(type)?.forEach((fn) => fn(payload))
    },
    reset(): void { byType.clear() },
  }
})

vi.mock('@/shared/lib/wsClient', () => ({
  liveClient: { subscribe: handlers.subscribe },
}))

const apiCalls = vi.hoisted(() => ({
  predictLap: vi.fn(),
}))

vi.mock('@/shared/lib/api', () => ({
  api: { predictLap: apiCalls.predictLap },
}))

import { useLapPredictionQuery } from '@/shared/hooks/queries/predictions'

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return { client, Wrapper }
}

describe('useLapPredictionQuery', () => {
  beforeEach(() => {
    handlers.reset()
    apiCalls.predictLap.mockReset()
  })

  it('stays disabled (no fetch) when sessionId is null', () => {
    const { Wrapper } = makeWrapper()
    renderHook(() => useLapPredictionQuery(null, 3), { wrapper: Wrapper })
    expect(apiCalls.predictLap).not.toHaveBeenCalled()
  })

  it('stays disabled when caller passes enabled:false (e.g. in-replay)', () => {
    const { Wrapper } = makeWrapper()
    renderHook(() => useLapPredictionQuery('sess-1', 3, { enabled: false }), { wrapper: Wrapper })
    expect(apiCalls.predictLap).not.toHaveBeenCalled()
  })

  it('fetches when sessionId is provided and forwards the response', async () => {
    apiCalls.predictLap.mockResolvedValueOnce({
      predictions: [{ lap: 1, time_s: 90, upper_s: 91, lower_s: 89, confidence: 0.8 }],
      limiter: null,
    })
    const { Wrapper } = makeWrapper()
    const { result } = renderHook(() => useLapPredictionQuery('sess-1', 3), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(apiCalls.predictLap).toHaveBeenCalledWith(3, 'sess-1')
    expect(result.current.data?.predictions[0]?.lap).toBe(1)
  })

  it('refetches when a lap_completed event fires (live-event invalidation)', async () => {
    apiCalls.predictLap
      .mockResolvedValueOnce({ predictions: [{ lap: 1, time_s: 90, upper_s: 91, lower_s: 89, confidence: 0.5 }], limiter: null })
      .mockResolvedValueOnce({ predictions: [{ lap: 2, time_s: 89, upper_s: 90, lower_s: 88, confidence: 0.9 }], limiter: null })

    const { Wrapper } = makeWrapper()
    const { result } = renderHook(() => useLapPredictionQuery('sess-1', 3), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.data?.predictions[0]?.lap).toBe(1))
    expect(apiCalls.predictLap).toHaveBeenCalledTimes(1)

    act(() => { handlers.emit('event', { kind: 'lap_completed' }) })

    await waitFor(() => expect(apiCalls.predictLap).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.data?.predictions[0]?.lap).toBe(2))
  })

  it('ignores unrelated live events', async () => {
    apiCalls.predictLap.mockResolvedValue({ predictions: [], limiter: null })
    const { Wrapper } = makeWrapper()
    renderHook(() => useLapPredictionQuery('sess-1', 3), { wrapper: Wrapper })

    await waitFor(() => expect(apiCalls.predictLap).toHaveBeenCalledTimes(1))
    act(() => { handlers.emit('event', { kind: 'oversteer' }) })

    // Give React a microtask flush, then assert no extra fetch.
    await Promise.resolve()
    expect(apiCalls.predictLap).toHaveBeenCalledTimes(1)
  })
})
