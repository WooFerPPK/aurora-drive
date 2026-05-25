// client/src/lib/canvasUtils.ts
// Shared canvas drawing utilities for Aurora Drive widgets.
// All canvas widgets import from here — do not duplicate these locally.

// ── Palette ───────────────────────────────────────────────────────────────
export const C = {
  bg0:        '#0d0520',
  bg1:        '#1e0830',
  pink:       '#ff5ea7',
  pinkSoft:   'rgba(255,94,167,0.55)',
  mint:       '#a8f3d0',
  mintSoft:   'rgba(168,243,208,0.5)',
  butter:     '#ffe082',
  butterSoft: 'rgba(255,224,130,0.5)',
  lilac:      '#caa6ff',
  lilacSoft:  'rgba(202,166,255,0.4)',
  bubblegum:  '#ffc1dc',
  cream:      '#fff7f0',
  track:      'rgba(255,193,220,0.08)',
  trackTick:  'rgba(255,193,220,0.18)',
  inkFaint:   'rgba(253,233,255,0.42)',
  inkDim:     'rgba(253,233,255,0.18)',
} as const

export type Rgb = [number, number, number]

// ── Colour math ───────────────────────────────────────────────────────────
export const MINT_RGB:   Rgb = [168, 243, 208]
export const BUTTER_RGB: Rgb = [255, 224, 130]
export const PINK_RGB:   Rgb = [255,  94, 167]
export const COLD_RGB:   Rgb = [ 95, 190, 255]

export function lerpRGB([r1, g1, b1]: Rgb, [r2, g2, b2]: Rgb, t: number): Rgb {
  return [r1 + (r2 - r1) * t | 0, g1 + (g2 - g1) * t | 0, b1 + (b2 - b1) * t | 0]
}

export type ColourRamp = 'intensity' | 'thermal'

// valueColour(v, ramp = 'intensity')
//   'intensity'  mint → butter → pink. For: throttle, slip, G, speed, RPM, etc.
//   'thermal'    cold-blue → mint → butter → pink. For: tire temp, brake temp.
//
// Old call signature `valueColour(v)` continues to work — defaults to 'intensity'.
export function valueColour(v: number, ramp: ColourRamp = 'intensity'): Rgb {
  const u = Math.max(0, Math.min(1, v))
  if (ramp === 'thermal') {
    if (u < 0.25) return lerpRGB(COLD_RGB,   MINT_RGB,   u / 0.25)
    if (u < 0.55) return lerpRGB(MINT_RGB,   BUTTER_RGB, (u - 0.25) / 0.30)
    return                lerpRGB(BUTTER_RGB, PINK_RGB,   (u - 0.55) / 0.45)
  }
  // 'intensity' (default)
  return u < 0.5
    ? lerpRGB(MINT_RGB,   BUTTER_RGB, u / 0.5)
    : lerpRGB(BUTTER_RGB, PINK_RGB,   (u - 0.5) / 0.5)
}

export function toRgb([r, g, b]: Rgb): string     { return `rgb(${r},${g},${b})` }
export function toRgba([r, g, b]: Rgb, a: number): string { return `rgba(${r},${g},${b},${a})` }

// ── Animation helpers ─────────────────────────────────────────────────────
export function ease(cur: number, tgt: number, dt: number, k: number = 6): number {
  return cur + (tgt - cur) * Math.min(1, dt * k)
}

// ── Path helpers ──────────────────────────────────────────────────────────
export function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y,     x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x,     y + h, r)
  ctx.arcTo(x,     y + h, x,     y,     r)
  ctx.arcTo(x,     y,     x + w, y,     r)
  ctx.closePath()
}

// ── Background ────────────────────────────────────────────────────────────
// Canvas widgets are transparent — the card shell provides the background.
// Just clear what was drawn last frame.
export function drawWidgetBg(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  ctx.clearRect(0, 0, w, h)
}

// ── Ambient bloom ─────────────────────────────────────────────────────────
// Radial glow behind the focal point, colour-matched to current value.
// Draw AFTER background, BEFORE the arc track.
// The old hard-coded alpha was 0.16. The new formula is 0.08 + value² × 0.22,
// so alpha varies with intensity. Pass `value` ∈ [0, 1].
// Back-compat: if value is undefined, defaults to 0.6 — chosen so that
// existing 7-arg callers (which don't pass value) produce alpha ≈ 0.16 and
// match the old visual brightness.
export function drawAmbientBloom(
  ctx: CanvasRenderingContext2D,
  w: number, h: number,
  cx: number, cy: number, r: number,
  colRgb: Rgb,
  value?: number,
): void {
  const v = typeof value === 'number' ? Math.max(0, Math.min(1, value)) : 0.6
  const alpha = 0.08 + v * v * 0.22
  const bloom = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 1.5)
  bloom.addColorStop(0, toRgba(colRgb, alpha))
  bloom.addColorStop(1, 'transparent')
  ctx.fillStyle = bloom
  ctx.fillRect(0, 0, w, h)
}

// ── Radial gauge arc ──────────────────────────────────────────────────────
// Draws track + conic-gradient fill arc for all radial gauges.
// startRad / sweepRad in radians; v in [0,1].
export function drawGaugeArc(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, r: number,
  startRad: number, sweepRad: number,
  v: number, lw: number, glowBlur: number,
): void {
  const col = valueColour(v)
  ctx.lineCap   = 'round'
  ctx.lineWidth = lw

  // Track
  ctx.strokeStyle = C.track
  ctx.beginPath()
  ctx.arc(cx, cy, r, startRad, startRad + sweepRad)
  ctx.stroke()

  // Filled arc — conic gradient if supported, solid fallback
  const maybeConic = (ctx as unknown as { createConicGradient?: (startAngle: number, x: number, y: number) => CanvasGradient }).createConicGradient
  if (typeof maybeConic === 'function') {
    const cg = maybeConic.call(ctx, startRad, cx, cy)
    cg.addColorStop(0,    C.mint)
    cg.addColorStop(0.38, C.butter)
    cg.addColorStop(0.74, C.pink)
    cg.addColorStop(1,    C.pink)
    ctx.strokeStyle = cg
  } else {
    ctx.strokeStyle = toRgb(col)
  }
  ctx.shadowColor = toRgb(col)
  ctx.shadowBlur  = glowBlur
  ctx.beginPath()
  ctx.arc(cx, cy, r, startRad, startRad + sweepRad * Math.min(1, v))
  ctx.stroke()
  ctx.shadowBlur = 0
}

export type TickTier = 'compact' | 'standard' | 'hero'

// ── Tick marks ────────────────────────────────────────────────────────────
// tier 'compact' → nothing; 'standard' → major+minor; 'hero' → +micro+labels.
// valueMax is used to compute label text (e.g. 350 for km/h, 8 for k-RPM).
export function drawTicks(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, r: number,
  startRad: number, sweepRad: number,
  tier: TickTier, valueMax: number = 100,
): void {
  if (tier === 'compact') return
  const n = tier === 'hero' ? 20 : 10
  for (let i = 0; i <= n; i++) {
    const a       = startRad + (i / n) * sweepRad
    const isMaj   = i % (n / 4) === 0
    const isMicro = tier === 'hero' && !isMaj && i % 2 !== 0
    const len     = isMaj ? 9 : isMicro ? 3 : 5
    ctx.strokeStyle = isMaj   ? 'rgba(253,233,255,0.35)'
                    : isMicro ? 'rgba(253,233,255,0.07)'
                    :           'rgba(253,233,255,0.10)'
    ctx.lineWidth = isMaj ? 1.2 : 0.7
    ctx.lineCap   = 'butt'
    ctx.beginPath()
    ctx.moveTo(cx + (r + 4) * Math.cos(a),         cy + (r + 4) * Math.sin(a))
    ctx.lineTo(cx + (r + 4 + len) * Math.cos(a),   cy + (r + 4 + len) * Math.sin(a))
    ctx.stroke()
    if (isMaj && i > 0 && i < n) {
      ctx.font         = `400 7px "JetBrains Mono", monospace`
      ctx.fillStyle    = C.inkDim
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(
        String(Math.round((i / n) * valueMax)),
        cx + (r + 20) * Math.cos(a),
        cy + (r + 20) * Math.sin(a),
      )
    }
  }
}

export interface SparkOpts {
  count?: number
  innerR?: number
  outerR?: number
  lineWidth?: number
  rotation?: number
}

// ── Threshold sparks ──────────────────────────────────────────────────────
// Renders a short burst of radial particle streaks emanating from (cx, cy).
// `intensity` ∈ [0, 1] (use the value returned by useThresholdFlash). At 0,
// nothing draws. Colour follows the active ramp.
// opts: { count, innerR, outerR, lineWidth, rotation }
//   rotation — offset angle in radians applied to the whole burst (default 0).
//
// Call this AFTER the main element you're highlighting (so sparks read on top).
export function drawSparks(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  intensity: number,
  colRgb: Rgb,
  opts: SparkOpts = {},
): void {
  if (intensity <= 0) return
  const n = opts.count ?? 12
  const innerR = opts.innerR ?? 14
  const outerR = (opts.outerR ?? 38) * (0.5 + 0.5 * intensity)
  const lineWidth = opts.lineWidth ?? 1.5
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineWidth = lineWidth
  ctx.strokeStyle = toRgba(colRgb, 0.85 * intensity)
  ctx.shadowColor = toRgb(colRgb)
  ctx.shadowBlur  = 10 * intensity
  for (let i = 0; i < n; i++) {
    const a  = (i / n) * Math.PI * 2 + (opts.rotation ?? 0)
    const r0 = innerR + (outerR - innerR) * (0.3 + 0.7 * (((i * 0x9E3779B1) >>> 0) / 0x100000000)) // Knuth hash, no period
    ctx.beginPath()
    ctx.moveTo(cx + r0 * Math.cos(a), cy + r0 * Math.sin(a))
    ctx.lineTo(cx + outerR * Math.cos(a), cy + outerR * Math.sin(a))
    ctx.stroke()
  }
  ctx.restore()
}
