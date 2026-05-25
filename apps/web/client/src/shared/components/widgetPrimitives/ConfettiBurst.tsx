// client/src/lib/widgetPrimitives/ConfettiBurst.tsx
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

// <ConfettiBurst ref={confettiRef} colour="butter" />
//
// Imperative-only particle burst. Widgets call confettiRef.current.fire()
// from inside their frame loop when a PB / position-improvement event
// happens. Self-renders an absolutely-positioned canvas inside the wrap;
// runs its own rAF loop only while particles are alive (sleeps otherwise).

export type ConfettiColour = 'butter' | 'mint' | 'pink' | 'lilac'

export interface ConfettiBurstProps {
  colour?: ConfettiColour
  particleCount?: number
}

export interface ConfettiBurstHandle {
  fire: () => void
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  rot: number
  vrot: number
  life: number
  ttl: number
  col: string
}

const COLOURS: Record<ConfettiColour, string[]> = {
  butter: ['255,224,130', '255,193,220', '255,247,240'],
  mint:   ['168,243,208', '184,212,255', '255,247,240'],
  pink:   ['255,94,167',  '255,193,220', '202,166,255'],
  lilac:  ['202,166,255', '184,212,255', '255,247,240'],
}

const ConfettiBurst = forwardRef<ConfettiBurstHandle, ConfettiBurstProps>(function ConfettiBurst({ colour = 'butter', particleCount = 36 }, ref) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const rafRef = useRef(0)
  const palette = COLOURS[colour] ?? COLOURS.butter

  useImperativeHandle(ref, () => ({
    fire(): void {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const w = rect.width, h = rect.height
      // Spawn from the centre, spread outward + downward (gravity-ish)
      for (let i = 0; i < particleCount; i++) {
        const a = (Math.random() * 0.8 - 0.4) - Math.PI / 2   // upward cone
        const sp = 120 + Math.random() * 180
        particlesRef.current.push({
          x: w / 2 + (Math.random() - 0.5) * w * 0.1,
          y: h * 0.55,
          vx: Math.cos(a) * sp,
          vy: Math.sin(a) * sp,
          rot: Math.random() * Math.PI * 2,
          vrot: (Math.random() - 0.5) * 8,
          life: 0,
          ttl: 1.2 + Math.random() * 0.6,
          col: palette[i % palette.length]!,
        })
      }
      ensureRunning()
    },
  }), [particleCount, palette])

  // Setup canvas DPR scaling
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1
    const resize = (): void => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = Math.round(rect.width * dpr)
      canvas.height = Math.round(rect.height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(canvas)
    return () => { ro.disconnect(); cancelAnimationFrame(rafRef.current) }
  }, [])

  function ensureRunning(): void {
    if (rafRef.current) return
    let last = performance.now()
    const tick = (now: number): void => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const canvas = canvasRef.current
      if (!canvas) { rafRef.current = 0; return }
      const ctx = canvas.getContext('2d')
      if (!ctx) { rafRef.current = 0; return }
      const rect = canvas.getBoundingClientRect()
      const w = rect.width, h = rect.height
      ctx.clearRect(0, 0, w, h)

      const ps = particlesRef.current
      let alive = 0
      for (let i = 0; i < ps.length; i++) {
        const p = ps[i]!
        if (p.life >= p.ttl) continue
        p.life += dt
        p.vy += 320 * dt  // gravity
        p.x += p.vx * dt
        p.y += p.vy * dt
        p.rot += p.vrot * dt
        const a = Math.max(0, 1 - p.life / p.ttl)
        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(p.rot)
        ctx.fillStyle = `rgba(${p.col},${a})`
        ctx.fillRect(-3, -6, 6, 12)
        ctx.restore()
        alive++
      }

      // Compact the pool every so often when more than half is dead
      if (ps.length > 100 && alive < ps.length / 2) {
        particlesRef.current = ps.filter((p) => p.life < p.ttl)
      }

      if (alive > 0) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        particlesRef.current = []
        rafRef.current = 0
      }
    }
    rafRef.current = requestAnimationFrame(tick)
  }

  return <canvas ref={canvasRef} className="confetti-burst" aria-hidden />
})

export default ConfettiBurst
