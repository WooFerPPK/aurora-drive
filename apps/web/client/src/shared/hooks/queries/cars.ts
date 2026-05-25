import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'
import { carKeys, sessionKeys } from './keys'

type Schemas = components['schemas']
type CarListResponse = Schemas['CarListResponse']
type CarSummary = Schemas['CarSummary']

export interface CarQueryOpts {
  enabled?: boolean
}

export function useListCarsQuery(opts: CarQueryOpts = {}): UseQueryResult<CarListResponse> {
  return useQuery({
    queryKey: carKeys.list(),
    queryFn: () => api.listCars(),
    enabled: opts.enabled ?? true,
  })
}

interface RenameCarArgs {
  ordinal: number | string
  displayName: string
}

export function useRenameCarMutation() {
  const queryClient = useQueryClient()
  return useMutation<CarSummary, Error, RenameCarArgs>({
    mutationFn: ({ ordinal, displayName }) => api.renameCar(ordinal, displayName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: carKeys.all })
    },
  })
}

export function useDeleteCarMutation() {
  const queryClient = useQueryClient()
  return useMutation<null, Error, string>({
    mutationFn: (id) => api.deleteCar(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: carKeys.all })
      queryClient.invalidateQueries({ queryKey: sessionKeys.all })
    },
  })
}

export function useDeleteCarSessionsMutation() {
  const queryClient = useQueryClient()
  return useMutation<null, Error, string>({
    mutationFn: (id) => api.deleteCarSessions(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sessionKeys.all })
    },
  })
}

export function useWipeAllDataMutation() {
  const queryClient = useQueryClient()
  return useMutation<null, Error, void>({
    mutationFn: () => api.wipeAllData(),
    onSuccess: () => {
      queryClient.clear()
    },
  })
}
