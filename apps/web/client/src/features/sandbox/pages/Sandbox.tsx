// client/src/pages/Sandbox.tsx
import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { WIDGETS, ROW_HEIGHT_PX, GRID_GAP_PX } from '@/features/dashboard/widgetRegistry'
import { liveClient, getCoachClient } from '@/shared/lib/wsClient'
import { buildFrame } from '@/features/sandbox/lib/frameBuilder'
import { getConfig } from '@/features/sandbox/lib/widgetConfigs'
import Select from '@/shared/components/primitives/Select'
import { SessionCtx } from '@/features/sessions/context/SessionContext'
import { setApiMocks } from '@/shared/lib/api'

const CELL_W = 80
const CELL_H = ROW_HEIGHT_PX

/* eslint-disable @typescript-eslint/no-explicit-any */

interface CfgField {
  path: string
  label: string
  min: number
  max: number
  step: number
  default: number
}
interface CfgEmit {
  channel: 'live' | 'coach'
  type: string
  payload: any
}
interface Cfg {
  fields?: CfgField[]
  defaults?: Record<string, unknown>
  presets?: Record<string, Record<string, number>>
  notes?: string
  apiMocks?: Record<string, (values: Record<string, unknown>, ...args: any[]) => unknown>
  wsEmit?: (values: Record<string, unknown>) => CfgEmit[] | undefined
}

declare global {
  interface Window {
    __sandbox?: {
      setWidget: (kind: string) => void
      setSize: (idx: number) => void
      setStale: (v: boolean) => void
      list: () => Array<{ kind: string; sizes: { w: number; h: number; label: string }[] }>
      getState: () => { selectedKind: string; sizeIdx: number; stale: boolean }
    }
  }
}

export default function Sandbox() {
  const [selectedKind, setSelectedKind] = useState<string>(WIDGETS[0]!.kind)
  const [sizeIdx, setSizeIdx] = useState<number>(WIDGETS[0]!.defaultSize ?? 0)
  const [stale, setStale] = useState(false)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [animating, setAnimating] = useState<Record<string, boolean>>({})
  const [tick, setTick] = useState(0)

  const widget = useMemo(() => WIDGETS.find(w => w.kind === selectedKind), [selectedKind])
  const cfg = useMemo<Cfg>(() => getConfig(selectedKind) as Cfg, [selectedKind])

  if (import.meta.env.DEV) {
    window.__sandbox = {
      setWidget: (kind) => setSelectedKind(kind),
      setSize:   (idx)  => setSizeIdx(idx),
      setStale:  (v)    => setStale(v),
      list:      () => WIDGETS.map(w => ({ kind: w.kind, sizes: w.sizes })),
      getState:  () => ({ selectedKind, sizeIdx, stale }),
    }
  }

  useEffect(() => {
    const init: Record<string, unknown> = {}
    for (const f of cfg.fields ?? []) init[f.path] = f.default
    Object.assign(init, cfg.defaults ?? {})
    setValues(init)
    setAnimating({})
    setSizeIdx(widget?.defaultSize ?? 0)
  }, [selectedKind, cfg, widget])

  useEffect(() => {
    const hasAny = Object.values(animating).some(Boolean)
    if (!hasAny) return
    let raf = 0
    let last = performance.now()
    const loop = (now: number): void => {
      const dt = (now - last) / 1000
      last = now
      setTick(t => t + dt)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [animating])

  const effective = useMemo(() => {
    const out: Record<string, unknown> = { ...values }
    for (const f of cfg.fields ?? []) {
      if (animating[f.path]) {
        const phase = (Math.sin(tick * 0.6) + 1) / 2
        out[f.path] = f.min + phase * (f.max - f.min)
      }
    }
    return out
  }, [values, animating, tick, cfg])

  const effectiveRef = useRef<Record<string, unknown>>(effective)
  effectiveRef.current = effective

  {
    const builders = cfg.apiMocks
    if (builders) {
      const mocks: Record<string, (...args: any[]) => unknown> = {}
      for (const [methodName, builder] of Object.entries(builders)) {
        mocks[methodName] = (...args) => builder(effectiveRef.current, ...args)
      }
      setApiMocks(mocks as any)
    } else {
      setApiMocks(null)
    }
  }

  useEffect(() => () => setApiMocks(null), [])

  const mockRefreshKey = useMemo(() => {
    const entries = Object.entries(effective)
      .filter(([k]) => k.startsWith('mock.'))
      .sort()
    return JSON.stringify(entries)
  }, [effective])

  useEffect(() => {
    if (!cfg.wsEmit) return
    const emits = cfg.wsEmit(effectiveRef.current)
    if (!emits || !emits.length) return
    for (const e of emits) {
      if (e.channel === 'coach') (getCoachClient() as any).__emit(e.type, e.payload)
      else if (e.channel === 'live') (liveClient as any).__emit(e.type, e.payload)
    }
  }, [cfg, mockRefreshKey])

  const realSession = useContext(SessionCtx)
  const sandboxSession = useMemo(() => ({
    ...(realSession || {}),
    currentSession: { id: 'sandbox-session', name: 'Sandbox', startedAt: Date.now() / 1000 },
    cars: realSession?.cars ?? [],
  }), [realSession])

  useEffect(() => {
    liveClient.setFrameOverride({
      frame: () => buildFrame(effective) as any,
      ageMs: () => stale ? 5000 : 0,
    })
    return () => liveClient.setFrameOverride(null)
  }, [effective, stale])

  const sizes = widget?.sizes ?? []
  const size = sizes[sizeIdx] ?? sizes[0]
  const pxW = size ? size.w * CELL_W + (size.w - 1) * GRID_GAP_PX : 200
  const pxH = size ? size.h * CELL_H + (size.h - 1) * GRID_GAP_PX : 200

  const setField = (path: string, val: number): void => setValues(v => ({ ...v, [path]: val }))
  const toggleAnimate = (path: string): void => setAnimating(a => ({ ...a, [path]: !a[path] }))
  const applyPreset = (presetValues: Record<string, number>): void => setValues(v => ({ ...v, ...presetValues }))
  const resetDefaults = (): void => {
    const init: Record<string, unknown> = {}
    for (const f of cfg.fields ?? []) init[f.path] = f.default
    setValues(init)
    setAnimating({})
  }

  return (
    <div className="widget-sandbox">
      <div className="sb-topbar">
        <label className="sb-field">
          <span>Widget</span>
          <Select<string>
            value={selectedKind}
            onChange={setSelectedKind}
            options={WIDGETS.map(w => ({ value: w.kind, label: `${w.title} (${w.kind})` }))}
            ariaLabel="Widget"
            className="sb-widget-select"
          />
        </label>
        <div className="sb-size-group">
          <span className="sb-field-label">Size</span>
          {sizes.map((s, i) => (
            <button
              key={i}
              className={`sb-size-btn ${i === sizeIdx ? 'active' : ''}`}
              onClick={() => setSizeIdx(i)}
            >
              {s.label} ({s.w}×{s.h})
            </button>
          ))}
        </div>
        <label className="sb-stale">
          <input type="checkbox" checked={stale} onChange={(e) => setStale(e.target.checked)} />
          Stale frame
        </label>
      </div>

      <div className="sb-body">
        <aside className="sb-panel">
          {cfg.notes && <div className="sb-notes">{cfg.notes}</div>}

          {Object.keys(cfg.presets ?? {}).length > 0 && (
            <div className="sb-section">
              <div className="sb-section-title">Presets</div>
              <div className="sb-presets">
                {Object.entries(cfg.presets!).map(([name, vals]) => (
                  <button key={name} className="sb-preset" onClick={() => applyPreset(vals)}>
                    {name}
                  </button>
                ))}
                <button className="sb-preset sb-preset-reset" onClick={resetDefaults}>&#8634; Reset</button>
              </div>
            </div>
          )}

          {(cfg.fields ?? []).length > 0 && (
            <div className="sb-section">
              <div className="sb-section-title">Frame fields</div>
              {cfg.fields!.map((f) => {
                const v = (effective[f.path] ?? f.default) as number
                return (
                  <div key={f.path} className="sb-field-row">
                    <div className="sb-field-head">
                      <span className="sb-field-name">{f.label}</span>
                      <span className="sb-field-val">{typeof v === 'number' ? v.toFixed(2) : String(v)}</span>
                    </div>
                    <div className="sb-field-controls">
                      <input
                        type="range"
                        min={f.min} max={f.max} step={f.step}
                        value={v}
                        disabled={animating[f.path]}
                        onChange={(e) => setField(f.path, Number(e.target.value))}
                      />
                      <label className="sb-animate">
                        <input
                          type="checkbox"
                          checked={!!animating[f.path]}
                          onChange={() => toggleAnimate(f.path)}
                        />
                        anim
                      </label>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </aside>

        <main className="sb-stage">
          <div className="sb-stage-meta">
            {pxW}×{pxH}px · {size?.label}
          </div>
          <SessionCtx.Provider value={sandboxSession as any}>
            <div
              key={mockRefreshKey}
              className="sb-widget-frame"
              style={{ width: `${pxW}px`, height: `${pxH}px` }}
            >
              {widget && size && widget.render({ w: size.w, h: size.h })}
            </div>
          </SessionCtx.Provider>
        </main>
      </div>
    </div>
  )
}
