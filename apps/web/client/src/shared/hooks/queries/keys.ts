// Stable query-key factories. One per feature; keys form a hierarchy
// so invalidating `predictionKeys.all` busts every prediction query
// at once. Each leaf returns a tuple typed `as const` so accidental
// shape drift in a consumer trips a TS error.
//
// Convention: the first element is the feature namespace; the second
// element is the entity ("lap", "tireFailure", …); subsequent elements
// are query parameters in the order they affect the response.

export const predictionKeys = {
  all:          ['predictions'] as const,
  lap:          (sessionId: string, n: number) => ['predictions', 'lap', sessionId, n] as const,
  tireFailure:  (sessionId: string)            => ['predictions', 'tireFailure', sessionId] as const,
  finish:       ()                             => ['predictions', 'finish'] as const,
  crashRisk:    (windowS: number)              => ['predictions', 'crashRisk', windowS] as const,
  shiftReport:  (sessionId: string)            => ['predictions', 'shiftReport', sessionId] as const,
}

export const sessionKeys = {
  all:    ['sessions'] as const,
  list:   (params: Record<string, unknown>) => ['sessions', 'list', params] as const,
  current: ()                                => ['sessions', 'current'] as const,
  detail:  (id: string)                      => ['sessions', 'detail', id] as const,
  frames:  (id: string, opts: Record<string, unknown>) => ['sessions', 'frames', id, opts] as const,
}

export const carKeys = {
  all:  ['cars'] as const,
  list: () => ['cars', 'list'] as const,
}

export const driverKeys = {
  all:     ['driver'] as const,
  profile: () => ['driver', 'profile'] as const,
}

export const coachKeys = {
  all:    ['coach'] as const,
  status: () => ['coach', 'status'] as const,
}

export const settingsKeys = {
  all: ['settings'] as const,
  current: () => ['settings', 'current'] as const,
}
