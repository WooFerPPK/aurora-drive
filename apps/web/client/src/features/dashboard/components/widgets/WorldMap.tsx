import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Frame, MotionBlock } from '@fh-racer/contract/ws'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { useSettings } from '@/features/settings/context/SettingsContext'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useReplay } from '@/features/dashboard/context/ReplayContext'
import { useNotify } from '@/shared/context/NotificationContext'
import { liveClient } from '@/shared/lib/wsClient'
import { useSessionFramesQuery } from '@/shared/hooks/queries/sessions'
import type { SessionFramesOpts } from '@/shared/lib/api'
import {
  MAP_CONFIG, xyzSimpleCRS,
  computeTransform, worldToPix,
} from '@/shared/lib/worldMapCalibration'
import type { Calibration, PixelTransform } from '@/shared/lib/worldMapCalibration'
import { predictPath, projectAlongMotion } from '@/features/dashboard/lib/trajectoryPrediction'
import { cx } from '@/shared/lib/format'

// World map. Renders the car's position on a pre-rendered raster of the
// FH6 world.
//
// `world-map` (root) is kept as a marker for the Leaflet-scoped rules in
// index.css: `.world-map .leaflet-*` styles the third-party DOM that
// Leaflet creates outside React. Same for `world-map-arrow*`,
// `world-map-predict`, `world-map-brake*` — all set on Leaflet divIcons
// or polylines that aren't in our render tree.

// Tailwind class strings for the React-rendered DOM.
const WRAP =
  'world-map relative w-full h-full overflow-hidden rounded-[10px]'

const HOST = 'world-map-host absolute inset-0'

const OVERLAY =
  'absolute top-2.5 left-2.5 flex flex-col gap-1 px-2.5 py-2 ' +
  'bg-[rgba(26,8,38,0.62)] border border-[rgba(255,193,220,0.20)] rounded-lg ' +
  '[backdrop-filter:blur(10px)_saturate(140%)] pointer-events-none z-[400]'

const OVERLAY_ROW = 'flex items-baseline gap-2'

const OVERLAY_LBL_BASE = 'font-display text-[12px] [letter-spacing:0.20em] uppercase text-ink-faint'
const OVERLAY_LBL_HERO = 'text-[16px]'

const OVERLAY_VAL_BASE = 'font-mono text-[13px] text-cream'
const OVERLAY_VAL_HERO = 'text-[16px]'

const EMPTY =
  'absolute inset-0 flex flex-col items-center justify-center gap-3 p-[22px] text-center ' +
  '[background:linear-gradient(180deg,rgba(26,8,38,0.40)_0%,rgba(26,8,38,0.78)_100%)] ' +
  '[backdrop-filter:blur(6px)] z-[500]'
const EMPTY_COMPACT = 'p-2'

const EMPTY_TITLE = 'font-display [letter-spacing:0.22em] uppercase text-[13px] text-bubblegum'
const EMPTY_BODY = 'font-ui text-[12px] text-ink-dim max-w-[260px] leading-[1.5]'

const TOOLBAR = 'absolute top-2.5 right-2.5 z-[450] flex gap-1.5'

const ICON_BTN_BASE =
  'inline-flex items-center justify-center bg-[rgba(26,8,38,0.70)] ' +
  'border border-[rgba(255,193,220,0.22)] text-ink cursor-pointer ' +
  '[backdrop-filter:blur(8px)] [transition:background_120ms_ease,border-color_120ms_ease,color_120ms_ease] ' +
  'min-w-[32px] h-8 px-2.5 rounded-full ' +
  'font-display text-[14px] [letter-spacing:0.10em] uppercase ' +
  'hover:bg-[rgba(58,24,80,0.90)] hover:border-[rgba(255,193,220,0.45)] hover:text-cream'
const ICON_BTN_ON =
  'bg-[rgba(168,243,208,0.18)] border-[rgba(168,243,208,0.65)] text-cream ' +
  '[box-shadow:0_0_14px_rgba(168,243,208,0.30)]'

const RECENTRE =
  'absolute bottom-2.5 right-2.5 z-[450] inline-flex items-center justify-center ' +
  'bg-[rgba(26,8,38,0.70)] border border-[rgba(255,193,220,0.22)] text-ink cursor-pointer ' +
  '[backdrop-filter:blur(8px)] [transition:background_120ms_ease,border-color_120ms_ease,color_120ms_ease] ' +
  'px-3 py-1.5 rounded-full font-display text-[10px] [letter-spacing:0.18em] uppercase ' +
  'hover:bg-[rgba(58,24,80,0.90)] hover:border-[rgba(255,193,220,0.45)] hover:text-cream'

const CAL =
  'absolute left-2.5 right-2.5 bottom-2.5 z-[600] px-3.5 pt-3 pb-2.5 ' +
  'bg-[rgba(26,8,38,0.84)] border border-[rgba(255,193,220,0.22)] rounded-xl ' +
  '[backdrop-filter:blur(14px)_saturate(140%)] [box-shadow:0_8px_30px_rgba(255,94,167,0.10)]'

const CAL_HEAD = 'flex items-center justify-between mb-2.5'

const CAL_BODY_BASE = 'grid grid-cols-2 gap-2.5'
const CAL_BODY_COMPACT = 'grid-cols-1'

const CAL_FOOT = 'mt-3 flex items-center gap-2'
const CAL_SPACER = 'flex-1'

const CAL_SLOT_BASE =
  'px-2.5 py-2 bg-[rgba(58,24,80,0.45)] border border-[rgba(255,193,220,0.14)] ' +
  'rounded-lg flex flex-col gap-1.5'
const CAL_SLOT_ACTIVE =
  'border-[rgba(255,94,167,0.55)] ' +
  '[box-shadow:0_0_0_1px_rgba(255,94,167,0.20),0_0_18px_rgba(255,94,167,0.18)_inset]'

const CAL_SLOT_LABEL =
  'font-display text-[10px] [letter-spacing:0.22em] uppercase text-bubblegum'
const CAL_SLOT_ROW = 'grid grid-cols-[44px_1fr_auto] gap-2 items-center'
const CAL_SLOT_KEY = 'font-display text-[9px] [letter-spacing:0.18em] uppercase text-ink-faint'
const CAL_SLOT_VAL = 'font-mono text-[11px] text-ink overflow-hidden text-ellipsis whitespace-nowrap'

const HEATMAP =
  'absolute left-2.5 bottom-2.5 z-[450] flex flex-col gap-1.5 px-2.5 py-2 ' +
  'bg-[rgba(26,8,38,0.72)] border border-[rgba(255,193,220,0.22)] rounded-[10px] ' +
  '[backdrop-filter:blur(10px)_saturate(140%)] max-w-[240px]'

const HEATMAP_PICKER = 'flex gap-1 flex-wrap'

const HEATMAP_BTN_BASE =
  'px-2 py-1 bg-transparent border border-[rgba(255,193,220,0.16)] rounded-full text-ink-faint cursor-pointer ' +
  'font-display text-[12px] [letter-spacing:0.18em] uppercase ' +
  '[transition:background_120ms_ease,border-color_120ms_ease,color_120ms_ease] ' +
  'hover:border-[rgba(255,193,220,0.40)] hover:text-ink'
const HEATMAP_BTN_HERO = 'text-[16px]'
const HEATMAP_BTN_ON =
  'bg-[rgba(255,94,167,0.18)] border-[rgba(255,94,167,0.55)] text-cream ' +
  '[box-shadow:0_0_14px_rgba(255,94,167,0.18)]'

const HEATMAP_LEGEND = 'flex flex-col gap-[3px]'

const HEATMAP_BAR =
  'h-1.5 rounded-full opacity-[0.92] ' +
  '[background:linear-gradient(90deg,#b8d4ff_0%,#caa6ff_20%,#ff8cba_40%,#ff5ea7_60%,#ffe082_80%,#fff7f0_100%)]'

const HEATMAP_RANGE_BASE =
  'flex justify-between items-baseline gap-1.5 font-mono text-[12px] text-ink-faint ' +
  '[&>:nth-child(2)]:font-display [&>:nth-child(2)]:[letter-spacing:0.18em] ' +
  '[&>:nth-child(2)]:uppercase [&>:nth-child(2)]:text-bubblegum'
const HEATMAP_RANGE_HERO = 'text-[16px]'

const ZOOM =
  'absolute top-12 right-2.5 z-[450] flex flex-col rounded-[10px] overflow-hidden ' +
  'bg-[rgba(26,8,38,0.70)] border border-[rgba(255,193,220,0.22)] [backdrop-filter:blur(8px)]'

const ZOOM_BTN =
  'w-7 h-7 inline-flex items-center justify-center bg-transparent border-0 text-ink cursor-pointer ' +
  'font-display text-[16px] leading-none [transition:background_120ms_ease,color_120ms_ease] ' +
  'hover:bg-[rgba(58,24,80,0.90)] hover:text-cream ' +
  '[&+&]:border-t [&+&]:border-[rgba(255,193,220,0.18)]'

const REPLAY_BADGE =
  'absolute top-3 left-1/2 -translate-x-1/2 z-[500] inline-flex items-center gap-2 px-3 py-[5px] ' +
  'bg-[rgba(58,24,80,0.85)] border border-[color:color-mix(in_srgb,var(--amber)_50%,transparent)] ' +
  'rounded-full [backdrop-filter:blur(10px)_saturate(140%)] ' +
  'font-display text-[10px] [letter-spacing:0.20em] uppercase text-cream ' +
  'max-w-[calc(100%-100px)]'

const REPLAY_DOT =
  'w-1.5 h-1.5 rounded-full bg-amber [box-shadow:0_0_10px_var(--amber)] ' +
  'animate-[pulse_1.6s_ease-in-out_infinite] flex-shrink-0'

const REPLAY_LABEL = 'text-amber'

const REPLAY_NAME =
  'text-ink font-ui normal-case [letter-spacing:0.04em] ' +
  'overflow-hidden text-ellipsis whitespace-nowrap min-w-0'

const REPLAY_COUNT =
  'text-ink-faint font-mono text-[9px] [letter-spacing:0] normal-case flex-shrink-0'

/* eslint-disable @typescript-eslint/no-explicit-any */
type LeafletMap    = any
type LeafletMarker = any
type LeafletPoly   = any

const TRAIL_HZ      = 10
const TRAIL_MAX     = 600
const STALE_MS      = 1500
const PREDICT_HZ    = 20
const PREDICT_HORIZON_S = 2.0
const MIN_SPEED_MPS = 3.0

type HeatmapId = 'v' | 'g' | 'th' | 'br' | 'tt'

interface HeatmapLayer {
  id: HeatmapId
  label: string
  short: string
  max: number
  units: string
  get: (f: Frame | null | undefined) => number
}

const HEATMAP_LAYERS: HeatmapLayer[] = [
  { id: 'v',  label: 'SPEED',    short: 'SPD',  max: 180,  units: 'km/h',
    get:    (f) => (f?.motion?.speed_mps ?? 0) * 3.6 },
  { id: 'g',  label: 'G-FORCE',  short: 'G',    max: 2.5,  units: 'g',
    get:    gForceG },
  { id: 'th', label: 'THROTTLE', short: 'THR',  max: 1.0,  units: '',
    get:    (f) => f?.inputs?.throttle ?? 0 },
  { id: 'br', label: 'BRAKE',    short: 'BRK',  max: 1.0,  units: '',
    get:    (f) => f?.inputs?.brake ?? 0 },
  { id: 'tt', label: 'TIRE',     short: 'TIRE', max: 0.8,  units: 'norm',
    get:    avgTireTempNorm },
]
const HEATMAP_BY_ID: Record<HeatmapId, HeatmapLayer> = Object.fromEntries(
  HEATMAP_LAYERS.map((l) => [l.id, l] as const),
) as Record<HeatmapId, HeatmapLayer>

const REPLAY_FIELDS = new Set<HeatmapId>(['v', 'th', 'br'])

const BUCKET_COLORS = [
  '#b8d4ff',
  '#caa6ff',
  '#ff8cba',
  '#ff5ea7',
  '#ffe082',
  '#fff7f0',
]
function bucketIndex(t: number): number {
  if (t < 0.20) return 0
  if (t < 0.40) return 1
  if (t < 0.60) return 2
  if (t < 0.80) return 3
  if (t < 0.95) return 4
  return 5
}

function gForceG(frame: Frame | null | undefined): number {
  const a = frame?.motion?.acceleration
  if (!a) return 0
  return Math.hypot(a.x ?? 0, a.z ?? 0) / 9.81
}
function avgTireTempNorm(frame: Frame | null | undefined): number {
  const w = frame?.wheels
  if (!w) return 0
  return (
    (w.fl?.tireTemp_normWindow ?? 0) +
    (w.fr?.tireTemp_normWindow ?? 0) +
    (w.rl?.tireTemp_normWindow ?? 0) +
    (w.rr?.tireTemp_normWindow ?? 0)
  ) / 4
}

interface TrailSample {
  t?: number
  ll: [number, number]
  v: number
  g: number
  th: number
  br: number
  tt: number
}

interface ReplayMeta {
  sessionId: string
  name: string | null
  carId: string | null
  count: number
}

export interface WorldMapProps {
  w: number
  h: number
}

export default function WorldMap({ w, h }: WorldMapProps) {
  const tier =
    w * h <= 9 ? 'compact'
    : w * h <= 20 ? 'standard'
    : 'hero'

  const hostRef        = useRef<HTMLDivElement>(null)
  const mapRef         = useRef<LeafletMap | null>(null)
  const tileLayerRef   = useRef<any>(null)
  const markerRef      = useRef<LeafletMarker | null>(null)
  const heatmapPolysRef = useRef<LeafletPoly[] | null>(null)
  const trailBufRef    = useRef<TrailSample[]>([])
  const lastTrailMsRef = useRef(0)
  const brakeLineRef     = useRef<LeafletPoly | null>(null)
  const brakeMarkRef     = useRef<any>(null)
  const predictLineRef   = useRef<LeafletPoly | null>(null)
  const lastPredictMsRef = useRef(0)
  const transformRef   = useRef<PixelTransform | null>(null)
  const overlayRef     = useRef<HTMLDivElement>(null)
  const followRef      = useRef(true)
  const prevRaceOnRef  = useRef(false)

  const [following, setFollowingState] = useState(true)
  const [calOpen, setCalOpen]          = useState(false)
  const [saving, setSaving]            = useState(false)
  const [heatmapField, setHeatmapFieldState] = useState<HeatmapId>('v')
  const heatmapFieldRef = useRef<HeatmapId>('v')
  const [mode3D, setMode3DState] = useState(false)
  const mode3DRef = useRef(false)

  const { settings, patch: patchSettings } = useSettings()
  const { loadedSessionId, getLoadedSession } = useSession()
  const replay = useReplay()
  const notify = useNotify()
  const cal = (settings?.worldMap?.calibration as Calibration | null | undefined) ?? null

  const replayBufRef       = useRef<TrailSample[] | null>(null)
  const [replayMeta, setReplayMeta] = useState<ReplayMeta | null>(null)

  const setFollowing = (v: boolean): void => {
    followRef.current = v
    setFollowingState(v)
  }

  const setHeatmapField = (id: HeatmapId): void => {
    heatmapFieldRef.current = id
    setHeatmapFieldState(id)
    rebuildHeatmap(trailBufRef.current, id, heatmapPolysRef.current)
  }

  const clearTrail = (): void => {
    trailBufRef.current = []
    rebuildHeatmap([], heatmapFieldRef.current, heatmapPolysRef.current)
  }

  const setMode3D = (v: boolean): void => {
    mode3DRef.current = v
    setMode3DState(v)
    if (v) {
      setFollowing(true)
      const m = mapRef.current
      if (m) m.setView(m.getCenter(), m.getZoom(), { animate: false })
    } else if (hostRef.current) {
      hostRef.current.style.transform = ''
      hostRef.current.style.transformOrigin = ''
    }
  }

  useEffect(() => {
    transformRef.current = computeTransform(cal)
  }, [cal])

  useEffect(() => {
    if (replayMeta && !REPLAY_FIELDS.has(heatmapField)) {
      setHeatmapField('v')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayMeta, heatmapField])

  const replayFrameOpts = useMemo<SessionFramesOpts>(() => ({
    hz: 10,
    fields: 'speed,throttle,brake,position',
  }), [])
  const { data: replayFramesData, error: replayFramesError } = useSessionFramesQuery(
    loadedSessionId,
    replayFrameOpts,
  )

  useEffect(() => {
    if (!loadedSessionId) {
      replayBufRef.current = null
      setReplayMeta(null)
      rebuildHeatmap(trailBufRef.current, heatmapFieldRef.current, heatmapPolysRef.current)
      return
    }
    const t = transformRef.current
    const map = mapRef.current
    if (!t || !map) return
    if (!replayFramesData) return

    const rows: any[] = (replayFramesData as any)?.data ?? []
    const buf: TrailSample[] = []
    for (const row of rows) {
      const tRow      = row[0]
      const speed_mps = row[1]
      const throttle  = row[2]
      const brake     = row[3]
      const pos       = row[4]
      if (!pos || pos.length !== 3) continue
      const [pxp, pyp] = worldToPix(t, pos[0], pos[2])
      const ll = map.unproject(L.point(pxp, pyp), MAP_CONFIG.maxZoom)
      buf.push({
        t:  tRow ?? 0,
        ll: [ll.lat, ll.lng],
        v:  (speed_mps ?? 0) * 3.6,
        g:  0,
        th: throttle ?? 0,
        br: brake ?? 0,
        tt: 0,
      })
    }
    replayBufRef.current = buf
    const meta = getLoadedSession?.() ?? null
    setReplayMeta({
      sessionId: loadedSessionId,
      name:      meta?.name ?? null,
      carId:     meta?.carId ?? null,
      count:     buf.length,
    })
    rebuildHeatmap(buf, heatmapFieldRef.current, heatmapPolysRef.current)
    if (buf.length > 1) {
      const bounds = L.latLngBounds(buf.map((p) => p.ll))
      map.fitBounds(bounds, { padding: [24, 24], animate: false })
      setFollowing(false)
    }
  }, [loadedSessionId, cal, getLoadedSession, replayFramesData])

  useEffect(() => {
    if (!replayFramesError) return
    console.warn('[world_map] session frames fetch failed', replayFramesError)
    notify.error('Replay load failed', { message: replayFramesError.message ?? String(replayFramesError) })
  }, [replayFramesError, notify])

  useEffect(() => {
    if (!hostRef.current) return
    const map = L.map(hostRef.current, {
      crs:                 xyzSimpleCRS(L),
      attributionControl:  false,
      zoomControl:         false,
      minZoom:             MAP_CONFIG.minZoom,
      maxZoom:             MAP_CONFIG.viewMaxZoom,
      maxBoundsViscosity:  1.0,
    })

    tileLayerRef.current = L.tileLayer(MAP_CONFIG.tileUrl, {
      minZoom:       MAP_CONFIG.minZoom,
      maxZoom:       MAP_CONFIG.viewMaxZoom,
      maxNativeZoom: MAP_CONFIG.maxZoom,
      tileSize:      MAP_CONFIG.tileSize,
      noWrap:        true,
      keepBuffer:    6,
      errorTileUrl:  '',
    }).addTo(map)

    const _origGetTiledPixelBounds = tileLayerRef.current._getTiledPixelBounds.bind(tileLayerRef.current)
    tileLayerRef.current._getTiledPixelBounds = function (center: any): any {
      const b = _origGetTiledPixelBounds(center)
      if (!mode3DRef.current) return b
      const size = b.max.subtract(b.min)
      const pad  = new L.Point(size.x * 0.6, size.y * 0.6)
      return new L.Bounds(b.min.subtract(pad), b.max.add(pad))
    }

    map.setView(
      map.unproject(L.point(...MAP_CONFIG.defaultCenter), MAP_CONFIG.maxZoom),
      MAP_CONFIG.defaultZoom,
    )

    heatmapPolysRef.current = BUCKET_COLORS.map((color) =>
      L.polyline([], {
        color,
        weight: 3,
        opacity: 0.92,
        lineCap: 'round',
        className: 'world-map-trail',
      }).addTo(map),
    )

    predictLineRef.current = L.polyline([], {
      color:     '#a8f3d0',
      weight:    3,
      opacity:   0.80,
      lineCap:   'round',
      className: 'world-map-predict',
    }).addTo(map)

    brakeLineRef.current = L.polyline([], {
      color:     '#ffe082',
      weight:    2,
      opacity:   0.85,
      dashArray: '5,4',
      className: 'world-map-brake',
    }).addTo(map)
    brakeMarkRef.current = L.circleMarker([0, 0], {
      radius:      0,
      color:       '#ffe082',
      fillColor:   '#ffe082',
      fillOpacity: 0.20,
      weight:      1.5,
      interactive: false,
      className:   'world-map-brake-mark',
    }).addTo(map)

    markerRef.current = L.marker(
      map.unproject(L.point(...MAP_CONFIG.defaultCenter), MAP_CONFIG.maxZoom),
      { icon: makeArrowIcon(0, tier), interactive: false, keyboard: false },
    ).addTo(map)

    const userUnfollow = (e: any): void => {
      if (e?.originalEvent) setFollowing(false)
    }
    map.on('dragstart', userUnfollow)
    map.on('zoomstart', userUnfollow)

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current        = null
      tileLayerRef.current  = null
      markerRef.current     = null
      heatmapPolysRef.current = null
      brakeLineRef.current  = null
      brakeMarkRef.current  = null
      predictLineRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tier])

  useFrameLoop((frame, { frameAgeMs }) => {
    const map = mapRef.current
    const marker = markerRef.current
    if (!map || !marker) return

    if (replayBufRef.current) {
      const buf = replayBufRef.current
      brakeLineRef.current?.setLatLngs([])
      predictLineRef.current?.setLatLngs([])
      brakeMarkRef.current?.setRadius(0)

      if (buf.length === 0) {
        if (marker._icon) marker._icon.style.opacity = '0'
        writeOverlay(overlayRef.current, null, null, tier)
        return
      }

      const tScrub = (replay as any).tRef?.current ?? 0
      let lo = 0, hi = buf.length - 1
      while (lo <= hi) {
        const mid = (lo + hi) >> 1
        if ((buf[mid]!.t ?? 0) <= tScrub) lo = mid + 1
        else hi = mid - 1
      }
      const idx = Math.max(0, hi)
      const sample = buf[idx]!

      if (marker._icon) marker._icon.style.opacity = '1'
      marker.setLatLng(sample.ll)
      if (marker._icon) {
        let headingDeg = 0
        if (idx + 1 < buf.length) {
          const next = buf[idx + 1]!
          const dLat = next.ll[0] - sample.ll[0]
          const dLng = next.ll[1] - sample.ll[1]
          if (dLat || dLng) headingDeg = (Math.atan2(dLng, dLat) * 180) / Math.PI
        }
        const arrow = marker._icon.firstElementChild
        if (arrow) arrow.style.transform = `rotate(${headingDeg}deg)`
      }

      if (followRef.current) {
        map.setView(sample.ll, map.getZoom(), { animate: false })
      }

      const replayFrame = {
        motion: {
          speed_mps: (sample.v ?? 0) / 3.6,
          orientation: { yaw: 0 },
        },
        inputs: { throttle: sample.th ?? 0, brake: sample.br ?? 0 },
      } as unknown as Frame
      writeOverlay(overlayRef.current, replayFrame, sample.ll, tier)
      return
    }

    const t = transformRef.current
    const pos = frame?.motion?.position
    const yaw = frame?.motion?.orientation?.yaw ?? 0

    const live = frame && (frameAgeMs ?? 0) <= STALE_MS && t && pos
    if (!live) {
      if (marker._icon) marker._icon.style.opacity = '0.35'
      writeOverlay(overlayRef.current, null, null, tier)
      return
    }
    if (marker._icon) marker._icon.style.opacity = '1'

    const [px, py] = worldToPix(t!, pos!.x, pos!.z)
    const ll = map.unproject(L.point(px, py), MAP_CONFIG.maxZoom)

    marker.setLatLng(ll)
    if (marker._icon) {
      const headingDeg = (yaw * 180) / Math.PI
      const arrow = marker._icon.firstElementChild
      if (arrow) arrow.style.transform = `rotate(${headingDeg}deg)`
    }

    const now = performance.now()
    if (now - lastTrailMsRef.current >= 1000 / TRAIL_HZ) {
      lastTrailMsRef.current = now
      const buf = trailBufRef.current
      buf.push({
        ll: [ll.lat, ll.lng],
        v:  HEATMAP_BY_ID.v.get(frame),
        g:  HEATMAP_BY_ID.g.get(frame),
        th: HEATMAP_BY_ID.th.get(frame),
        br: HEATMAP_BY_ID.br.get(frame),
        tt: HEATMAP_BY_ID.tt.get(frame),
      })
      if (buf.length > TRAIL_MAX) buf.shift()
      if (tier === 'compact') {
        if (buf.length) buf.length = 0
        rebuildHeatmap([], heatmapFieldRef.current, heatmapPolysRef.current)
      } else {
        rebuildHeatmap(buf, heatmapFieldRef.current, heatmapPolysRef.current)
      }
    }

    if (frame!.isRaceOn && !prevRaceOnRef.current) {
      trailBufRef.current = []
      rebuildHeatmap([], heatmapFieldRef.current, heatmapPolysRef.current)
    }
    prevRaceOnRef.current = !!frame!.isRaceOn

    if (followRef.current) {
      map.setView(ll, map.getZoom(), { animate: false })
    }

    if (mode3DRef.current && hostRef.current) {
      const yawDeg = (yaw * 180) / Math.PI
      hostRef.current.style.transformOrigin = '50% 50%'
      hostRef.current.style.transform =
        `perspective(700px) rotateX(55deg) rotate(${-yawDeg}deg) scale(1.6)`
    }

    if (now - lastPredictMsRef.current >= 1000 / PREDICT_HZ) {
      lastPredictMsRef.current = now
      updatePredictions(map, t!, frame!, {
        brakeLine:   brakeLineRef.current,
        brakeMark:   brakeMarkRef.current,
        predictLine: predictLineRef.current,
        carLL:       ll,
      })
    }

    writeOverlay(overlayRef.current, frame, pos, tier)
  })

  const onCalibrationSaved = async (next: Calibration): Promise<void> => {
    setSaving(true)
    try {
      await patchSettings({ worldMap: { calibration: next } } as any)
      setCalOpen(false)
      notify.success('Calibration saved')
    } catch (err) {
      notify.error('Calibration save failed', { message: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }
  const onCalibrationCleared = async (): Promise<void> => {
    setSaving(true)
    try {
      await patchSettings({ worldMap: { calibration: null } } as any)
      trailBufRef.current = []
      rebuildHeatmap([], heatmapFieldRef.current, heatmapPolysRef.current)
      notify.info('Calibration cleared')
    } catch (err) {
      notify.error('Failed to clear calibration', { message: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={cx(WRAP, `tier-${tier}`, mode3D && 'mode-3d', replayMeta && 'mode-replay')}>
      <div className={HOST} ref={hostRef} />

      {replayMeta && tier !== 'compact' && (
        <div className={REPLAY_BADGE} title={`Replaying session ${replayMeta.sessionId}`}>
          <span className={REPLAY_DOT} />
          <span className={REPLAY_LABEL}>REPLAY</span>
          {replayMeta.name
            ? <span className={REPLAY_NAME}>{replayMeta.name}</span>
            : <span className={REPLAY_NAME} style={{ fontFamily: 'var(--f-mono)' }}>
                {replayMeta.sessionId.slice(0, 18)}
              </span>}
          <span className={REPLAY_COUNT}>{replayMeta.count.toLocaleString()} pts</span>
        </div>
      )}

      {tier === 'hero' && (
        <div className={OVERLAY} ref={overlayRef}>
          <div className={OVERLAY_ROW}>
            <span className={cx(OVERLAY_LBL_BASE, OVERLAY_LBL_HERO)}>SPEED</span>
            <span className={cx(OVERLAY_VAL_BASE, OVERLAY_VAL_HERO)} data-slot="speed">—</span>
          </div>
          <div className={OVERLAY_ROW}>
            <span className={cx(OVERLAY_LBL_BASE, OVERLAY_LBL_HERO)}>HEADING</span>
            <span className={cx(OVERLAY_VAL_BASE, OVERLAY_VAL_HERO)} data-slot="heading">—</span>
          </div>
        </div>
      )}

      {!cal && !calOpen && tier !== 'compact' && (
        <div className={EMPTY}>
          <div className={EMPTY_TITLE}>CALIBRATE</div>
          <div className={EMPTY_BODY}>
            Two reference points map world position to map pixels.
            Drive to a distinctive landmark to start.
          </div>
          <button className="btn primary small" onClick={() => setCalOpen(true)}>
            Begin calibration
          </button>
        </div>
      )}

      {!cal && tier === 'compact' && (
        <div className={cx(EMPTY, EMPTY_COMPACT)}>
          <button className="btn small" onClick={() => setCalOpen(true)}>
            Calibrate
          </button>
        </div>
      )}

      {tier !== 'compact' && cal && (
        <div className={TOOLBAR}>
          <button
            className={cx(ICON_BTN_BASE, mode3D && ICON_BTN_ON)}
            onClick={() => setMode3D(!mode3D)}
            title={mode3D ? 'Back to top-down' : '3D follow-cam'}
          >
            3D
          </button>
          <button
            className={ICON_BTN_BASE}
            onClick={() => {
              if (mode3DRef.current) setMode3D(false)
              setCalOpen(true)
            }}
            title="Recalibrate"
          >
            ◎
          </button>
          <button
            className={ICON_BTN_BASE}
            onClick={clearTrail}
            title="Clear trail"
          >
            ⊘
          </button>
        </div>
      )}

      {tier !== 'compact' && cal && (
        <div className={ZOOM}>
          <button
            className={ZOOM_BTN}
            onClick={() => mapRef.current?.zoomIn()}
            title="Zoom in"
            aria-label="Zoom in"
          >
            +
          </button>
          <button
            className={ZOOM_BTN}
            onClick={() => mapRef.current?.zoomOut()}
            title="Zoom out"
            aria-label="Zoom out"
          >
            −
          </button>
        </div>
      )}

      {tier !== 'compact' && tier !== 'standard' && cal && (
        <div className={HEATMAP}>
          <div className={HEATMAP_PICKER}>
            {HEATMAP_LAYERS
              .filter((l) => !replayMeta || REPLAY_FIELDS.has(l.id))
              .map((l) => (
                <button
                  key={l.id}
                  className={cx(HEATMAP_BTN_BASE, tier === 'hero' && HEATMAP_BTN_HERO, heatmapField === l.id && HEATMAP_BTN_ON)}
                  onClick={() => setHeatmapField(l.id)}
                  title={l.label}
                >
                  {l.short}
                </button>
              ))}
          </div>
          <div className={HEATMAP_LEGEND}>
            <div className={HEATMAP_BAR} />
            <div className={cx(HEATMAP_RANGE_BASE, tier === 'hero' && HEATMAP_RANGE_HERO)}>
              <span>LOW</span>
              <span>{HEATMAP_BY_ID[heatmapField].label}</span>
              <span>
                {Math.round(HEATMAP_BY_ID[heatmapField].max)}
                {HEATMAP_BY_ID[heatmapField].units
                  ? ` ${HEATMAP_BY_ID[heatmapField].units}`
                  : ''}
              </span>
            </div>
          </div>
        </div>
      )}

      {calOpen && (
        <CalibrationPanel
          map={mapRef.current}
          initial={cal}
          saving={saving}
          onCancel={() => setCalOpen(false)}
          onSave={onCalibrationSaved}
          onClear={onCalibrationCleared}
          tier={tier}
        />
      )}

      {tier !== 'compact' && !following && (
        <button
          className={RECENTRE}
          onClick={() => {
            setFollowing(true)
            const m = markerRef.current
            if (m && mapRef.current) mapRef.current.setView(m.getLatLng())
          }}
        >
          Re-centre
        </button>
      )}
    </div>
  )
}

function rebuildHeatmap(buf: TrailSample[] | null, fieldId: HeatmapId, polys: LeafletPoly[] | null): void {
  if (!polys || polys.length !== BUCKET_COLORS.length) return
  if (!buf || buf.length < 2) {
    for (const p of polys) p.setLatLngs([])
    return
  }
  const layer = HEATMAP_BY_ID[fieldId] || HEATMAP_BY_ID.v
  const max   = layer.max
  const segs: Array<Array<[[number, number], [number, number]]>> = BUCKET_COLORS.map(() => [])
  for (let i = 1; i < buf.length; i++) {
    const p0 = buf[i - 1]!
    const p1 = buf[i]!
    const v0 = p0[fieldId] ?? 0
    const v1 = p1[fieldId] ?? 0
    const t  = Math.min(((v0 + v1) * 0.5) / max, 1)
    const b  = bucketIndex(t)
    segs[b]!.push([p0.ll, p1.ll])
  }
  for (let i = 0; i < polys.length; i++) polys[i].setLatLngs(segs[i])
}

interface PredictRefs {
  brakeLine:   LeafletPoly | null
  brakeMark:   any
  predictLine: LeafletPoly | null
  carLL:       any
}

function updatePredictions(map: LeafletMap, t: PixelTransform, frame: Frame, { brakeLine, brakeMark, predictLine, carLL }: PredictRefs): void {
  const motion: MotionBlock | undefined = frame?.motion
  const speed  = motion?.speed_mps ?? 0
  if (!motion || speed < MIN_SPEED_MPS) {
    predictLine?.setLatLngs([])
    brakeLine?.setLatLngs([])
    if (brakeMark) brakeMark.setRadius(0)
    return
  }

  const path = predictPath(motion, { horizonS: PREDICT_HORIZON_S })
  if (path.length >= 2 && predictLine) {
    const pts = new Array(path.length)
    pts[0] = carLL
    for (let i = 1; i < path.length; i++) {
      const [wx, wz] = path[i]!
      const [pxp, pyp] = worldToPix(t, wx, wz)
      pts[i] = map.unproject(L.point(pxp, pyp), MAP_CONFIG.maxZoom)
    }
    predictLine.setLatLngs(pts)
  } else {
    predictLine?.setLatLngs([])
  }

  let stopM = frame.derived?.stopDistance_m
  if (stopM == null) stopM = clientFallbackStopDistance(motion)
  if (stopM > 0) {
    const end = projectAlongMotion(motion, stopM)
    if (end && brakeLine && brakeMark) {
      const [epx, epy] = worldToPix(t, end[0], end[1])
      const endLL = map.unproject(L.point(epx, epy), MAP_CONFIG.maxZoom)
      brakeLine.setLatLngs([carLL, endLL])
      brakeMark.setLatLng(endLL)
      brakeMark.setRadius(Math.min(14, 6 + stopM * 0.04))
    }
  } else {
    brakeLine?.setLatLngs([])
    brakeMark?.setRadius(0)
  }
}

function clientFallbackStopDistance(motion: MotionBlock | null | undefined): number {
  const speed = motion?.speed_mps ?? 0
  if (speed < 1.0) return 0
  const vx = motion?.velocity?.x ?? 0
  const vz = motion?.velocity?.z ?? 0
  const ax = motion?.acceleration?.x ?? 0
  const az = motion?.acceleration?.z ?? 0
  const sp = Math.hypot(vx, vz)
  if (sp < 1.0) return 0
  const decel = -(ax * vx + az * vz) / sp
  if (decel < 0.5) return 0
  return (speed * speed) / (2.0 * decel)
}

function makeArrowIcon(initialDeg: number, tier: 'compact' | 'standard' | 'hero'): any {
  const sz = tier === 'compact' ? 28 : tier === 'standard' ? 36 : 44
  const html =
    `<div class="world-map-arrow-wrap" style="transform: rotate(${initialDeg}deg)">` +
      `<svg width="${sz}" height="${sz}" viewBox="0 0 24 24">` +
        `<defs>` +
          `<radialGradient id="warrow-fill" cx="50%" cy="35%" r="65%">` +
            `<stop offset="0%" stop-color="#fff7f0"/>` +
            `<stop offset="100%" stop-color="#ff5ea7"/>` +
          `</radialGradient>` +
        `</defs>` +
        `<path d="M12 2 L19 21 L12 16 L5 21 Z" ` +
          `fill="url(#warrow-fill)" ` +
          `stroke="#fff7f0" stroke-width="1.2" stroke-linejoin="round"/>` +
      `</svg>` +
    `</div>`
  return L.divIcon({
    className: 'world-map-arrow',
    html,
    iconSize:   [sz, sz],
    iconAnchor: [sz / 2, sz / 2],
  })
}

function writeOverlay(root: HTMLElement | null, frame: Frame | null, pos: unknown, tier: 'compact' | 'standard' | 'hero'): void {
  if (!root || tier !== 'hero') return
  const speedEl   = root.querySelector('[data-slot="speed"]')
  const headingEl = root.querySelector('[data-slot="heading"]')
  if (!frame || !pos) {
    if (speedEl)   speedEl.textContent   = '—'
    if (headingEl) headingEl.textContent = '—'
    return
  }
  const kmh = (frame.motion?.speed_mps ?? 0) * 3.6
  const deg = (((frame.motion?.orientation?.yaw ?? 0) * 180) / Math.PI + 360) % 360
  if (speedEl)   speedEl.textContent   = `${Math.round(kmh)} km/h`
  if (headingEl) headingEl.textContent = `${Math.round(deg)}°`
}

interface CalibrationPanelProps {
  map: LeafletMap | null
  initial: Calibration | null
  saving: boolean
  onCancel: () => void
  onSave: (next: Calibration) => void
  onClear: () => void
  tier: 'compact' | 'standard' | 'hero'
}

function CalibrationPanel({ map, initial, saving, onCancel, onSave, onClear, tier }: CalibrationPanelProps) {
  const [draft, setDraft] = useState<Partial<Calibration>>(() => {
    const d: Partial<Calibration> = {}
    if (initial?.aWorld) d.aWorld = initial.aWorld
    if (initial?.aPix)   d.aPix   = initial.aPix
    if (initial?.bWorld) d.bWorld = initial.bWorld
    if (initial?.bPix)   d.bPix   = initial.bPix
    return d
  })
  const [activeSlot, setActiveSlot] = useState<'a' | 'b' | null>(null)

  useEffect(() => {
    if (!map || !activeSlot) return
    const handler = (e: any): void => {
      const p = map.project(e.latlng, MAP_CONFIG.maxZoom)
      setDraft((d) => ({
        ...d,
        [activeSlot === 'a' ? 'aPix' : 'bPix']: [p.x, p.y],
      }))
      setActiveSlot(null)
    }
    map.on('click', handler)
    return () => { map.off('click', handler) }
  }, [map, activeSlot])

  const captureWorld = (slot: 'a' | 'b'): void => {
    const frame = liveClient.getLatestFrame()
    const pos = frame?.motion?.position
    if (!pos) return
    setDraft((d) => ({
      ...d,
      [slot === 'a' ? 'aWorld' : 'bWorld']: [pos.x, pos.z],
    }))
  }

  const ready = !!(
    draft.aWorld && draft.aPix && draft.bWorld && draft.bPix &&
    (draft.aWorld[0] !== draft.bWorld[0] || draft.aWorld[1] !== draft.bWorld[1])
  )

  return (
    <div className={CAL}>
      <div className={CAL_HEAD}>
        <div className="flex items-center gap-2 whitespace-nowrap font-display text-[10px] font-medium uppercase tracking-[0.2em] text-bubblegum [text-shadow:0_0_8px_rgba(255,193,220,0.4)]">
          <span className="w-[7px] h-[7px] rounded-full bg-pink shadow-[0_0_8px_var(--pink)] animate-[pulse_1.6s_ease-in-out_infinite]" />
          CALIBRATE
        </div>
        <button className="btn ghost small" onClick={onCancel}>Close</button>
      </div>

      <div className={cx(CAL_BODY_BASE, tier === 'compact' && CAL_BODY_COMPACT)}>
        <CalibrationSlot
          label="POINT A"
          world={draft.aWorld ?? null}
          pix={draft.aPix ?? null}
          active={activeSlot === 'a'}
          onCaptureWorld={() => captureWorld('a')}
          onStartPix={() => setActiveSlot('a')}
        />
        <CalibrationSlot
          label="POINT B"
          world={draft.bWorld ?? null}
          pix={draft.bPix ?? null}
          active={activeSlot === 'b'}
          onCaptureWorld={() => captureWorld('b')}
          onStartPix={() => setActiveSlot('b')}
        />
      </div>

      <div className={CAL_FOOT}>
        {initial && (
          <button
            className="btn danger small"
            disabled={saving}
            onClick={onClear}
          >
            Clear
          </button>
        )}
        <div className={CAL_SPACER} />
        <button
          className="btn ghost small"
          disabled={saving}
          onClick={onCancel}
        >Cancel</button>
        <button
          className="btn primary small"
          disabled={!ready || saving}
          onClick={() => onSave(draft as Calibration)}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

interface CalibrationSlotProps {
  label: string
  world: [number, number] | null
  pix:   [number, number] | null
  active: boolean
  onCaptureWorld: () => void
  onStartPix: () => void
}

function CalibrationSlot({ label, world, pix, active, onCaptureWorld, onStartPix }: CalibrationSlotProps) {
  return (
    <div className={cx(CAL_SLOT_BASE, active && CAL_SLOT_ACTIVE)}>
      <div className={CAL_SLOT_LABEL}>{label}</div>
      <div className={CAL_SLOT_ROW}>
        <span className={CAL_SLOT_KEY}>World</span>
        <span className={CAL_SLOT_VAL}>
          {world
            ? `${world[0].toFixed(1)}, ${world[1].toFixed(1)}`
            : 'not captured'}
        </span>
        <button className="btn small" onClick={onCaptureWorld}>
          Capture
        </button>
      </div>
      <div className={CAL_SLOT_ROW}>
        <span className={CAL_SLOT_KEY}>Pixel</span>
        <span className={CAL_SLOT_VAL}>
          {pix
            ? `${Math.round(pix[0])}, ${Math.round(pix[1])}`
            : active ? 'click the map…' : 'not captured'}
        </span>
        <button
          className={`btn small${active ? ' primary' : ''}`}
          onClick={onStartPix}
        >
          {active ? 'Click map' : 'Pick'}
        </button>
      </div>
    </div>
  )
}
