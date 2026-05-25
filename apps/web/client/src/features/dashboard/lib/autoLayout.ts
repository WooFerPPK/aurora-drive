// Grid-based widget packer. Skyline best-fit decreasing with multi-
// start orderings, optional size-variant swapping, and category-
// affinity clustering.
//
// Inputs:
//   items: [{ kind, w, h, sizes?, resize?, categories? }]
//     - sizes: the widget's discrete size presets ({w,h}[]) — when
//       provided and `resize !== 'freeform'` the packer may swap to a
//       different preset to tighten the layout.
//     - resize: 'freeform' widgets keep the user's exact rect. A
//       stretched chart means something specific, so we won't auto-
//       relax it; we just place it as-is.
//     - categories: tags from the widget registry. Used to score
//       clustering — pairs that share categories are pulled toward
//       sharing an edge in the final layout.
//   cols: column count of the target grid.
//   opts.targetRows: visible rows in the viewport — a soft cap. The
//     packer will shrink widgets to fit when overflow is the
//     alternative.
//   opts.allowResize: gate for size-variant search. Default true.
//
// Returns { [kind]: { x, y, w, h } }. w/h may differ from inputs when
// the packer chose a tighter preset; callers treat them as
// authoritative.
//
// Algorithm:
// 1. For each (ordering × resize policy) trial, run a skyline best-
//    fit packer that places widgets one at a time at the position that
//    sits lowest, with the least under-widget waste, and the most
//    shared-edge contact with already-placed widgets in matching
//    categories.
// 2. Score each trial: overflow rows are heavily penalised, then
//    bounding-box area (smaller = tighter), then size shrinkage (so
//    we don't downsize without payoff), minus a clustering reward
//    that sums affinity across every pair of touching widgets.
// 3. Return the lowest-scoring layout.

import { GRID_COLS } from '@/features/dashboard/widgetRegistry'

export interface SizePreset { w: number; h: number }

export interface AutoLayoutItem {
  kind: string
  w: number
  h: number
  sizes?: SizePreset[] | undefined
  resize?: 'freeform' | string | undefined
  categories?: string[] | undefined
}

export interface AutoLayoutOpts {
  targetRows?: number
  allowResize?: boolean
}

export type PlacedRect = { x: number; y: number; w: number; h: number }
export type PlacedMap = Record<string, PlacedRect>

interface InternalItem extends AutoLayoutItem {
  _i: number
}

interface PlacedRectWithCategories extends PlacedRect {
  categories?: string[]
}

// Sort orders tried in the multi-start. 2D bin packing has no closed-
// form best sort, but the union of these covers the typical wins.
// `ORDERINGS` are item-list → item-list so we can mix plain comparator
// sorts with structural reorderings (the by-category cluster).
const ORDERINGS: Array<(items: InternalItem[]) => InternalItem[]> = [
  (items) => items.slice().sort((a, b) =>
    (b.w * b.h - a.w * a.h) || (b.h - a.h) || (a._i - b._i)),       // area desc
  (items) => items.slice().sort((a, b) =>
    (b.w - a.w) || (b.h - a.h) || (a._i - b._i)),                   // width desc
  (items) => items.slice().sort((a, b) =>
    (b.h - a.h) || (b.w - a.w) || (a._i - b._i)),                   // height desc
  (items) => items.slice().sort((a, b) =>
    (Math.max(b.w, b.h) - Math.max(a.w, a.h))
    || (b.w * b.h - a.w * a.h) || (a._i - b._i)),                   // max-dim desc
  (items) => items.slice().sort((a, b) => a._i - b._i),             // original order
  (items) => clusteredOrder(items),                                 // by-category clusters
]

// Group items by primary category, sort each group by area desc, then
// emit the groups in total-area-desc order. Skyline placement processes
// items in order, so adjacent items in the ordering tend to land
// adjacent in the grid — which means widgets that share a primary
// category cluster together for free.
function clusteredOrder(items: InternalItem[]): InternalItem[] {
  const groups = new Map<string, InternalItem[]>()
  for (const it of items) {
    const key = it.categories?.[0] || '_'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(it)
  }
  for (const g of groups.values()) {
    g.sort((a, b) => (b.w * b.h - a.w * a.h) || (a._i - b._i))
  }
  const ordered = Array.from(groups.values())
    .sort((a, b) => sumArea(b) - sumArea(a))
  return ordered.flat()
}

function sumArea(arr: InternalItem[]): number {
  let s = 0
  for (const it of arr) s += it.w * it.h
  return s
}

// Jaccard similarity over category sets — symmetric, in [0, 1], with
// 0 meaning "no shared category" (so the affinity term vanishes for
// unrelated widgets). Using Jaccard instead of raw intersection
// prevents widgets with many tags from dominating clustering.
function categoryAffinity(a: { categories?: string[] | undefined }, b: { categories?: string[] | undefined }): number {
  const aCats = a?.categories, bCats = b?.categories
  if (!aCats?.length || !bCats?.length) return 0
  const seen = new Set(aCats)
  let intersect = 0
  for (const c of bCats) if (seen.has(c)) intersect++
  if (intersect === 0) return 0
  const union = aCats.length + bCats.length - intersect
  return intersect / union
}

// Length of the shared edge between two axis-aligned rectangles.
// Returns 0 unless they touch on one side (no overlap, no diagonal).
// Used as the geometric half of the affinity score — the packer
// rewards placements where a new widget's edge runs alongside a
// category-similar neighbour.
function sharedEdge(a: PlacedRect, b: PlacedRect): number {
  if (a.y + a.h === b.y || b.y + b.h === a.y) {
    return Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x))
  }
  if (a.x + a.w === b.x || b.x + b.w === a.x) {
    return Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y))
  }
  return 0
}

function candidateSizes(item: InternalItem, allowResize: boolean): SizePreset[] {
  // Freeform widgets and items without a preset list have exactly one
  // size — whatever the caller gave us.
  if (!allowResize || item.resize === 'freeform' || !item.sizes?.length) {
    return [{ w: item.w, h: item.h }]
  }
  // Current size goes first so ties in the per-placement score break
  // toward keeping the user's choice.
  const out: SizePreset[] = [{ w: item.w, h: item.h }]
  const seen = new Set([`${item.w}x${item.h}`])
  for (const sz of item.sizes) {
    const k = `${sz.w}x${sz.h}`
    if (seen.has(k)) continue
    seen.add(k)
    out.push({ w: sz.w, h: sz.h })
  }
  return out
}

interface PackResult {
  placed: PlacedMap
  placedRects: PlacedRectWithCategories[]
  rows: number
}

// Skyline best-fit placement. `skyline[c]` is the top of the free
// space in column c — every placement raises the relevant columns.
// `placedRects` retains each placement's category list so subsequent
// items can score their adjacency against it.
function packSkyline(items: InternalItem[], cols: number, allowResize: boolean): PackResult {
  const skyline = new Uint16Array(cols)
  const placed: PlacedMap = {}
  const placedRects: PlacedRectWithCategories[] = []
  let maxRow = 0

  for (const it of items) {
    const candidates = candidateSizes(it, allowResize).filter((sz) => sz.w <= cols)
    if (candidates.length === 0) {
      // Caller passed a widget wider than the grid. Force-fit by
      // clamping; placement still finds a slot for it.
      candidates.push({ w: Math.min(cols, it.w), h: it.h })
    }

    let best: { x: number; y: number; w: number; h: number; score: number } | null = null
    for (let ci = 0; ci < candidates.length; ci++) {
      const sz = candidates[ci]!
      for (let x = 0; x + sz.w <= cols; x++) {
        // Widget bottoms at the tallest skyline column inside its
        // footprint. `wasted` is the empty cells between that bottom
        // and the shorter columns underneath it — the per-widget
        // gap contribution.
        let y = 0
        for (let dx = 0; dx < sz.w; dx++) {
          if (skyline[x + dx]! > y) y = skyline[x + dx]!
        }
        let wasted = 0
        for (let dx = 0; dx < sz.w; dx++) wasted += y - skyline[x + dx]!

        // Affinity: shared-edge length weighted by Jaccard similarity
        // against every already-placed widget. A speed dial dropped
        // next to an RPM dial scores high; an unrelated tire widget
        // scores nothing. Capped per-pair by the candidate's longest
        // side so a single huge neighbour can't dominate.
        let affinity = 0
        if (it.categories?.length && placedRects.length) {
          const rect: PlacedRect = { x, y, w: sz.w, h: sz.h }
          for (const p of placedRects) {
            const sim = categoryAffinity(it, p)
            if (sim === 0) continue
            const edge = sharedEdge(rect, p)
            if (edge > 0) affinity += sim * edge
          }
        }

        // Lower y wins (compact top); ties: less waste under the
        // widget; ties: stronger category clustering; ties: bigger
        // size (don't shrink without reason); ties: earlier candidate
        // (so the current size beats alts).
        const score = y * 10000
                    + wasted * 100
                    - affinity * 60
                    - sz.w * sz.h
                    + ci * 0.001
        if (!best || score < best.score) {
          best = { x, y, w: sz.w, h: sz.h, score }
        }
      }
    }
    if (!best) continue

    for (let dx = 0; dx < best.w; dx++) {
      skyline[best.x + dx] = best.y + best.h
    }
    placed[it.kind] = { x: best.x, y: best.y, w: best.w, h: best.h }
    placedRects.push({
      x: best.x, y: best.y, w: best.w, h: best.h,
      ...(it.categories ? { categories: it.categories } : {}),
    })
    if (best.y + best.h > maxRow) maxRow = best.y + best.h
  }

  return { placed, placedRects, rows: maxRow }
}

export function autoArrangeGrid(items: AutoLayoutItem[], cols: number = GRID_COLS, opts: AutoLayoutOpts = {}): PlacedMap {
  if (!items || items.length === 0) return {}
  const { targetRows = Infinity, allowResize = true } = opts

  const indexed: InternalItem[] = items.map((it, i) => ({
    ...it,
    _i: i,
    w: Math.min(cols, Math.max(1, it.w | 0)),
    h: Math.max(1, it.h | 0),
  }))
  const origArea = indexed.reduce((s, it) => s + it.w * it.h, 0)

  // Total affinity across all touching pairs of placed widgets — the
  // layout-wide companion to the per-placement affinity term. Trials
  // that herd similar widgets together score lower (better) here.
  function totalClustering(placedRects: PlacedRectWithCategories[]): number {
    let s = 0
    for (let i = 0; i < placedRects.length; i++) {
      for (let j = i + 1; j < placedRects.length; j++) {
        const sim = categoryAffinity(placedRects[i]!, placedRects[j]!)
        if (sim === 0) continue
        const edge = sharedEdge(placedRects[i]!, placedRects[j]!)
        if (edge > 0) s += sim * edge
      }
    }
    return s
  }

  // Cost: overflow >> bbox area >> shrink penalty >> clustering. The
  // first term makes the packer reach for smaller variants when the
  // user's sizes can't fit the viewport; the second tightens the
  // bounding box; the third stops it shrinking when it didn't need
  // to; the fourth pulls similar-category widgets together among
  // otherwise comparable layouts.
  function cost({ placed, placedRects, rows }: PackResult): number {
    let area = 0
    for (const k in placed) area += placed[k]!.w * placed[k]!.h
    const used = Math.max(rows, 1)
    const overflow = Math.max(0, used - targetRows)
    const bbox = used * cols
    const shrink = Math.max(0, origArea - area)
    const cluster = totalClustering(placedRects)
    return overflow * cols * 50 + bbox + shrink * 0.6 - cluster * 0.4
  }

  let best: { result: PackResult; cost: number } | null = null
  for (const order of ORDERINGS) {
    const sorted = order(indexed)
    // Pass 1: try preserving the input sizes first. This wins
    // whenever the user's chosen sizes fit nicely.
    const a = packSkyline(sorted, cols, false)
    const ca = cost(a)
    if (!best || ca < best.cost) best = { result: a, cost: ca }
    if (!allowResize) continue
    // Pass 2: allow swapping to alternate presets. Wins when the
    // input sizes overflow the viewport.
    const b = packSkyline(sorted, cols, true)
    const cb = cost(b)
    if (cb < best.cost) best = { result: b, cost: cb }
  }

  return best!.result.placed
}
