import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'
import { settingsKeys } from './keys'

type SettingsResponse = components['schemas']['SettingsResponse']

export interface SettingsQueryOpts {
  enabled?: boolean
}

export function useSettingsQuery(
  opts: SettingsQueryOpts = {},
): UseQueryResult<SettingsResponse> {
  return useQuery({
    queryKey: settingsKeys.current(),
    queryFn: () => api.getSettings(),
    enabled: opts.enabled ?? true,
  })
}

export function usePatchSettingsMutation() {
  const queryClient = useQueryClient()
  return useMutation<SettingsResponse, Error, Partial<SettingsResponse>>({
    mutationFn: (partial) => api.patchSettings(partial),
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKeys.current(), data)
    },
  })
}
