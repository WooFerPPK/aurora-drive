// Widget registry. `kind` strings must appear in the backend's
// allow-list (apps/backend/src/fh6/interfaces/rest/widget_kinds.py)
// so layout persistence stays compatible. The legacy
// `/api/widgets/catalog` endpoint was removed in Phase 3 (§1.3 #6) —
// this file is the only catalog now.
//
// Sizing rules:
// - Layout is on a dynamic-column CSS grid. Cells are fixed-size
//   squares (64 × 64 px); the column count grows or shrinks with the
//   viewport so the grid fills the window. `GRID_COLS` below is the
//   floor — the minimum column count even on narrow viewports.
// - Each widget declares a **discrete list of supported sizes**, ordered
//   smallest to largest — like iOS widget size families.
// - The widget's `render` receives the active size as { w, h } so it
//   can show more or less information per size.
// - `resize` controls how the drag-resize handle behaves:
//     'snap' (default) — resize snaps to the nearest declared preset
//                        in `sizes`. Widget is locked to those rungs.
//     'freeform'        — resize is grid-cell-continuous between
//                        `sizes[0]` (min) and `sizes.at(-1)` (max).
//                        The size picker (▣) still offers the presets
//                        as quick-picks. Use for widgets where any
//                        rectangle makes sense (maps, charts, large
//                        canvas surfaces).
//
// To add a new size: append to `sizes` (or insert in order). Tile-only
// widgets get a single size.

import SpeedDial from '@/features/dashboard/components/widgets/SpeedDial'
import WorldMap  from '@/features/dashboard/components/widgets/WorldMap'
import RpmTape   from '@/features/dashboard/components/widgets/RpmTape'
import RpmDial   from '@/features/dashboard/components/widgets/RpmDial'
import BoostGauge from '@/features/dashboard/components/widgets/BoostGauge'
import DynoPlot from '@/features/dashboard/components/widgets/DynoPlot'
import InputTrace from '@/features/dashboard/components/widgets/InputTrace'
import SlipWarning from '@/features/dashboard/components/widgets/SlipWarning'
import CoachFeed from '@/features/dashboard/components/widgets/CoachFeed'
import GripBudget from '@/features/dashboard/components/widgets/GripBudget'
import TireHeatmap from '@/features/dashboard/components/widgets/TireHeatmap'
import TireViz from '@/features/dashboard/components/widgets/TireViz'
import TireWear from '@/features/dashboard/components/widgets/TireWear'
import TireFailure from '@/features/dashboard/components/widgets/TireFailure'
import GearDisplay from '@/features/dashboard/components/widgets/GearDisplay'
import Pedals from '@/features/dashboard/components/widgets/Pedals'
import LapTimer from '@/features/dashboard/components/widgets/LapTimer'
import GMeter from '@/features/dashboard/components/widgets/GMeter'
import LapPredict from '@/features/dashboard/components/widgets/LapPredict'
import FinishPredict from '@/features/dashboard/components/widgets/FinishPredict'
import SessionSummary from '@/features/dashboard/components/widgets/SessionSummary'
import Fingerprint from '@/features/dashboard/components/widgets/Fingerprint'
import StyleDrift from '@/features/dashboard/components/widgets/StyleDrift'
import ShiftCoach from '@/features/dashboard/components/widgets/ShiftCoach'
import ShiftReport from '@/features/dashboard/components/widgets/ShiftReport'
import HighlightReel from '@/features/dashboard/components/widgets/HighlightReel'
import LapTable from '@/features/dashboard/components/widgets/LapTable'
import LapCompare from '@/features/dashboard/components/widgets/LapCompare'
import SteeringWheel from '@/features/dashboard/components/widgets/SteeringWheel'
import CarSilhouette from '@/features/dashboard/components/widgets/CarSilhouette'
import SpeedTrace from '@/features/dashboard/components/widgets/SpeedTrace'
import SuspensionViz from '@/features/dashboard/components/widgets/SuspensionViz'
import PowerFlow from '@/features/dashboard/components/widgets/PowerFlow'
import CrashRisk from '@/features/dashboard/components/widgets/CrashRisk'
import RaceStats from '@/features/dashboard/components/widgets/RaceStats'
import CarBadge from '@/features/dashboard/components/widgets/CarBadge'
import EngineCutaway from '@/features/dashboard/components/widgets/EngineCutaway'
import PhysicsInsights from '@/features/dashboard/components/widgets/PhysicsInsights'
import PositionTracker from '@/features/dashboard/components/widgets/PositionTracker'
import StintTimer from '@/features/dashboard/components/widgets/StintTimer'

import type { ReactElement } from 'react'

// Minimum column count for the dynamic grid. WidgetSurface measures
// the viewport and uses max(GRID_COLS, fits-in-viewport) as the actual
// column count.
export const GRID_COLS     = 12
export const ROW_HEIGHT_PX = 64
export const GRID_GAP_PX   = 6

export interface SizePreset { w: number; h: number; label: string }

export interface WidgetRenderProps {
  w: number
  h: number
  kind?: string
  size?: { w: number; h: number }
}

export interface WidgetDef {
  kind: string
  title: string
  categories: string[]
  sizes: SizePreset[]
  defaultSize: number
  resize?: 'freeform' | 'snap'
  render: (p: WidgetRenderProps) => ReactElement
}

export interface PinnedEntry {
  kind: string
  x: number
  y: number
  w: number
  h: number
}

export type TabVisibleEntry = string | PinnedEntry

export interface DefaultLayoutEntry {
  kind: string
  x: number
  y: number
  w: number
  h: number
  visible: boolean
}

// `map` category holds `world_map` (the open-world position widget).
// `track_line`, `mistake_heatmap`, etc. are still blocked on track
// inference and not reinstated. See docs/do-not-build.md.
export const CATEGORIES = [
  { id: 'gauges',    label: 'Gauges' },
  { id: 'engine',    label: 'Engine' },
  { id: 'chassis',   label: 'Chassis' },
  { id: 'tires',     label: 'Tires' },
  { id: 'map',       label: 'Map' },
  { id: 'predict',   label: 'Predict' },
  { id: 'coach',     label: 'Coach' },
  { id: 'driver',    label: 'Driver' },
  { id: 'analytics', label: 'Analytics' },
]

// Helper for terse size declarations.
const s = (w: number, h: number, label?: string): SizePreset => ({ w, h, label: label ?? `${w}×${h}` })

// One source of truth for every widget that has a real implementation.
// Stub entries for unbuilt widgets have been removed — add a widget by
// implementing its component, importing it above, and inserting a
// registry entry here. The shorter list of backend-allowed kinds is
// in widget_kinds.py on the backend; widgets that exist there but not
// here are tracked in docs/widget-catalog-proposal.md.
//
// `sizes` is ordered smallest → largest; `defaultSize` is an index
// into it.
export const WIDGETS: WidgetDef[] = [
  {
    kind: 'speed_dial', title: 'Speed dial', categories: ['gauges'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 2,
    render: (p) => <SpeedDial {...p} />,
  },
  {
    kind: 'rpm_tape', title: 'RPM tape', categories: ['gauges', 'engine'],
    sizes: [s(4, 1, 'Compact'), s(6, 2, 'Standard'), s(8, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <RpmTape {...p} />,
  },
  {
    kind: 'rpm_dial', title: 'RPM dial', categories: ['gauges', 'engine'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 2,
    render: (p) => <RpmDial {...p} />,
  },
  {
    kind: 'boost_gauge', title: 'Boost', categories: ['engine', 'gauges'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 2,
    render: (p) => <BoostGauge {...p} />,
  },
  {
    kind: 'dyno_plot', title: 'Dyno', categories: ['engine', 'analytics'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <DynoPlot {...p} />,
  },
  {
    kind: 'input_trace', title: 'Input trace', categories: ['gauges', 'analytics'],
    sizes: [s(3, 1, 'Compact'), s(4, 2, 'Standard'), s(5, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <InputTrace {...p} />,
  },
  {
    kind: 'slip_warning', title: 'Slip warning', categories: ['chassis', 'coach'],
    sizes: [s(2, 2, 'Compact'), s(3, 2, 'Standard'), s(4, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <SlipWarning {...p} />,
  },
  {
    kind: 'world_map', title: 'World map', categories: ['map'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(6, 5, 'Hero'), s(12, 8, 'Full')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <WorldMap {...p} />,
  },
  {
    kind: 'coach_feed', title: 'Coach feed', categories: ['coach'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <CoachFeed {...p} />,
  },
  {
    kind: 'grip_budget', title: 'Grip budget', categories: ['chassis'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 1,
    render: (p) => <GripBudget {...p} />,
  },
  {
    kind: 'tire_heatmap', title: 'Tire heatmap', categories: ['tires', 'chassis'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <TireHeatmap {...p} />,
  },
  {
    kind: 'tire_viz', title: 'Tire viz', categories: ['tires', 'chassis'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <TireViz {...p} />,
  },
  {
    kind: 'tire_wear', title: 'Tire wear', categories: ['tires', 'chassis'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <TireWear {...p} />,
  },
  {
    kind: 'tire_failure', title: 'Tire failure', categories: ['tires', 'predict'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <TireFailure {...p} />,
  },
  {
    kind: 'gear_display', title: 'Gear', categories: ['gauges', 'engine'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 2,
    render: (p) => <GearDisplay {...p} />,
  },
  {
    kind: 'pedals', title: 'Pedals', categories: ['gauges'],
    sizes: [s(2, 2, 'Compact'), s(2, 3, 'Standard'), s(3, 3, 'Hero')],
    defaultSize: 1,
    render: (p) => <Pedals {...p} />,
  },
  {
    kind: 'lap_timer', title: 'Lap timer', categories: ['analytics'],
    sizes: [s(3, 1, 'Compact'), s(3, 2, 'Standard'), s(4, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <LapTimer {...p} />,
  },
  {
    kind: 'g_meter', title: 'G-meter', categories: ['chassis'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 1,
    render: (p) => <GMeter {...p} />,
  },
  {
    kind: 'lap_predict', title: 'Lap predict', categories: ['predict', 'analytics'],
    sizes: [s(3, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <LapPredict {...p} />,
  },
  {
    kind: 'finish_predict', title: 'Finish predict', categories: ['predict'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 3, 'Hero')],
    defaultSize: 1,
    render: (p) => <FinishPredict {...p} />,
  },
  {
    kind: 'session_summary', title: 'Session summary', categories: ['analytics'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(6, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <SessionSummary {...p} />,
  },
  {
    kind: 'fingerprint', title: 'Driver fingerprint', categories: ['driver'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <Fingerprint {...p} />,
  },
  {
    kind: 'style_drift', title: 'Style drift', categories: ['driver', 'analytics'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <StyleDrift {...p} />,
  },
  {
    kind: 'shift_coach', title: 'Shift coach', categories: ['engine', 'coach'],
    sizes: [s(3, 1, 'Compact'), s(4, 2, 'Standard'), s(6, 2, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <ShiftCoach {...p} />,
  },
  {
    kind: 'shift_report', title: 'Shift report', categories: ['analytics', 'engine'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <ShiftReport {...p} />,
  },
  {
    kind: 'highlight_reel', title: 'Highlight reel', categories: ['analytics', 'coach'],
    sizes: [s(3, 2, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <HighlightReel {...p} />,
  },
  {
    kind: 'lap_table', title: 'Lap table', categories: ['analytics'],
    sizes: [s(3, 2, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <LapTable {...p} />,
  },
  {
    kind: 'lap_compare', title: 'Lap compare', categories: ['analytics'],
    sizes: [s(3, 1, 'Compact'), s(3, 2, 'Standard'), s(4, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <LapCompare {...p} />,
  },
  {
    kind: 'steering_wheel', title: 'Steering wheel', categories: ['chassis', 'gauges'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 4, 'Hero')],
    defaultSize: 1,
    render: (p) => <SteeringWheel {...p} />,
  },
  {
    kind: 'car_silhouette', title: 'Car silhouette', categories: ['chassis'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <CarSilhouette {...p} />,
  },
  {
    kind: 'speed_trace', title: 'Speed trace', categories: ['analytics', 'gauges'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <SpeedTrace {...p} />,
  },
  {
    kind: 'suspension_viz', title: 'Suspension viz', categories: ['chassis'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <SuspensionViz {...p} />,
  },
  {
    kind: 'power_flow', title: 'Power flow', categories: ['engine', 'chassis'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <PowerFlow {...p} />,
  },
  {
    kind: 'crash_risk', title: 'Crash risk', categories: ['predict', 'coach'],
    sizes: [s(2, 2, 'Compact'), s(3, 3, 'Standard'), s(4, 3, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <CrashRisk {...p} />,
  },
  {
    kind: 'race_stats', title: 'Race stats', categories: ['analytics', 'gauges'],
    sizes: [s(2, 2, 'Compact'), s(3, 2, 'Standard'), s(4, 2, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <RaceStats {...p} />,
  },
  {
    kind: 'car_badge', title: 'Car badge', categories: ['analytics'],
    sizes: [s(2, 2, 'Compact'), s(3, 2, 'Standard'), s(4, 2, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <CarBadge {...p} />,
  },
  {
    kind: 'engine_cutaway', title: 'Engine cutaway', categories: ['engine'],
    sizes: [s(3, 3, 'Compact'), s(4, 4, 'Standard'), s(5, 5, 'Hero')],
    defaultSize: 1,
    render: (p) => <EngineCutaway {...p} />,
  },
  {
    kind: 'physics_insights', title: 'Physics insights', categories: ['chassis', 'analytics'],
    sizes: [s(3, 2, 'Compact'), s(4, 3, 'Standard'), s(5, 4, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <PhysicsInsights {...p} />,
  },
  {
    kind: 'position_tracker', title: 'Position', categories: ['analytics'],
    sizes: [s(2, 2, 'Compact'), s(2, 3, 'Standard'), s(3, 3, 'Hero')],
    defaultSize: 1,
    render: (p) => <PositionTracker {...p} />,
  },
  {
    kind: 'stint_timer', title: 'Stint timer', categories: ['analytics'],
    sizes: [s(3, 1, 'Compact'), s(3, 2, 'Standard'), s(4, 2, 'Hero')],
    defaultSize: 1,
    resize: 'freeform',
    render: (p) => <StintTimer {...p} />,
  },
]

// Default-visible widget kinds per tab. Only kinds present in WIDGETS
// (i.e. with a real implementation) belong here — empty entries mean
// the tab opens blank until widgets are added. Add a kind to a tab's
// list once it's built and ready to ship by default.
//
// Each tab is a curated *pairing* of widgets that tell one story
// together. Entries can be either a string (kind, auto-positioned at
// the widget's default size) OR an object {kind, x, y, w, h} that pins
// the widget at an explicit grid position and size. Tabs whose entries
// are all explicit set autoArrange:false in TabsContext so the layout
// stays exactly where it's specified.
//
// Layouts below are designed for a 2560×720 viewport, which works out
// to a 35×8 grid at the 64px cell + 6px gap pitch. Widgets respect
// their declared min/max envelopes — see WIDGETS above for valid sizes.
export const TAB_DEFAULT_VISIBLE: Record<string, TabVisibleEntry[]> = {
  // LIVE — at-a-glance cockpit: every essential big gauge plus map,
  // coach, and a row of analysis widgets below.
  live: [
    { kind: 'speed_dial',      x:  0, y: 0, w: 4, h: 4 },
    { kind: 'rpm_dial',        x:  4, y: 0, w: 4, h: 4 },
    { kind: 'gear_display',    x:  8, y: 0, w: 4, h: 4 },
    { kind: 'grip_budget',     x: 12, y: 0, w: 4, h: 4 },
    { kind: 'g_meter',         x: 16, y: 0, w: 4, h: 4 },
    { kind: 'pedals',          x: 20, y: 0, w: 3, h: 3 },
    { kind: 'input_trace',     x: 20, y: 3, w: 3, h: 1 },
    { kind: 'coach_feed',      x: 23, y: 0, w: 5, h: 4 },
    { kind: 'world_map',       x: 28, y: 0, w: 7, h: 8 },
    { kind: 'rpm_tape',        x:  0, y: 4, w: 8, h: 3 },
    { kind: 'lap_timer',       x:  8, y: 4, w: 4, h: 3 },
    { kind: 'race_stats',      x: 12, y: 4, w: 4, h: 2 },
    { kind: 'car_badge',       x: 12, y: 6, w: 4, h: 2 },
    { kind: 'slip_warning',    x: 16, y: 4, w: 4, h: 3 },
    { kind: 'finish_predict',  x: 20, y: 4, w: 3, h: 3 },
    { kind: 'session_summary', x: 23, y: 4, w: 5, h: 3 },
    { kind: 'shift_coach',     x:  0, y: 7, w: 6, h: 1 },
    { kind: 'lap_compare',     x:  6, y: 7, w: 3, h: 1 },
    { kind: 'stint_timer',     x: 16, y: 7, w: 4, h: 1 },
  ],

  // ENGINE — powertrain story: how the engine makes power right now.
  engine: [
    { kind: 'rpm_dial',          x:  0, y: 0, w: 4, h: 4 },
    { kind: 'boost_gauge',       x:  4, y: 0, w: 4, h: 4 },
    { kind: 'gear_display',      x:  8, y: 0, w: 4, h: 4 },
    { kind: 'power_flow',        x: 12, y: 0, w: 5, h: 4 },
    { kind: 'dyno_plot',         x: 17, y: 0, w: 5, h: 4 },
    { kind: 'engine_cutaway',    x: 22, y: 0, w: 5, h: 5 },
    { kind: 'pedals',            x: 27, y: 0, w: 3, h: 3 },
    { kind: 'input_trace',       x: 27, y: 3, w: 3, h: 1 },
    { kind: 'shift_coach',       x: 30, y: 0, w: 5, h: 2 },
    { kind: 'speed_trace',       x: 30, y: 2, w: 5, h: 2 },
    { kind: 'rpm_tape',          x:  0, y: 4, w: 8, h: 3 },
    { kind: 'physics_insights',  x:  8, y: 4, w: 5, h: 4 },
    { kind: 'lap_timer',         x: 13, y: 4, w: 4, h: 3 },
    { kind: 'session_summary',   x: 17, y: 4, w: 5, h: 3 },
    { kind: 'finish_predict',    x: 22, y: 5, w: 4, h: 3 },
    { kind: 'coach_feed',        x: 27, y: 4, w: 5, h: 4 },
    { kind: 'highlight_reel',    x: 32, y: 4, w: 3, h: 4 },
  ],

  // CHASSIS — what the car is doing under load.
  chassis: [
    { kind: 'g_meter',           x:  0, y: 0, w: 4, h: 4 },
    { kind: 'grip_budget',       x:  4, y: 0, w: 4, h: 4 },
    { kind: 'steering_wheel',    x:  8, y: 0, w: 4, h: 4 },
    { kind: 'tire_heatmap',      x: 12, y: 0, w: 4, h: 4 },
    { kind: 'suspension_viz',    x: 16, y: 0, w: 5, h: 5 },
    { kind: 'car_silhouette',    x: 21, y: 0, w: 5, h: 5 },
    { kind: 'slip_warning',      x: 26, y: 0, w: 4, h: 3 },
    { kind: 'coach_feed',        x: 30, y: 0, w: 5, h: 5 },
    { kind: 'physics_insights',  x:  0, y: 4, w: 5, h: 4 },
    { kind: 'speed_trace',       x:  5, y: 4, w: 5, h: 4 },
    { kind: 'pedals',            x: 10, y: 4, w: 3, h: 3 },
    { kind: 'input_trace',       x: 10, y: 7, w: 3, h: 1 },
    { kind: 'lap_compare',       x: 13, y: 5, w: 3, h: 3 },
    { kind: 'session_summary',   x: 16, y: 5, w: 5, h: 3 },
    { kind: 'highlight_reel',    x: 21, y: 5, w: 5, h: 3 },
    { kind: 'finish_predict',    x: 26, y: 5, w: 4, h: 3 },
    { kind: 'rpm_tape',          x: 30, y: 5, w: 5, h: 3 },
  ],

  // TIRES — rubber temperature, wear, and failure prediction.
  tires: [
    { kind: 'tire_heatmap',      x:  0, y: 0, w: 5, h: 5 },
    { kind: 'tire_viz',          x:  5, y: 0, w: 5, h: 5 },
    { kind: 'tire_wear',         x: 10, y: 0, w: 5, h: 5 },
    { kind: 'tire_failure',      x: 15, y: 0, w: 5, h: 4 },
    { kind: 'grip_budget',       x: 20, y: 0, w: 4, h: 4 },
    { kind: 'g_meter',           x: 24, y: 0, w: 4, h: 4 },
    { kind: 'slip_warning',      x: 28, y: 0, w: 4, h: 3 },
    { kind: 'coach_feed',        x: 32, y: 0, w: 3, h: 5 },
    { kind: 'speed_trace',       x:  0, y: 5, w: 5, h: 3 },
    { kind: 'physics_insights',  x:  5, y: 5, w: 5, h: 3 },
    { kind: 'session_summary',   x: 10, y: 5, w: 5, h: 3 },
    { kind: 'lap_compare',       x: 15, y: 4, w: 4, h: 3 },
    { kind: 'lap_predict',       x: 19, y: 4, w: 4, h: 4 },
    { kind: 'highlight_reel',    x: 23, y: 4, w: 5, h: 4 },
    { kind: 'finish_predict',    x: 28, y: 3, w: 4, h: 3 },
    { kind: 'rpm_tape',          x: 28, y: 6, w: 7, h: 2 },
  ],

  // TRACK — open-world map as hero, with lap timing + speed context.
  track: [
    { kind: 'world_map',         x:  0, y: 0, w: 12, h: 8 },
    { kind: 'speed_dial',        x: 12, y: 0, w: 4, h: 4 },
    { kind: 'gear_display',      x: 16, y: 0, w: 4, h: 4 },
    { kind: 'rpm_dial',          x: 20, y: 0, w: 4, h: 4 },
    { kind: 'lap_timer',         x: 24, y: 0, w: 4, h: 3 },
    { kind: 'race_stats',        x: 28, y: 0, w: 4, h: 2 },
    { kind: 'car_badge',         x: 28, y: 2, w: 4, h: 2 },
    { kind: 'coach_feed',        x: 32, y: 0, w: 3, h: 5 },
    { kind: 'speed_trace',       x: 12, y: 4, w: 5, h: 4 },
    { kind: 'rpm_tape',          x: 17, y: 4, w: 8, h: 3 },
    { kind: 'input_trace',       x: 17, y: 7, w: 5, h: 1 },
    { kind: 'pedals',            x: 25, y: 4, w: 3, h: 3 },
    { kind: 'lap_compare',       x: 28, y: 4, w: 4, h: 3 },
    { kind: 'stint_timer',       x: 22, y: 7, w: 6, h: 1 },
    { kind: 'shift_coach',       x: 28, y: 7, w: 4, h: 1 },
    { kind: 'highlight_reel',    x: 32, y: 5, w: 3, h: 3 },
  ],

  // TELEMETRY — lap-by-lap analysis. Tables and traces dominate.
  telemetry: [
    { kind: 'lap_table',         x:  0, y: 0, w: 5, h: 5 },
    { kind: 'lap_compare',       x:  5, y: 0, w: 4, h: 3 },
    { kind: 'speed_trace',       x:  9, y: 0, w: 5, h: 4 },
    { kind: 'input_trace',       x: 14, y: 0, w: 5, h: 3 },
    { kind: 'session_summary',   x: 19, y: 0, w: 6, h: 3 },
    { kind: 'highlight_reel',    x: 25, y: 0, w: 5, h: 5 },
    { kind: 'fingerprint',       x: 30, y: 0, w: 5, h: 5 },
    { kind: 'lap_compare',       x:  5, y: 3, w: 4, h: 2 },
    { kind: 'physics_insights',  x: 14, y: 3, w: 5, h: 4 },
    { kind: 'style_drift',       x: 19, y: 3, w: 5, h: 4 },
    { kind: 'race_stats',        x: 24, y: 5, w: 4, h: 2 },
    { kind: 'car_badge',         x: 28, y: 5, w: 4, h: 2 },
    { kind: 'rpm_tape',          x:  0, y: 5, w: 8, h: 3 },
    { kind: 'speed_trace',       x:  9, y: 4, w: 5, h: 4 },
    { kind: 'lap_timer',         x: 24, y: 7, w: 4, h: 1 },
    { kind: 'stint_timer',       x: 28, y: 7, w: 4, h: 1 },
    { kind: 'shift_coach',       x: 32, y: 5, w: 3, h: 1 },
    { kind: 'lap_predict',       x: 32, y: 6, w: 3, h: 2 },
  ],

  // STRATEGY — predictions, position, tire endurance.
  strategy: [
    { kind: 'finish_predict',    x:  0, y: 0, w: 4, h: 3 },
    { kind: 'position_tracker',  x:  4, y: 0, w: 3, h: 3 },
    { kind: 'lap_predict',       x:  7, y: 0, w: 4, h: 4 },
    { kind: 'crash_risk',        x: 11, y: 0, w: 4, h: 3 },
    { kind: 'tire_failure',      x: 15, y: 0, w: 5, h: 4 },
    { kind: 'tire_heatmap',      x: 20, y: 0, w: 4, h: 4 },
    { kind: 'tire_wear',         x: 24, y: 0, w: 4, h: 4 },
    { kind: 'race_stats',        x: 28, y: 0, w: 4, h: 2 },
    { kind: 'car_badge',         x: 28, y: 2, w: 4, h: 2 },
    { kind: 'coach_feed',        x: 32, y: 0, w: 3, h: 5 },
    { kind: 'world_map',         x:  0, y: 3, w: 7, h: 5 },
    { kind: 'stint_timer',       x:  7, y: 4, w: 4, h: 2 },
    { kind: 'session_summary',   x: 11, y: 4, w: 5, h: 3 },
    { kind: 'lap_timer',         x: 16, y: 4, w: 4, h: 3 },
    { kind: 'lap_compare',       x: 20, y: 4, w: 4, h: 3 },
    { kind: 'highlight_reel',    x: 24, y: 4, w: 5, h: 4 },
    { kind: 'speed_trace',       x: 29, y: 4, w: 3, h: 4 },
    { kind: 'rpm_tape',          x:  7, y: 6, w: 9, h: 2 },
    { kind: 'shift_coach',       x: 16, y: 7, w: 6, h: 1 },
  ],

  // DRIVER — long-term style profile and skill drift.
  driver: [
    { kind: 'fingerprint',       x:  0, y: 0, w: 5, h: 5 },
    { kind: 'style_drift',       x:  5, y: 0, w: 5, h: 4 },
    { kind: 'session_summary',   x: 10, y: 0, w: 6, h: 3 },
    { kind: 'highlight_reel',    x: 16, y: 0, w: 5, h: 5 },
    { kind: 'lap_table',         x: 21, y: 0, w: 5, h: 5 },
    { kind: 'speed_trace',       x: 26, y: 0, w: 5, h: 4 },
    { kind: 'car_badge',         x: 31, y: 0, w: 4, h: 2 },
    { kind: 'race_stats',        x: 31, y: 2, w: 4, h: 2 },
    { kind: 'physics_insights',  x:  5, y: 4, w: 5, h: 4 },
    { kind: 'lap_compare',       x: 10, y: 3, w: 4, h: 3 },
    { kind: 'lap_predict',       x: 14, y: 3, w: 4, h: 4 },
    { kind: 'input_trace',       x: 26, y: 4, w: 5, h: 2 },
    { kind: 'rpm_tape',          x: 26, y: 6, w: 9, h: 2 },
    { kind: 'stint_timer',       x: 10, y: 6, w: 4, h: 1 },
    { kind: 'lap_timer',         x: 14, y: 7, w: 4, h: 1 },
    { kind: 'shift_coach',       x: 31, y: 4, w: 4, h: 2 },
    { kind: 'crash_risk',        x: 18, y: 5, w: 3, h: 3 },
    { kind: 'finish_predict',    x: 21, y: 5, w: 3, h: 3 },
  ],
}

export function getWidgetDef(kind: string): WidgetDef | null {
  return WIDGETS.find((w) => w.kind === kind) || null
}

export function widgetsForCategories(categories: string[] | null | undefined): WidgetDef[] {
  if (!categories || categories.length === 0) return WIDGETS
  const want = new Set(categories)
  return WIDGETS.filter((w) => (w.categories || []).some((c) => want.has(c)))
}

export type NearestSizeBias = 'grow' | 'shrink' | null

// Find the size in `def.sizes` closest to (w, h). When `bias` is given
// we prefer sizes whose area is *at least* the bias direction — used
// during resize so the snap target tracks the user's gesture.
//   bias === 'grow'   → prefer the smallest size ≥ (w,h)
//   bias === 'shrink' → prefer the largest  size ≤ (w,h)
//   bias === null     → nearest by Manhattan distance
export function nearestSize(def: WidgetDef | null, w: number, h: number, bias: NearestSizeBias = null): { w: number; h: number } {
  if (!def?.sizes?.length) return { w, h }
  const sizes = def.sizes
  if (bias === 'grow') {
    for (const sz of sizes) {
      if (sz.w >= w && sz.h >= h) return sz
    }
    return sizes[sizes.length - 1]!
  }
  if (bias === 'shrink') {
    for (let i = sizes.length - 1; i >= 0; i--) {
      const sz = sizes[i]!
      if (sz.w <= w && sz.h <= h) return sz
    }
    return sizes[0]!
  }
  // Nearest by Manhattan distance, then by area, then by index.
  let best = sizes[0]!
  let bestD = Math.abs(best.w - w) + Math.abs(best.h - h)
  for (let i = 1; i < sizes.length; i++) {
    const sz = sizes[i]!
    const d = Math.abs(sz.w - w) + Math.abs(sz.h - h)
    if (d < bestD) { best = sz; bestD = d }
  }
  return best
}

// The first declared size is the floor, the last is the ceiling.
export function minSize(def: WidgetDef | null): { w: number; h: number } { return def?.sizes?.[0] || { w: 1, h: 1 } }
export function maxSize(def: WidgetDef | null): { w: number; h: number } {
  if (!def?.sizes?.length) return { w: GRID_COLS, h: 99 }
  return def.sizes[def.sizes.length - 1]!
}

// Clamp (w, h) to the widget's min/max envelope without snapping to a
// preset. Used by freeform-resize widgets where any (w, h) inside the
// envelope is valid.
export function clampSize(def: WidgetDef | null, w: number, h: number): { w: number; h: number } {
  const mn = minSize(def)
  const mx = maxSize(def)
  return {
    w: Math.max(mn.w, Math.min(mx.w, w | 0)),
    h: Math.max(mn.h, Math.min(mx.h, h | 0)),
  }
}
export function defaultSize(def: WidgetDef | null): { w: number; h: number } {
  if (!def?.sizes?.length) return { w: 3, h: 2 }
  return def.sizes[def.defaultSize ?? 0]!
}

// Compose the default per-tab layout. Each visible widget gets its
// Entries in TAB_DEFAULT_VISIBLE may be either a string kind (default
// size, auto-arranged) or an object {kind, x, y, w, h} that pins the
// widget at an explicit grid position. Returns a uniform list of
// entries the layout system can use directly.
export function buildDefaultLayout(visible: TabVisibleEntry[] = []): DefaultLayoutEntry[] {
  const byKind = new Map<string, PinnedEntry | null>()
  for (const entry of visible) {
    if (typeof entry === 'string') byKind.set(entry, null)
    else if (entry && typeof entry === 'object' && entry.kind) byKind.set(entry.kind, entry)
  }
  return WIDGETS.map((wdef) => {
    const sz = defaultSize(wdef)
    const pin = byKind.get(wdef.kind)
    if (pin) {
      return {
        kind: wdef.kind,
        x: pin.x | 0,
        y: pin.y | 0,
        w: pin.w | 0,
        h: pin.h | 0,
        visible: true,
      }
    }
    return {
      kind: wdef.kind,
      x: 0, y: 0,
      w: sz.w, h: sz.h,
      visible: byKind.has(wdef.kind),
    }
  })
}

// True when every visible entry for a tab carries explicit coordinates.
// Used by TabsContext to suppress the auto-arrange first-paint pass.
export function tabHasExplicitLayout(tabId: string): boolean {
  const entries = TAB_DEFAULT_VISIBLE[tabId] || []
  if (entries.length === 0) return false
  return entries.every((e): e is PinnedEntry => typeof e === 'object' && !!e.kind && Number.isFinite(e.x) && Number.isFinite(e.y))
}
