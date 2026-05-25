import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'
import type { ListSessionsParams, SessionFramesOpts } from '@/shared/lib/api'
import { sessionKeys } from './keys'

type Schemas = components['schemas']
type SessionListItem = Schemas['SessionListItem']
type SessionDetailResponse = Schemas['SessionDetailResponse']
type SessionFramesResponse = Schemas['SessionFramesResponse']

export interface SessionQueryOpts {
  enabled?: boolean
}

export function useListSessionsQuery(
  params: ListSessionsParams = {},
  opts: SessionQueryOpts = {},
): UseQueryResult<SessionListItem[]> {
  return useQuery({
    queryKey: sessionKeys.list(params as Record<string, unknown>),
    queryFn: () => api.listSessions(params),
    enabled: opts.enabled ?? true,
  })
}

export function useCurrentSessionQuery(
  opts: SessionQueryOpts = {},
): UseQueryResult<SessionListItem | null> {
  return useQuery({
    queryKey: sessionKeys.current(),
    queryFn: () => api.currentSession(),
    enabled: opts.enabled ?? true,
  })
}

export interface SessionDetailQueryOpts extends SessionQueryOpts {
  refetchInterval?: number | false
}

export function useSessionDetailQuery(
  sessionId: string | null | undefined,
  opts: SessionDetailQueryOpts = {},
): UseQueryResult<SessionDetailResponse> {
  const enabled = (opts.enabled ?? true) && !!sessionId
  const sid = sessionId ?? ''
  const interval = opts.refetchInterval
  return useQuery({
    queryKey: sessionKeys.detail(sid),
    queryFn: () => api.sessionDetail(sid),
    enabled,
    refetchInterval: enabled ? (interval ?? false) : false,
  })
}

export interface SessionFramesQueryOpts extends SessionQueryOpts {
  // Sticky cache: replay frame buffers don't churn. Match the
  // hand-rolled WorldMap behaviour where a session was fetched once on
  // load and held in memory until the next session swap.
  staleTime?: number
}

export function useSessionFramesQuery(
  sessionId: string | null | undefined,
  frameOpts: SessionFramesOpts,
  opts: SessionFramesQueryOpts = {},
): UseQueryResult<SessionFramesResponse> {
  const enabled = (opts.enabled ?? true) && !!sessionId
  const sid = sessionId ?? ''
  return useQuery({
    queryKey: sessionKeys.frames(sid, frameOpts as Record<string, unknown>),
    queryFn: () => api.sessionFrames(sid, frameOpts),
    enabled,
    staleTime: opts.staleTime ?? Infinity,
  })
}

export function useDeleteSessionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sessionKeys.all })
    },
  })
}
