import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react'
import type { ReactNode } from 'react'
import type { components } from '@fh-racer/contract/api'
import type { EventMessage, Frame } from '@fh-racer/contract/ws'
import { api } from '@/shared/lib/api'
import type { ListSessionsParams } from '@/shared/lib/api'
import { liveClient } from '@/shared/lib/wsClient'

type CarSummary = components['schemas']['CarSummary']
type SessionListItem = components['schemas']['SessionListItem']
type SessionDetailResponse = components['schemas']['SessionDetailResponse']

export interface SessionValue {
  cars: CarSummary[]
  carsLoading: boolean
  refreshCars: () => Promise<void>
  currentSession: SessionListItem | null
  refreshCurrent: () => Promise<void>
  sessionsList: SessionListItem[]
  sessionsLoading: boolean
  refreshSessionsList: (params?: ListSessionsParams) => Promise<void>
  loadedSessionId: string | null
  loadSession: (sessionId: string | null) => Promise<SessionDetailResponse | null>
  clearLoadedSession: () => void
  getLoadedSession: () => SessionDetailResponse | null
  deleteSession: (sessionId: string) => Promise<void>
  deleteCar: (carId: string) => Promise<void>
  deleteCarSessions: (carId: string) => Promise<void>
  renameCar: (ordinal: number | string, displayName: string) => Promise<CarSummary>
  wipeAll: () => Promise<void>
  selectedCarId: string | null
  setSelectedCarId: (carId: string | null) => void
  liveCarId: string | null
  activeCarId: string | null
  activeCar: CarSummary | null
}

export const SessionCtx = createContext<SessionValue | null>(null)

// SessionContext mirrors backend session/car state. On boot it fetches
// /api/cars and /api/sessions/current; thereafter the live WS keeps it
// fresh:
//   - `event` kinds `session_started` / `session_ended` invalidate the
//     cached current-session and list, triggering a refetch.
//   - The live frame's carId becomes the implicit "active" car. The
//     garage panel can override it with setSelectedCarId() — useful for
//     browsing other cars while still driving.
//
// Per-session detail (`/api/sessions/:id`) is fetched on demand via
// `loadSession`.

export function SessionProvider({ children }: { children: ReactNode }) {
  const [cars, setCars]                       = useState<CarSummary[]>([])
  const [carsLoading, setCarsLoading]         = useState(true)
  const [currentSession, setCurrentSession]   = useState<SessionListItem | null>(null)
  const [sessionsList, setSessionsList]       = useState<SessionListItem[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [loadedSessionId, setLoadedSessionId] = useState<string | null>(null)
  // `selectedCarId` is the user-pinned car (garage selection). Null
  // means "follow whatever the live frame is reporting", which is what
  // `activeCarId` resolves to.
  const [selectedCarId, setSelectedCarIdState] = useState<string | null>(null)
  const [liveCarId, setLiveCarId]              = useState<string | null>(null)

  // detail cache for /api/sessions/:id
  const detailRef = useRef<Record<string, SessionDetailResponse>>({})

  const refreshCars = useCallback(async () => {
    setCarsLoading(true)
    try {
      const r = await api.listCars()
      setCars(r?.cars ?? [])
    } catch (err) {
      console.warn('[session] listCars failed', err)
    } finally {
      setCarsLoading(false)
    }
  }, [])

  const refreshCurrent = useCallback(async () => {
    try {
      const s = await api.currentSession()
      setCurrentSession(s)
      if (s?.carId) setLiveCarId(s.carId)
    } catch (err) {
      console.warn('[session] currentSession failed', err)
      setCurrentSession(null)
    }
  }, [])

  const refreshSessionsList = useCallback(async (params?: ListSessionsParams) => {
    setSessionsLoading(true)
    try {
      const r = await api.listSessions(params)
      setSessionsList(Array.isArray(r) ? r : [])
    } catch (err) {
      console.warn('[session] listSessions failed', err)
      setSessionsList([])
    } finally {
      setSessionsLoading(false)
    }
  }, [])

  // Initial hydrate
  useEffect(() => {
    refreshCars()
    refreshCurrent()
  }, [refreshCars, refreshCurrent])

  // Backend pushes discrete `event`s on the live channel. The two we
  // care about for session bookkeeping are session_started and
  // session_ended — both invalidate the current pointer and the list.
  useEffect(() => {
    const offEvent = liveClient.subscribe('event', (msg: EventMessage) => {
      if (msg.kind === 'session_started' || msg.kind === 'session_ended') {
        refreshCurrent()
        refreshCars()
      }
    })
    return offEvent
  }, [refreshCurrent, refreshCars])

  const liveCarIdRef = useRef<string | null>(null)

  // Watch frames for the live carId. Frames come in fast so we throttle
  // to "only when it changes" rather than per-frame state churn.
  useEffect(() => {
    const offFrame = liveClient.subscribe('frame', (msg: Frame) => {
      const cid = msg?.carId
      if (cid && cid !== liveCarIdRef.current) {
        liveCarIdRef.current = cid
        setLiveCarId(cid)
      }
    })
    return offFrame
  }, [])

  // Resolved active car id — selectedCarId wins; otherwise the live
  // frame's car; otherwise the current session's car; otherwise the
  // most-recently-seen car.
  const activeCarId = useMemo<string | null>(() => {
    if (selectedCarId) return selectedCarId
    if (liveCarId) return liveCarId
    if (currentSession?.carId) return currentSession.carId
    if (cars.length) return cars[0]!.id
    return null
  }, [selectedCarId, liveCarId, currentSession, cars])

  const activeCar = useMemo<CarSummary | null>(
    () => cars.find((c) => c.id === activeCarId) || null,
    [cars, activeCarId]
  )

  // Refresh the sessions list whenever the active car changes (or when
  // a session event invalidates it). Empty string means "all cars".
  useEffect(() => {
    refreshSessionsList(activeCarId ? { carId: activeCarId, limit: 200 } : { limit: 200 })
  }, [activeCarId, refreshSessionsList])

  // Re-pull sessions on open/close events too — they often change
  // counts and best-laps mid-stream.
  useEffect(() => {
    const offEvent = liveClient.subscribe('event', (msg: EventMessage) => {
      if (msg.kind === 'session_started' || msg.kind === 'session_ended' || msg.kind === 'lap_completed') {
        refreshSessionsList(activeCarId ? { carId: activeCarId, limit: 200 } : { limit: 200 })
      }
    })
    return offEvent
  }, [activeCarId, refreshSessionsList])

  const setSelectedCarId = useCallback((carId: string | null) => {
    // Passing null/undefined clears the pin so we follow the live frame
    // again.
    setSelectedCarIdState(carId || null)
  }, [])

  const loadSession = useCallback(async (sessionId: string | null) => {
    if (!sessionId) { setLoadedSessionId(null); return null }
    if (!detailRef.current[sessionId]) {
      try {
        detailRef.current[sessionId] = await api.sessionDetail(sessionId)
      } catch (err) {
        console.warn('[session] sessionDetail failed', err)
        return null
      }
    }
    setLoadedSessionId(sessionId)
    return detailRef.current[sessionId] ?? null
  }, [])

  const clearLoadedSession = useCallback(() => setLoadedSessionId(null), [])

  const getLoadedSession = useCallback(
    () => loadedSessionId ? (detailRef.current[loadedSessionId] ?? null) : null,
    [loadedSessionId]
  )

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await api.deleteSession(sessionId)
      delete detailRef.current[sessionId]
      if (loadedSessionId === sessionId) setLoadedSessionId(null)
      await refreshSessionsList(activeCarId ? { carId: activeCarId, limit: 200 } : { limit: 200 })
      await refreshCurrent()
    } catch (err) { console.warn('[session] deleteSession failed', err) }
  }, [loadedSessionId, activeCarId, refreshSessionsList, refreshCurrent])

  const deleteCarSessions = useCallback(async (carId: string) => {
    try {
      await api.deleteCarSessions(carId)
      await refreshSessionsList(activeCarId ? { carId: activeCarId, limit: 200 } : { limit: 200 })
      await refreshCurrent()
      await refreshCars()
    } catch (err) { console.warn('[session] deleteCarSessions failed', err) }
  }, [activeCarId, refreshSessionsList, refreshCurrent, refreshCars])

  const renameCar = useCallback(async (ordinal: number | string, displayName: string) => {
    // Calls PATCH /api/cars/:ordinal then refreshes the cars list so
    // every panel showing the car name picks up the new value. Throws
    // on failure (404 unknown ordinal, 422 empty name) so callers can
    // surface the error to the user.
    const trimmed = (displayName || '').trim()
    if (!trimmed) throw new Error('Name must not be empty')
    if (ordinal == null) throw new Error('Car has no ordinal to rename')
    const res = await api.renameCar(ordinal, trimmed)
    await refreshCars()
    return res
  }, [refreshCars])

  const deleteCar = useCallback(async (carId: string) => {
    try {
      await api.deleteCar(carId)
      if (selectedCarId === carId) setSelectedCarIdState(null)
      await refreshCars()
      await refreshSessionsList(activeCarId ? { carId: activeCarId, limit: 200 } : { limit: 200 })
      await refreshCurrent()
    } catch (err) { console.warn('[session] deleteCar failed', err) }
  }, [selectedCarId, activeCarId, refreshCars, refreshSessionsList, refreshCurrent])

  const wipeAll = useCallback(async () => {
    try {
      await api.wipeAllData()
      detailRef.current = {}
      setLoadedSessionId(null)
      setSelectedCarIdState(null)
      await refreshCars()
      await refreshSessionsList()
      await refreshCurrent()
    } catch (err) { console.warn('[session] wipeAll failed', err) }
  }, [refreshCars, refreshSessionsList, refreshCurrent])

  const value = useMemo<SessionValue>(() => ({
    cars, carsLoading, refreshCars,
    currentSession, refreshCurrent,
    sessionsList, sessionsLoading, refreshSessionsList,
    loadedSessionId, loadSession, clearLoadedSession, getLoadedSession,
    deleteSession, deleteCar, deleteCarSessions, renameCar, wipeAll,
    selectedCarId, setSelectedCarId,
    liveCarId, activeCarId, activeCar,
  }), [
    cars, carsLoading, refreshCars,
    currentSession, refreshCurrent,
    sessionsList, sessionsLoading, refreshSessionsList,
    loadedSessionId, loadSession, clearLoadedSession, getLoadedSession,
    deleteSession, deleteCar, deleteCarSessions, renameCar, wipeAll,
    selectedCarId, setSelectedCarId,
    liveCarId, activeCarId, activeCar,
  ])

  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionCtx)
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>')
  return ctx
}
