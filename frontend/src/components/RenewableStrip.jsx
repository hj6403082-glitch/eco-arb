import { useMemo } from 'react'
import { useMeasure } from '../lib/useMeasure'

const SLOT_MS = 30 * 60 * 1000
const M = { top: 6, right: 18, bottom: 4, left: 52 }

/**
 * Renewable share, as its own chart with its own axis.
 *
 * Deliberately NOT a second y-axis on the intensity chart: two measures on one
 * frame with different scales is the single most misread chart form there is.
 */
export default function RenewableStrip({ slots, nowIso, height = 56 }) {
  const [ref, { width }] = useMeasure()

  const geom = useMemo(() => {
    if (!slots?.length || width < 80) return null
    const t0 = Date.parse(slots[0].timestamp)
    const t1 = Date.parse(slots[slots.length - 1].timestamp) + SLOT_MS
    const iw = Math.max(10, width - M.left - M.right)
    const ih = Math.max(6, height - M.top - M.bottom)
    return {
      t0, t1, iw, ih,
      x: (ms) => M.left + ((ms - t0) / (t1 - t0)) * iw,
      y: (v) => M.top + ih - (Math.min(100, Math.max(0, v)) / 100) * ih,
    }
  }, [slots, width, height])

  if (!geom) return <div ref={ref} style={{ height }} />
  const { t0, t1, ih, x, y } = geom

  const pts = []
  slots.forEach((s) => {
    const a = Date.parse(s.timestamp)
    pts.push([x(a), y(s.renewable_pct)], [x(a + SLOT_MS), y(s.renewable_pct)])
  })
  const line = pts.map(([px, py], i) => `${i ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`).join('')
  const area = `${line}L${x(t1).toFixed(1)},${(M.top + ih).toFixed(1)}L${x(t0).toFixed(1)},${(M.top + ih).toFixed(1)}Z`
  const nowMs = nowIso ? Date.parse(nowIso) : null
  const nowX = nowMs != null && nowMs >= t0 && nowMs <= t1 ? x(nowMs) : null

  return (
    <div ref={ref} style={{ height }}>
      <svg width="100%" height={height} role="img" aria-label="Renewable share of generation over the same 24 hours, percent">
        <line x1={M.left} x2={width - M.right} y1={y(50)} y2={y(50)} stroke="var(--color-hair)" strokeWidth="1" />
        <text x={M.left - 8} y={y(100) + 8} textAnchor="end" fontSize="9" fill="var(--color-ink-3)">100</text>
        <text x={M.left - 8} y={y(0)} textAnchor="end" fontSize="9" fill="var(--color-ink-3)">0</text>
        <path d={area} fill="var(--color-renew)" fillOpacity="0.1" />
        <path d={line} fill="none" stroke="var(--color-renew)" strokeWidth="2" strokeLinejoin="round" />
        {nowX != null && <line x1={nowX} x2={nowX} y1={M.top} y2={M.top + ih} stroke="var(--color-ink-2)" strokeWidth="1" />}
      </svg>
    </div>
  )
}
