import { QueryClient } from '@tanstack/react-query'

// Module-level singleton. Local-only dashboard, no SSR — one client per
// browser session is fine. Defaults below mirror the cadence of the
// hand-rolled poll loops Phase 6 is replacing: explicit refetch
// intervals live per-hook (see `hooks/queries/intervals.ts`), and
// `retry: 1` matches the previous behaviour of "log and try again on
// the next tick" rather than React Query's default exponential backoff.
//
// `gcTime` is bumped from 5 min to 30 min so unmounting a widget tab
// and remounting doesn't re-fetch from cold; the dashboard pattern is
// "user toggles between a few tabs constantly".
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      gcTime: 30 * 60 * 1000,
    },
  },
})
