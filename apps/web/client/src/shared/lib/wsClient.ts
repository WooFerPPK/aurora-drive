// Singleton WebSocket subscriber, modelled on the legacy wsClient but
// rewritten for the new backend wire protocol (api-contract §2).
//
// The backend speaks raw envelope messages on /ws/live:
//   { type: "hello",            server, capabilities }
//   { type: "frame",            ... }
//   { type: "frames",           batch: [frame, frame, ...] }   // batched mode
//   { type: "state",            state, at, lastFrameAt, reason }
//   { type: "event",            kind, at, ... }
//   { type: "heartbeat",        at }
//   { type: "error",            code, ... }
//   { type: "udp_bind_failed",  message }                       // one-shot after hello
//
// Subscribers register against a `type` (the same string as `msg.type`).
// `frames` (batched) is unrolled here and republished as individual
// `frame` messages so subscribers only ever handle one shape.
//
// Event-kind coverage (api-contract §2, Phase 3 §1.3 #4 audit). Live
// events the backend emits and what currently consumes each:
//
//   session_started   → SessionContext (current session refresh)
//   session_ended     → SessionContext
//   lap_completed     → SessionContext (lap-counter bump) + HighlightReel (via REST events)
//   lap_started       → UNCONSUMED on the live channel. Highlight reel surfaces it
//                       via REST history. Live-time hook (e.g. lap-start chime) is
//                       a future widget — leave the server-side emission in place.
//   sector_completed  → HighlightReel (via REST events). No live-channel consumer.
//   shift             → UNCONSUMED. Future widget hook (shift-timing trace).
//   missed_upshift    → ShiftCoach (drives the warning pulse)
//   oversteer         → CrashRisk (recompute risk) + HighlightReel
//   off_track         → CrashRisk + HighlightReel
//   smashable_hit     → HighlightReel (via REST events). No live-channel consumer.
//   engine_curve_change → EngineCurveChangeToast
//
// The four UNCONSUMED-on-live kinds (lap_started, sector_completed,
// shift, smashable_hit) intentionally have no live subscriber today.
// They keep flowing on the wire so future widgets can hook in without
// a backend round-trip. Updating this list when adding/removing a
// subscriber is part of the change.

import type {
  Frame, FrameBatch, StateMessage, EventMessage, Heartbeat, Hello,
  LiveErrorMessage, UdpBindFailedMessage, CalloutMessage, CoachHello,
} from '@fh-racer/contract/ws'
import { WS_LIVE_PATH, WS_RECONNECT_DELAY_MS, DEFAULT_FRAME_RATE } from './constants'

// Per-channel message-type maps. The subscribe API uses these to narrow
// each handler's payload by the type string passed at the call site.
export type LiveMessageByType = {
  hello: Hello
  frame: Frame
  frames: FrameBatch
  state: StateMessage
  event: EventMessage
  heartbeat: Heartbeat
  error: LiveErrorMessage
  udp_bind_failed: UdpBindFailedMessage
}

export type CoachMessageByType = {
  hello: CoachHello
  callout: CalloutMessage
}

export interface FrameOverride {
  frame: () => Frame | null
  ageMs?: () => number
}

export type ConnectionListener = (connected: boolean) => void

export interface WsClient<TMap extends Record<string, unknown>> {
  subscribe: <K extends keyof TMap & string>(type: K, fn: (msg: TMap[K]) => void) => () => void
  onConnectionChange: (fn: ConnectionListener) => () => void
  send: (msg: unknown) => void
  close: () => void
  __emit: <K extends keyof TMap & string>(type: K, payload: TMap[K]) => void
  isConnected: () => boolean
  isReady: () => boolean
  getLatestFrame: () => Frame | null
  getFrameAgeMs: () => number
  getFrameCount: () => number
  setFrameOverride: (override: FrameOverride | null) => void
}

function makeWsUrl(path: string, query: Record<string, string> | undefined): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const qs = query ? `?${new URLSearchParams(query).toString()}` : ''
  return `${proto}//${window.location.host}${path}${qs}`
}

function createClient<TMap extends Record<string, unknown>>(
  path: string,
  queryFactory?: () => Record<string, string>,
): WsClient<TMap> {
  const listeners = new Map<string, Set<(msg: unknown) => void>>()
  const connectionListeners = new Set<ConnectionListener>()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let connectedState = false
  let helloSeen = false
  let manualClose = false

  // Per-channel latest-frame cache. Updated synchronously when a
  // `frame` message arrives so widgets can poll it from a rAF loop
  // without going through React state. `frameMonoTs` is the
  // performance.now() at receive time, used to detect staleness.
  let latestFrame: Frame | null = null
  let frameMonoTs = 0
  let frameCounter = 0

  // Frame override. While replay is active, ReplayContext installs a
  // synthesiser via setFrameOverride(); getLatestFrame() then returns
  // the synthesised frame at the current scrub time instead of the
  // live one, so every canvas / rAF widget follows the scrubber with
  // no per-widget plumbing. Override is { frame: () => synthFrame,
  // ageMs?: () => number }; setting it to null restores live mode.
  let frameOverride: FrameOverride | null = null

  function notify(type: string, msg: unknown): void {
    const set = listeners.get(type)
    if (!set) return
    for (const fn of set) {
      try { fn(msg) } catch (err) { console.warn(`[ws ${path}] listener for ${type} threw`, err) }
    }
  }

  function recordFrame(f: Frame): void {
    latestFrame  = f
    frameMonoTs  = performance.now()
    frameCounter++
  }

  function setConnected(v: boolean): void {
    if (connectedState === v) return
    connectedState = v
    for (const fn of connectionListeners) {
      try { fn(v) } catch { /* ignore */ }
    }
  }

  function connect(): void {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    manualClose = false
    const url = makeWsUrl(path, queryFactory ? queryFactory() : undefined)
    try {
      ws = new WebSocket(url)
    } catch (err) {
      console.warn(`[ws ${path}] open failed`, err)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      helloSeen = false
      setConnected(true)
    }

    ws.onmessage = (e: MessageEvent) => {
      let msg: { type?: string; batch?: unknown } & Record<string, unknown>
      try { msg = JSON.parse(typeof e.data === 'string' ? e.data : '') } catch { return }
      if (!msg || typeof msg !== 'object' || !msg.type) return
      if (msg.type === 'hello') helloSeen = true

      // Unbox batched frames so subscribers only see one shape.
      if (msg.type === 'frames' && Array.isArray(msg.batch)) {
        for (const f of msg.batch as Frame[]) {
          recordFrame(f)
          notify('frame', f)
        }
        return
      }
      if (msg.type === 'frame') recordFrame(msg as unknown as Frame)
      notify(msg.type, msg)
    }

    ws.onclose = () => {
      setConnected(false)
      if (!manualClose) scheduleReconnect()
    }

    ws.onerror = () => {
      try { ws?.close() } catch { /* ignore */ }
    }
  }

  function scheduleReconnect(): void {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, WS_RECONNECT_DELAY_MS)
  }

  function subscribe<K extends keyof TMap & string>(type: K, fn: (msg: TMap[K]) => void): () => void {
    if (!listeners.has(type)) listeners.set(type, new Set())
    listeners.get(type)!.add(fn as (msg: unknown) => void)
    if (!ws) connect()
    return () => {
      const set = listeners.get(type)
      if (set) set.delete(fn as (msg: unknown) => void)
    }
  }

  function onConnectionChange(fn: ConnectionListener): () => void {
    connectionListeners.add(fn)
    fn(connectedState)
    if (!ws) connect()
    return () => { connectionListeners.delete(fn) }
  }

  function send(msg: unknown): void {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify(msg)) } catch (err) { console.warn(`[ws ${path}] send failed`, err) }
    }
  }

  function close(): void {
    manualClose = true
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (ws) { try { ws.close() } catch { /* ignore */ } }
  }

  // Test / sandbox hook: synthesise a fake inbound message so widgets
  // that subscribe via .subscribe() see it as if it came off the wire.
  // Used by the dev sandbox to mock /ws/coach callouts for CoachFeed.
  function __emit<K extends keyof TMap & string>(type: K, payload: TMap[K]): void {
    const set = listeners.get(type)
    if (!set) return
    for (const fn of set) {
      try { fn(payload) } catch (err) { console.warn(`[ws ${path}] __emit handler threw`, err) }
    }
  }

  return {
    subscribe,
    onConnectionChange,
    send,
    close,
    __emit,
    isConnected: () => connectedState,
    isReady:     () => connectedState && helloSeen,
    // Hot-path accessors for canvas / rAF widgets. Reading these
    // doesn't subscribe — call them inside a frame loop, not in
    // React render.
    getLatestFrame: (): Frame | null => {
      if (frameOverride && frameOverride.frame) {
        try {
          const f = frameOverride.frame()
          if (f) return f
        } catch (err) { console.warn(`[ws ${path}] frame override threw`, err) }
      }
      return latestFrame
    },
    getFrameAgeMs: (): number => {
      if (frameOverride) {
        if (frameOverride.ageMs) {
          try { return frameOverride.ageMs() } catch { /* fall through */ }
        }
        return 0   // replay frame is synthesised on-demand — always "fresh"
      }
      return frameMonoTs ? performance.now() - frameMonoTs : Infinity
    },
    getFrameCount: (): number => frameCounter,
    // Replay hook: install / clear a frame override.
    setFrameOverride: (override: FrameOverride | null): void => { frameOverride = override || null },
  }
}

// Two singletons: one for telemetry (/ws/live), one for coach (/ws/coach).
// The coach channel stays dormant until something calls subscribe() on
// it — we don't want every page eagerly opening a coach socket the user
// might not be looking at.

let frameRate: number = DEFAULT_FRAME_RATE

export const liveClient: WsClient<LiveMessageByType> = createClient<LiveMessageByType>(WS_LIVE_PATH, () => ({
  sessionId: 'auto',
  car: 'current',
  frameRate: String(frameRate),
}))

export function setLiveFrameRate(hz: number): void {
  if (![10, 30, 60].includes(hz)) return
  frameRate = hz
  // The backend also accepts a mid-stream rate change message so we
  // don't have to bounce the socket.
  liveClient.send({ type: 'rate', hz })
}

// Coach client is lazily constructed on first subscribe — many pages
// never need it.
let _coachClient: WsClient<CoachMessageByType> | null = null
export function getCoachClient(): WsClient<CoachMessageByType> {
  if (_coachClient) return _coachClient
  _coachClient = createClient<CoachMessageByType>('/ws/coach')
  return _coachClient
}

// Eagerly open the live connection so the hello frame lands fast.
liveClient.subscribe('hello', () => {})
