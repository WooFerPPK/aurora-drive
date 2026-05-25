// client/src/lib/widgetPrimitives/drawTire.ts
import { C, valueColour, toRgb, toRgba, PINK_RGB } from '@/shared/lib/canvasUtils'

export interface DrawTireOpts {
  cx: number
  cy: number
  r: number                  // outer radius
  temp: number               // 0..1 — thermal ramp
  slip?: number              // 0..1
  wear?: number              // 0..1
  label?: string
  locked?: boolean
  elapsed?: number
  treadCount?: number
}

const TWO_PI = Math.PI * 2

export function drawTire(ctx: CanvasRenderingContext2D, opts: DrawTireOpts): void {
  const { cx, cy, r, temp, slip = 0, wear = 0, label, locked = false, elapsed = 0, treadCount = 12 } = opts
  const tc = valueColour(Math.max(0, Math.min(1, temp)), 'thermal')

  // Slip motion lines (rearward, drawn first so the tire reads on top)
  if (slip > 0.1) {
    ctx.save()
    ctx.translate(cx, cy)
    const rotation = (elapsed * 1.5) % TWO_PI
    ctx.lineCap = 'round'
    ctx.lineWidth = 1.5
    ctx.strokeStyle = toRgba(PINK_RGB, slip * 0.7)
    for (let i = 0; i < 8; i++) {
      const a = rotation + i * (Math.PI / 4)
      const x1 = (r + 6) * Math.cos(a), y1 = (r + 6) * Math.sin(a)
      const len = 8 + slip * 18
      const x2 = (r + 6 + len) * Math.cos(a), y2 = (r + 6 + len) * Math.sin(a)
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
    }
    ctx.lineCap = 'butt'
    ctx.restore()
  }

  // Lockup pulse ring (pink, fades in/out via elapsed)
  if (locked) {
    const pulse = 0.55 + 0.45 * Math.sin(elapsed * 8)
    ctx.strokeStyle = toRgba(PINK_RGB, pulse)
    ctx.lineWidth = 2.4
    ctx.shadowColor = toRgb(PINK_RGB); ctx.shadowBlur = 14 * pulse
    ctx.beginPath(); ctx.arc(cx, cy, r + 4, 0, TWO_PI); ctx.stroke()
    ctx.shadowBlur = 0
  }

  // Sidewall (dark disc)
  ctx.fillStyle = '#0a0314'
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, TWO_PI); ctx.fill()

  // Outer ring (temp colour + glow)
  ctx.strokeStyle = toRgb(tc)
  ctx.shadowColor = toRgb(tc); ctx.shadowBlur = 14
  ctx.lineWidth = r * 0.10
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.95, 0, TWO_PI); ctx.stroke()
  ctx.shadowBlur = 0

  // Inner radial temp gradient
  const ig = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.85)
  ig.addColorStop(0, toRgba(tc, 0.30))
  ig.addColorStop(1, toRgba(tc, 0.10))
  ctx.fillStyle = ig
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.85, 0, TWO_PI); ctx.fill()

  // Tread blocks — radial slits eroding with wear
  const treadInnerR = r * 0.55
  const treadOuterR = r * 0.85
  const treadDepth = (1 - wear) * (treadOuterR - treadInnerR)
  ctx.strokeStyle = `rgba(0,0,0,${0.5 + wear * 0.3})`
  ctx.lineWidth = 1.5
  // treadInnerR is reserved for future use (currently the tread starts from
  // (treadOuterR - depth) outward; keeping the constant documents intent).
  void treadInnerR
  for (let i = 0; i < treadCount; i++) {
    const a = (i / treadCount) * TWO_PI
    const cosA = Math.cos(a), sinA = Math.sin(a)
    const r1 = treadOuterR - treadDepth
    const r2 = treadOuterR
    ctx.beginPath()
    ctx.moveTo(cx + r1 * cosA, cy + r1 * sinA)
    ctx.lineTo(cx + r2 * cosA, cy + r2 * sinA)
    ctx.stroke()
  }

  // Centre hub
  ctx.fillStyle = C.cream
  ctx.beginPath(); ctx.arc(cx, cy, r * 0.18, 0, TWO_PI); ctx.fill()

  // Hub label
  if (label) {
    ctx.font = `700 ${r * 0.36}px "Unbounded", system-ui, sans-serif`
    ctx.fillStyle = '#0d0520'
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(label, cx, cy)
  }
}
