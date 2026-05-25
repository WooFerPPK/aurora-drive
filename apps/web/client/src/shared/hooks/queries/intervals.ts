// Centralised refetch intervals for TanStack Query hooks. Numbers
// migrated from the per-widget setInterval calls Phase 6 replaced —
// changing one of these values changes the cadence everywhere that
// hook is consumed. Times are milliseconds.
//
// Predictions (LapPredict, TireFailure, FinishPredict, CrashRisk) also
// invalidate on relevant WS events; the interval is the upper bound
// for the case where no event fires (e.g. clean driving, no lap
// completed). ShiftReport intentionally polls slower than the
// prediction widgets — shift recommendations are stable across many
// laps and the report endpoint does meaningful work.
export const REFETCH = {
  // Predictions (event-driven plus polling fallback).
  lapPrediction:   5_000,
  tireFailure:     5_000,
  finishPrediction: 5_000,
  crashRisk:       5_000,
  shiftReport:     15_000,

  // Session-derived widgets.
  lapTable:        8_000,
  sessionSummary:  10_000,
  highlightReel:   10_000,

  // Driver profile widgets (slow-changing — aggregated over many laps).
  driverProfile:   60_000,
} as const

export type RefetchKey = keyof typeof REFETCH
