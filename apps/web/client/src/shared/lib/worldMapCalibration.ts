// World-map tile config, Leaflet CRS override, and coord math.
//
// Calibration itself lives on the backend under `settings.worldMap.calibration`
// (see api-contract.md §10). The widget reads it through SettingsContext and
// persists changes through `PATCH /api/settings`; this module is just the
// pure functions that turn a calibration into pixels.

// Tile pyramid config. Tiles live under `client/public/maptiles/`; Vite
// publishes them to `/maptiles/{z}/{y}/{x}.jpg` same-origin after build.
// The bundled pyramid is fh6-tel's FH6 Japan preset — replace it with a
// real FH6 map raster when one's available and recalibrate via the
// widget's in-place calibration tool.
export const MAP_CONFIG = {
  tileUrl:        '/maptiles/{z}/{y}/{x}.jpg',
  tileSize:       256,
  minZoom:        9,
  maxZoom:        14,    // deepest tile level on disk
  // Allow zooming past native; Leaflet upscales the tiles. Looks slightly
  // blurry at the extreme but the marker reads at a glance.
  viewMaxZoom:    17,
  // Open zoomed-in by default so the car is centred at a useful scale
  // rather than swimming in a town-block-wide viewport.
  defaultZoom:    16,
  defaultCenter:  [(8128 * 256 + 8192 * 256) / 2, (8128 * 256 + 8192 * 256) / 2] as [number, number],
} as const

export interface Calibration {
  aWorld: [number, number]
  bWorld: [number, number]
  aPix:   [number, number]
  bPix:   [number, number]
}

export interface PixelTransform {
  mX: number
  mZ: number
  bX: number
  bY: number
}

// Override Leaflet's CRS.Simple Y-flip so XYZ tile rows are requested in
// the top-left-origin order that gdal2tiles writes.
// `L` is the Leaflet module object — typed as `any` because Leaflet
// ships no types in this repo's dep set (no @types/leaflet installed)
// and pulling it in just for this one helper is overkill.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function xyzSimpleCRS(L: any): unknown {
  return L.Util.extend({}, L.CRS.Simple, {
    transformation: new L.Transformation(1, 0, 1, 0),
  })
}

// Per-axis linear fit from two reference points. A single rotation/scale
// can't represent the Z-axis reflection an overhead game map needs (world
// Z grows north, pixel Y grows south); per-axis slopes carry their own
// sign and stay correct.
export function computeTransform(cal: Calibration | null | undefined): PixelTransform | null {
  if (!cal) return null
  const dWX = cal.bWorld[0] - cal.aWorld[0]
  const dWZ = cal.bWorld[1] - cal.aWorld[1]
  if (Math.abs(dWX) < 1e-6 || Math.abs(dWZ) < 1e-6) return null
  const mX = (cal.bPix[0] - cal.aPix[0]) / dWX
  const mZ = (cal.bPix[1] - cal.aPix[1]) / dWZ
  return {
    mX, mZ,
    bX: cal.aPix[0] - mX * cal.aWorld[0],
    bY: cal.aPix[1] - mZ * cal.aWorld[1],
  }
}

export function worldToPix(t: PixelTransform, worldX: number, worldZ: number): [number, number] {
  return [t.mX * worldX + t.bX, t.mZ * worldZ + t.bY]
}
