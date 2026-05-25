import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react'
import type { ReactNode, MutableRefObject } from 'react'
import type { components } from '@fh-racer/contract/api'
import type { Frame } from '@fh-racer/contract/ws'
import { api } from '@/shared/lib/api'
import { liveClient } from '@/shared/lib/wsClient'
import { useSession } from '@/features/sessions/context/SessionContext'

type SessionFramesResponse = components['schemas']['SessionFramesResponse']
type FrameRow = unknown[]

export interface ReplayValue {
  active: boolean
  loading: boolean
  error: string | null
  loadedSessionId: string | null
  frames: FrameRow[] | null
  duration: number
  t: number
  tRef: MutableRefObject<number>
  playing: boolean
  play: () => void
  pause: () => void
  toggle: () => void
  seek: (newT: number | string) => void
  rowAt: (time: number) => FrameRow | null
}

const ReplayCtx = createContext<ReplayValue | null>(null)

// ReplayContext owns the playback timeline for the loaded session.
//
// When `loadedSessionId` flips from null → an id, this provider fetches
// `/api/sessions/:id/frames` once and exposes a scrub time `t` plus
// play / pause / seek controls. Widgets that want to follow the scrubber
// (e.g. WorldMap) read `tRef.current` inside their rAF loop; the
// scrubber UI reads the throttled state `t` for its label and slider.
//
// While replay is active, the provider also installs a frame override
// on liveClient.getLatestFrame() — every canvas / rAF widget therefore
// reads the synthesised replay frame at the current scrub time instead
// of the live one, with no per-widget plumbing. Fields populated in the
// replay frame come from /api/sessions/:id/frames: speed, throttle,
// brake, position, rpm, gear, currentLapS / lastLapS / bestLapS,
// gripBudget, acceleration (x/y/z), tireTemp (fl/fr/rl/rr).
// Engine.idleRpm / engine.maxRpm aren't projected, so we mirror the
// most-recently-seen live values so the RPM dial/tape scales stay
// correct between live and replay.

const PLAYBACK_HZ = 30
const STATE_UPDATE_HZ = 20  // throttle React state churn while playing
// Phase 3 §1.3 #2: the backend's `SUPPORTED_FIELDS` includes this full
// set, so we request it unconditionally. The 400-fallback retry that
// used to live here is gone — any failure now is a real backend
// regression worth surfacing as an error rather than papering over.
const REPLAY_FIELDS = 'speed,throttle,brake,position,rpm,gear,currentLapS,lastLapS,bestLapS,gripBudget,acceleration,tireTemp'

// Default engine scale used when no live frame has been seen yet.
// FH6 cars span roughly 700–9000 RPM; the dials accept anything as
// long as max > 2000. Matches RpmDial.jsx fallback.
const DEFAULT_IDLE_RPM = 800
const DEFAULT_MAX_RPM  = 8000

export function ReplayProvider({ children }: { children: ReactNode }) {
  const { loadedSessionId } = useSession()

  const [frames, setFrames]   = useState<FrameRow[] | null>(null)
  const [duration, setDuration] = useState(0)
  const [t, setT]             = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  // Refs for the hot path: rAF callers read tRef without forcing a
  // React render. Mirrors the pattern useFrameLoop uses.
  const tRef          = useRef(0)
  const playingRef    = useRef(false)
  const durationRef   = useRef(0)
  const rafRef        = useRef(0)
  const lastTickRef   = useRef(0)
  const lastStateMsRef = useRef(0)

  // Sync refs whenever scalar state changes — keeps hot-path reads cheap.
  useEffect(() => { durationRef.current = duration }, [duration])
  useEffect(() => { playingRef.current = playing }, [playing])

  // Field-order from the server response (e.g. ["speed", "throttle",
  // "brake", "position", "rpm", "gear"]). Used to map row columns onto
  // synthesised frame fields. Server is authoritative — we don't assume
  // the projection order matches our request.
  const fieldsRef = useRef<string[]>(REPLAY_FIELDS.split(','))

  // Mirror frames into a ref so play() can guard without depending on
  // the `frames` state slot (which would re-create the callback).
  const framesRef = useRef<FrameRow[] | null>(null)
  useEffect(() => { framesRef.current = frames }, [frames])

  // Snapshot the most-recently-seen live engine scale so the dials use
  // the correct max/idle RPM during replay. The session-frames endpoint
  // doesn't ship these (they're per-car constants), so we cache them
  // from the live stream.
  const engineScaleRef = useRef({ idleRpm: DEFAULT_IDLE_RPM, maxRpm: DEFAULT_MAX_RPM })
  useEffect(() => {
    const off = liveClient.subscribe('frame', (msg: Frame) => {
      const idle = msg?.engine?.idleRpm
      const max  = msg?.engine?.maxRpm
      if (idle && idle > 0) engineScaleRef.current.idleRpm = idle
      if (max  && max  > 0) engineScaleRef.current.maxRpm  = max
    })
    return off
  }, [])

  // Fetch frames when a session is loaded. Reset on unload.
  useEffect(() => {
    if (!loadedSessionId) {
      setFrames(null)
      setDuration(0)
      setT(0); tRef.current = 0
      setPlaying(false); playingRef.current = false
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)

    const fetchWith = (fields: string) =>
      api.sessionFrames(loadedSessionId, { hz: PLAYBACK_HZ, fields })

    const apply = (resp: SessionFramesResponse, requestedFields: string) => {
      const data = resp?.data ?? []
      fieldsRef.current = Array.isArray(resp?.fields) ? resp.fields : requestedFields.split(',')
      setFrames(data as FrameRow[])
      const last = data.length ? (data[data.length - 1]![0] as number) : 0
      setDuration(last)
      durationRef.current = last
      setT(0); tRef.current = 0
    }

    fetchWith(REPLAY_FIELDS).then((resp) => {
      if (cancelled) return
      apply(resp, REPLAY_FIELDS)
    }).catch((err: unknown) => {
      if (cancelled) return
      console.warn('[replay] sessionFrames failed', err)
      setFrames(null)
      setDuration(0)
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg || 'Replay load failed')
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [loadedSessionId])

  const seek = useCallback((newT: number | string) => {
    const dur = durationRef.current
    const clamped = Math.max(0, Math.min(dur, Number(newT) || 0))
    tRef.current = clamped
    setT(clamped)
  }, [])

  const play = useCallback(() => {
    if (!framesRef.current || framesRef.current.length === 0) return
    // If we're parked at the end, rewind to the start so play actually
    // does something (matches video-player UX).
    if (tRef.current >= durationRef.current - 0.001) {
      tRef.current = 0
      setT(0)
    }
    setPlaying(true)
  }, [])

  const pause = useCallback(() => setPlaying(false), [])

  const toggle = useCallback(() => {
    if (playingRef.current) setPlaying(false)
    else play()
  }, [play])

  // Playback loop. rAF-driven so motion stays smooth; React state for
  // `t` is throttled so widgets / scrubber labels don't re-render every
  // tick.
  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = 0
      return
    }
    lastTickRef.current = performance.now()
    lastStateMsRef.current = lastTickRef.current
    const tick = (now: number) => {
      const dt = (now - lastTickRef.current) / 1000
      lastTickRef.current = now
      const next = tRef.current + dt
      const dur = durationRef.current
      if (next >= dur) {
        // Stop at the end; user can press play again to rewind.
        tRef.current = dur
        setT(dur)
        setPlaying(false)
        playingRef.current = false
        return
      }
      tRef.current = next
      if (now - lastStateMsRef.current >= 1000 / STATE_UPDATE_HZ) {
        lastStateMsRef.current = now
        setT(next)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = 0
    }
  }, [playing])

  // Find the latest row whose timestamp <= time. Frames are pre-sorted
  // by t so binary search is safe.
  const rowAt = useCallback((time: number): FrameRow | null => {
    const arr = framesRef.current
    if (!arr || arr.length === 0) return null
    let lo = 0, hi = arr.length - 1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if ((arr[mid]![0] as number) <= time) lo = mid + 1
      else hi = mid - 1
    }
    return arr[Math.max(0, hi)] ?? null
  }, [])

  // Keep a ref to the loaded session id so buildReplayFrame doesn't need
  // to capture it (and re-create the callback every load).
  const loadedSessionRef = useRef<string | null>(null)
  useEffect(() => { loadedSessionRef.current = loadedSessionId }, [loadedSessionId])

  // Build a frame-shaped object from the row at the current scrub time.
  // Shape matches the live wire-protocol frame so widgets that read
  // `frame.motion.speed_mps`, `frame.engine.rpm`, etc. work unchanged.
  // Fields not in the session projection are zero / defaulted —
  // dependent widgets degrade gracefully (gauges flatline, but don't
  // throw).
  const buildReplayFrame = useCallback((): Frame | null => {
    const arr  = framesRef.current
    if (!arr || arr.length === 0) return null
    const flds = fieldsRef.current
    const time = tRef.current
    // Inline binary search (matches rowAt) — runs every rAF so hot path.
    let lo = 0, hi = arr.length - 1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if ((arr[mid]![0] as number) <= time) lo = mid + 1
      else hi = mid - 1
    }
    const row = arr[Math.max(0, hi)]
    if (!row) return null

    // Row layout: [t, <fields in order>]. Pluck by column index.
    let speed = 0, throttle = 0, brake = 0, rpm = 0, gear = 0
    let pos: [number, number, number] | null = null
    let currentLapS = 0, lastLapS = 0, bestLapS = 0
    let gripBudget = 0
    let accel: [number, number, number] | null = null
    let tireTemp: [number, number, number, number] | null = null
    for (let i = 0; i < flds.length; i++) {
      const col = row[i + 1]
      switch (flds[i]) {
        case 'speed':       speed       = (col as number) ?? 0;    break
        case 'throttle':    throttle    = (col as number) ?? 0;    break
        case 'brake':       brake       = (col as number) ?? 0;    break
        case 'position':    pos         = (col as [number, number, number]) ?? null; break
        case 'rpm':         rpm         = (col as number) ?? 0;    break
        case 'gear':        gear        = (col as number) ?? 0;    break
        case 'currentLapS': currentLapS = (col as number) ?? 0;    break
        case 'lastLapS':    lastLapS    = (col as number) ?? 0;    break
        case 'bestLapS':    bestLapS    = (col as number) ?? 0;    break
        case 'gripBudget':  gripBudget  = (col as number) ?? 0;    break
        case 'acceleration': accel      = (col as [number, number, number]) ?? null; break
        case 'tireTemp':    tireTemp    = (col as [number, number, number, number]) ?? null; break
        default: break
      }
    }

    const { idleRpm, maxRpm } = engineScaleRef.current
    return {
      t: time,
      sessionId: loadedSessionRef.current ?? '',
      carId: '',
      isRaceOn: true,
      race: { lap: 0, position: 0, currentLapS, lastLapS, bestLapS, raceTimeS: time },
      engine: { rpm, idleRpm, maxRpm, power_w: 0, torque_nm: 0, boost_psi: 0, fuel: 0 },
      drivetrain: { gear, clutch: 0, type: 'AWD' },
      motion: {
        speed_mps: speed,
        velocity:     { x: 0, y: 0, z: 0 },
        acceleration: accel
          ? { x: accel[0] ?? 0, y: accel[1] ?? 0, z: accel[2] ?? 0 }
          : { x: 0, y: 0, z: 0 },
        angularVelocity: { x: 0, y: 0, z: 0 },
        orientation: { yaw: 0, pitch: 0, roll: 0 },
        position: pos ? { x: pos[0], y: pos[1], z: pos[2] } : { x: 0, y: 0, z: 0 },
      },
      inputs: { throttle, brake, clutch: 0, handbrake: 0, steer: 0, drivingLine: 0, aiBrakeDelta: 0 },
      wheels: tireTemp ? {
        fl: { tireTemp_normWindow: tireTemp[0] ?? 0, combinedSlip: 0 } as Frame['wheels']['fl'],
        fr: { tireTemp_normWindow: tireTemp[1] ?? 0, combinedSlip: 0 } as Frame['wheels']['fr'],
        rl: { tireTemp_normWindow: tireTemp[2] ?? 0, combinedSlip: 0 } as Frame['wheels']['rl'],
        rr: { tireTemp_normWindow: tireTemp[3] ?? 0, combinedSlip: 0 } as Frame['wheels']['rr'],
      } : ({} as Frame['wheels']),
      world: {} as Frame['world'],
      derived: { gripBudgetUsed: gripBudget } as Frame['derived'],
      modeled: {} as Frame['modeled'],
    }
  }, [])

  // Install / clear the liveClient frame override. While set, every
  // widget that reads liveClient.getLatestFrame() — i.e. anything using
  // useCanvas or useFrameLoop — sees the synthesised replay frame.
  useEffect(() => {
    const hasFrames = !!frames && frames.length > 0
    if (!loadedSessionId || !hasFrames) {
      liveClient.setFrameOverride(null)
      return
    }
    liveClient.setFrameOverride({ frame: buildReplayFrame })
    return () => { liveClient.setFrameOverride(null) }
  }, [loadedSessionId, frames, buildReplayFrame])

  const value = useMemo<ReplayValue>(() => ({
    active: !!loadedSessionId && !!frames && frames.length > 0,
    loading,
    error,
    loadedSessionId,
    frames,
    duration,
    t,
    tRef,
    playing,
    play,
    pause,
    toggle,
    seek,
    rowAt,
  }), [
    loadedSessionId, loading, error, frames, duration, t, playing,
    play, pause, toggle, seek, rowAt,
  ])

  return <ReplayCtx.Provider value={value}>{children}</ReplayCtx.Provider>
}

export function useReplay(): ReplayValue {
  const ctx = useContext(ReplayCtx)
  if (!ctx) throw new Error('useReplay must be used inside <ReplayProvider>')
  return ctx
}
