import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'
import { coachKeys } from './keys'

type CoachStatus = components['schemas']['CoachStatus']

export interface CoachStatusQueryOpts {
  enabled?: boolean
}

export function useCoachStatusQuery(
  opts: CoachStatusQueryOpts = {},
): UseQueryResult<CoachStatus> {
  return useQuery({
    queryKey: coachKeys.status(),
    queryFn: () => api.coachStatus(),
    enabled: opts.enabled ?? true,
  })
}
