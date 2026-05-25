import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { QueryKey } from '@tanstack/react-query'
import { liveClient } from '@/shared/lib/wsClient'

// Bridges the live WS event stream to TanStack Query cache. Subscribe
// for the lifetime of the calling hook; when a matching event arrives,
// invalidate the given query key so the next render triggers a refetch.
//
// Replaces the hand-rolled `liveClient.subscribe('event', evt => evt.kind === X && refresh())`
// pattern that lived inside each prediction widget's useEffect. Passing
// `enabled: false` (e.g. while in replay) detaches the subscription
// without removing the cached data.
export function useInvalidateOnLiveEvent(
  eventKinds: readonly string[],
  queryKey: QueryKey,
  enabled: boolean = true,
): void {
  const queryClient = useQueryClient()
  const kinds = eventKinds.join('|')
  const keySig = JSON.stringify(queryKey)

  useEffect(() => {
    if (!enabled) return
    const off = liveClient.subscribe('event', (evt) => {
      const kind = (evt as { kind?: string } | null)?.kind
      if (kind && eventKinds.includes(kind)) {
        queryClient.invalidateQueries({ queryKey })
      }
    })
    return () => { off?.() }
    // `kinds` + `keySig` cover the array/object deps; queryClient is
    // stable across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, kinds, keySig, queryClient])
}
