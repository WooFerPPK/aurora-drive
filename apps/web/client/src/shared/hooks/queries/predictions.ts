import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'
import { REFETCH } from './intervals'
import { predictionKeys } from './keys'
import { useInvalidateOnLiveEvent } from './useInvalidateOnLiveEvent'

type Schemas = components['schemas']
type LapPredictionResponse = Schemas['LapPredictionResponse']
type TireFailurePredictionResponse = Schemas['TireFailurePredictionResponse']
type FinishPredictionResponse = Schemas['FinishPredictionResponse']
type CrashRiskPredictionResponse = Schemas['CrashRiskPredictionResponse']
type ShiftReportResponse = Schemas['ShiftReportResponse']

// Each predict hook takes `enabled` so the widget controls when polling
// pauses (currently: while in replay, or before a session is active).
// The live WS events listed in `useInvalidateOnLiveEvent` mirror the
// per-widget subscriptions Phase 6 removed.

export interface PredictionQueryOpts {
  enabled?: boolean
}

export function useLapPredictionQuery(
  sessionId: string | null | undefined,
  n: number,
  opts: PredictionQueryOpts = {},
): UseQueryResult<LapPredictionResponse> {
  const enabled = (opts.enabled ?? true) && !!sessionId
  const sid = sessionId ?? ''
  const key = predictionKeys.lap(sid, n)
  useInvalidateOnLiveEvent(['lap_completed'], key, enabled)
  return useQuery({
    queryKey: key,
    queryFn: () => api.predictLap(n, sid),
    enabled,
    refetchInterval: enabled ? REFETCH.lapPrediction : false,
  })
}

export function useTireFailureQuery(
  sessionId: string | null | undefined,
  opts: PredictionQueryOpts = {},
): UseQueryResult<TireFailurePredictionResponse> {
  const enabled = (opts.enabled ?? true) && !!sessionId
  const sid = sessionId ?? ''
  const key = predictionKeys.tireFailure(sid)
  useInvalidateOnLiveEvent(['lap_completed'], key, enabled)
  return useQuery({
    queryKey: key,
    queryFn: () => api.predictTireFailure(sid),
    enabled,
    refetchInterval: enabled ? REFETCH.tireFailure : false,
  })
}

export function useFinishPredictionQuery(
  opts: PredictionQueryOpts = {},
): UseQueryResult<FinishPredictionResponse> {
  const enabled = opts.enabled ?? true
  const key = predictionKeys.finish()
  useInvalidateOnLiveEvent(['lap_completed'], key, enabled)
  return useQuery({
    queryKey: key,
    queryFn: () => api.predictFinish(),
    enabled,
    refetchInterval: enabled ? REFETCH.finishPrediction : false,
  })
}

export function useCrashRiskQuery(
  windowS: number = 30,
  opts: PredictionQueryOpts = {},
): UseQueryResult<CrashRiskPredictionResponse> {
  const enabled = opts.enabled ?? true
  const key = predictionKeys.crashRisk(windowS)
  useInvalidateOnLiveEvent(['oversteer', 'off_track'], key, enabled)
  return useQuery({
    queryKey: key,
    queryFn: () => api.predictCrash(windowS),
    enabled,
    refetchInterval: enabled ? REFETCH.crashRisk : false,
  })
}

export function useShiftReportQuery(
  sessionId: string = 'live',
  opts: PredictionQueryOpts = {},
): UseQueryResult<ShiftReportResponse> {
  const enabled = opts.enabled ?? true
  const key = predictionKeys.shiftReport(sessionId)
  return useQuery({
    queryKey: key,
    queryFn: () => api.predictShiftReport(sessionId),
    enabled,
    refetchInterval: enabled ? REFETCH.shiftReport : false,
  })
}

export function useResetShiftMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: unknown) => api.resetShift(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: predictionKeys.all })
    },
  })
}
