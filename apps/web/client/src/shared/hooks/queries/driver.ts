import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'
import { REFETCH } from './intervals'
import { driverKeys } from './keys'

type DriverProfileResponse = components['schemas']['DriverProfileResponse']

export interface DriverProfileQueryOpts {
  enabled?: boolean
}

export function useDriverProfileQuery(
  opts: DriverProfileQueryOpts = {},
): UseQueryResult<DriverProfileResponse> {
  const enabled = opts.enabled ?? true
  return useQuery({
    queryKey: driverKeys.profile(),
    queryFn: () => api.driverProfile(),
    enabled,
    refetchInterval: enabled ? REFETCH.driverProfile : false,
  })
}
