// Thin REST wrapper over the backend documented in api-contract.md. All
// paths are origin-relative so the same module works against the dev
// proxy and against the nginx-served prod build.
//
// Only methods with at least one consumer in this app live here. New
// endpoints are added on demand — keeping the surface small makes the
// mock layer below cheap to reason about and keeps the contract test
// surface honest. Phase 3 §1.3 #3 pruned ~20 declared-but-uncalled
// methods (layouts CRUD, generic /coach/{ask,insights,replay},
// driver/evolution, track/optimal-line, track/mistakes, widget catalog,
// counter-factual whatIf, generic replay fetch, healthz, the legacy
// `predictTire`/`bestAchievable`/`carAggregate`/`trackCurrent`/`predictShift`
// duplicates). Re-add a method here when a real caller lands.

import type { components } from '@fh-racer/contract/api'

type Schemas = components['schemas']
type CarSummary = Schemas['CarSummary']
type CarListResponse = Schemas['CarListResponse']
type SessionListItem = Schemas['SessionListItem']
type SessionDetailResponse = Schemas['SessionDetailResponse']
type SessionFramesResponse = Schemas['SessionFramesResponse']
type DriverProfileResponse = Schemas['DriverProfileResponse']
type LapPredictionResponse = Schemas['LapPredictionResponse']
type TireFailurePredictionResponse = Schemas['TireFailurePredictionResponse']
type FinishPredictionResponse = Schemas['FinishPredictionResponse']
type CrashRiskPredictionResponse = Schemas['CrashRiskPredictionResponse']
type ShiftReportResponse = Schemas['ShiftReportResponse']
type CoachStatus = Schemas['CoachStatus']
type SettingsResponse = Schemas['SettingsResponse']

// Sandbox mock layer. Tests (or the dev sandbox) install per-method
// overrides via setApiMocks({ predictCrash: async (...args) => fake }).
// While set, any api method whose name is a key in the map calls that
// fn instead of hitting the network. Pass `null` to clear.
export type ApiMocks = Partial<{
  [K in keyof typeof __api]: (...args: Parameters<(typeof __api)[K]>) => unknown
}>
let __apiMocks: ApiMocks | null = null
export function setApiMocks(mocks: ApiMocks | null): void { __apiMocks = mocks || null }

// ApiError carries the backend's structured error shape (api-contract
// §1 errors). 400/404/422 responses come back as
//   { error, message, field?, supported?, resource?, header? }
// (wrapped under FastAPI's `detail` key) — we hoist those fields onto
// the thrown Error so callers can branch on `err.code` instead of
// regex-matching `err.message`. Phase 3 §1.3: this replaces the
// previous "throw Error('/path -> status body')" that lost the
// discriminator entirely.
interface ErrorDetail {
  error?: string
  message?: string
  field?: string
  supported?: unknown
  resource?: string
  header?: string
}

export class ApiError extends Error {
  readonly path: string
  readonly status: number
  readonly code: string | undefined
  readonly detail: ErrorDetail | string | null
  readonly field?: string
  readonly supported?: unknown
  readonly resource?: string
  readonly header?: string

  constructor(path: string, status: number, body: unknown) {
    const wrapper = (body && typeof body === 'object') ? (body as { detail?: unknown }) : null
    const detail = (wrapper && 'detail' in wrapper ? wrapper.detail : body) as ErrorDetail | string | null
    const code = (detail && typeof detail === 'object') ? detail.error : undefined
    const message = (detail && typeof detail === 'object' && detail.message)
      || (typeof detail === 'string' ? detail : `${path} -> ${status}`)
    super(`${path} -> ${status}${code ? ` (${code})` : ''}: ${message}`)
    this.name = 'ApiError'
    this.path = path
    this.status = status
    this.code = code
    this.detail = detail
    if (detail && typeof detail === 'object') {
      if (detail.field    != null) this.field = detail.field
      if (detail.supported != null) this.supported = detail.supported
      if (detail.resource != null) this.resource = detail.resource
      if (detail.header   != null) this.header = detail.header
    }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    let body: unknown = null
    const ct = res.headers.get('content-type') || ''
    try {
      body = ct.includes('application/json') ? await res.json() : await res.text()
    } catch { /* ignore parse failure — ApiError tolerates null */ }
    throw new ApiError(path, res.status, body)
  }
  if (res.status === 204) return null as T
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('application/json') ? res.json() : res.text()) as Promise<T>
}

export interface ListSessionsParams {
  carId?: string
  type?: string
  from?: string
  to?: string
  limit?: number
  cursor?: string
}

export interface SessionFramesOpts {
  hz?: 10 | 30 | 60
  fields?: string | string[]
  from?: number
  to?: number
}

const __api = {
  // --- cars
  listCars:        ():                                Promise<CarListResponse> => request('/api/cars'),
  // PATCH /api/cars/:ordinal — crowdsource a real name for the car
  // identified by ``carOrdinal``. Backend stamps every cars row sharing
  // that ordinal and the DB row wins over the static ordinal_lookup
  // seed on subsequent reads.
  renameCar:       (ordinal: number | string, displayName: string): Promise<CarSummary> => request(`/api/cars/${encodeURIComponent(ordinal)}`, {
    method: 'PATCH',
    body: JSON.stringify({ displayName }),
  }),
  deleteCar:       (id: string):                      Promise<null> => request(`/api/cars/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  deleteCarSessions: (id: string):                    Promise<null> => request(`/api/cars/${encodeURIComponent(id)}/sessions`, { method: 'DELETE' }),
  wipeAllData:     ():                                Promise<null> => request('/api/data/all', { method: 'DELETE', headers: { 'X-Confirm': 'true' } }),

  // --- sessions
  listSessions:    (params: ListSessionsParams = {}): Promise<SessionListItem[]> => {
    const qs = new URLSearchParams()
    if (params.carId) qs.set('carId', params.carId)
    if (params.type)  qs.set('type', params.type)
    if (params.from)  qs.set('from', params.from)
    if (params.to)    qs.set('to', params.to)
    if (params.limit) qs.set('limit', String(params.limit))
    if (params.cursor) qs.set('cursor', params.cursor)
    const q = qs.toString()
    return request(`/api/sessions${q ? `?${q}` : ''}`)
  },
  currentSession:  ():                                Promise<SessionListItem | null> => request<SessionListItem>('/api/sessions/current').catch((e: unknown) => {
    if (e instanceof ApiError && e.status === 404) return null
    return Promise.reject(e)
  }),
  sessionDetail:   (id: string):                      Promise<SessionDetailResponse> => request(`/api/sessions/${encodeURIComponent(id)}`),
  sessionFrames:   (id: string, opts: SessionFramesOpts = {}): Promise<SessionFramesResponse> => {
    const qs = new URLSearchParams()
    if (opts.hz)     qs.set('hz', String(opts.hz))
    if (opts.fields) qs.set('fields', Array.isArray(opts.fields) ? opts.fields.join(',') : opts.fields)
    if (opts.from != null) qs.set('from', String(opts.from))
    if (opts.to   != null) qs.set('to',   String(opts.to))
    const q = qs.toString()
    return request(`/api/sessions/${encodeURIComponent(id)}/frames${q ? `?${q}` : ''}`)
  },
  deleteSession:   (id: string):                      Promise<null> => request(`/api/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // --- driver
  driverProfile:   ():                                Promise<DriverProfileResponse> => request('/api/driver/profile'),

  // --- predict
  predictLap:      (n: number = 5, sessionId: string = 'live'): Promise<LapPredictionResponse> => request(`/api/predict/lap?n=${n}&sessionId=${encodeURIComponent(sessionId)}`),
  predictTireFailure: (sessionId: string = 'live'):   Promise<TireFailurePredictionResponse> => request(`/api/predict/tireFailure?sessionId=${encodeURIComponent(sessionId)}`),
  predictFinish:   ():                                Promise<FinishPredictionResponse> => request('/api/predict/finish'),
  predictCrash:    (windowS: number = 30):            Promise<CrashRiskPredictionResponse> => request(`/api/predict/crashRisk?windowS=${windowS}`),
  predictShiftReport: (sessionId: string = 'live'):   Promise<ShiftReportResponse> => request(`/api/predict/shift/report?sessionId=${encodeURIComponent(sessionId)}`),
  resetShift:          (body: unknown):               Promise<unknown> => request('/api/predict/shift/reset', { method: 'POST', body: JSON.stringify(body) }),

  // --- coach
  coachStatus:     ():                                Promise<CoachStatus> => request('/api/coach/status'),

  // --- settings
  getSettings:     ():                                Promise<SettingsResponse> => request('/api/settings'),
  patchSettings:   (partial: Partial<SettingsResponse>): Promise<SettingsResponse> => request('/api/settings', { method: 'PATCH', body: JSON.stringify(partial) }),
}

export type Api = typeof __api

export const api: Api = new Proxy(__api, {
  get(target, prop: string | symbol) {
    const orig = (target as Record<string | symbol, unknown>)[prop]
    if (typeof orig !== 'function') return orig
    return (...args: unknown[]) => {
      if (__apiMocks && typeof (__apiMocks as Record<string, unknown>)[prop as string] === 'function') {
        const mockFn = (__apiMocks as Record<string, (...a: unknown[]) => unknown>)[prop as string]!
        // Always resolve in a microtask so callers get Promise-like behaviour
        return Promise.resolve(mockFn(...args))
      }
      return (orig as (...a: unknown[]) => unknown)(...args)
    }
  },
}) as Api
