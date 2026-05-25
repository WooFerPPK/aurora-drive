import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Replace the singleton WS client with a controllable subscribe map so
// the hook can be driven synchronously by the test. `vi.hoisted` is
// required because `vi.mock` is hoisted above local declarations and
// the factory must not capture uninitialised state.
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

import { useTelemetry, EMPTY_FRAME } from '@/features/dashboard/hooks/useTelemetry'

describe('useTelemetry', () => {
  beforeEach(() => { handlers.reset() })

  it('starts with the default empty frame and is neither hasFrame nor fresh', () => {
    const { result } = renderHook(() => useTelemetry())

    expect(result.current.hasFrame).toBe(false)
    expect(result.current.fresh).toBe(false)
    expect(result.current.frame).toBe(EMPTY_FRAME)
    expect(result.current.frame.engine.rpm).toBe(0)
    expect(result.current.frame.derived.weightFront).toBe(0.5)
  })

  it('marks the frame fresh and forwards the payload after a frame arrives', () => {
    const { result } = renderHook(() => useTelemetry())
    expect(handlers.byType.get('frame')?.size).toBe(1)

    const next = {
      ...EMPTY_FRAME,
      t: 1,
      engine: { ...EMPTY_FRAME.engine, rpm: 4200 },
    }
    act(() => { handlers.emit('frame', next) })

    expect(result.current.hasFrame).toBe(true)
    expect(result.current.fresh).toBe(true)
    expect(result.current.frame.engine.rpm).toBe(4200)
  })
})
