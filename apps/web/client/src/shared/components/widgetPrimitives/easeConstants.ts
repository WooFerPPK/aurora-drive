// client/src/lib/widgetPrimitives/easeConstants.ts
// Shared ease constants for every widget. Do not introduce per-widget tuning.
// If you find yourself wanting a different value, change it here for everyone.

export const EASE_VALUE = 7   // tracking ramps for displayed values
export const EASE_STALE = 3   // fade in/out when the data goes stale
export const EASE_PEAK  = 6   // peak-pulse decay
