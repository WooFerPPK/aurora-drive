// Backend serves WS at /ws/live and /ws/coach. In dev Vite proxies these
// to FH6_BACKEND; in prod nginx proxies them on the same origin. Using
// relative paths means the same client code works in both.
export const WS_LIVE_PATH = '/ws/live'
export const WS_COACH_PATH = '/ws/coach'

// Default frame rate the live channel opens with. The backend allows
// 10/30/60.
//
// NOTE: the backend's 60 Hz mode is currently broken — at hz=60 it
// accepts the WS connection but never emits frames (the downsampler
// drops all decisions). Stay on 30 Hz until that's fixed backend-side.
// Widgets draw at rAF rate regardless (60 fps display), interpolating
// between samples — so 30 Hz over the wire still produces smooth
// visuals.
export const DEFAULT_FRAME_RATE = 30

// Backoff window for reconnects.
export const WS_RECONNECT_DELAY_MS = 2000

// How long after the last frame the client considers the stream stale
// even without a server-side `stream-paused` notice. The backend will
// usually beat us to it (250ms / 3× expected frame interval), but a
// belt-and-suspenders check keeps the UI honest if a server tick is
// missed.
export const TELEMETRY_STALE_MS = 1500

// Pages the backend recognises for /api/layouts/:pageId. The shell
// derives its built-in tab set from this so a new built-in page only
// needs to be added in one place.
export const SUPPORTED_PAGES = [
  'live',
  'sessions',
  'coach',
  'predictions',
  'driver',
  'track',
  'customize',
  'settings',
] as const

export type SupportedPage = (typeof SUPPORTED_PAGES)[number]

// Map of FH6 car class enum (0..7 inclusive) to label per official FH6 dev docs.
export const CLASS_NAMES: Record<number, string> = {
  0: 'D', 1: 'C', 2: 'B', 3: 'A', 4: 'S', 5: 'R', 6: 'P', 7: 'X',
}

export const CORNERS = ['fl', 'fr', 'rl', 'rr'] as const
export type Corner = (typeof CORNERS)[number]
