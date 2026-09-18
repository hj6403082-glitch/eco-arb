import { useMemo, useState } from 'react'
import { useMeasure } from '../lib/useMeasure'
import { hhmm } from '../lib/format'

const M = { top: 18, right: 18, bottom: 26, left: 52 }
const SLOT_MS = 30 * 60 * 1000

/**
 * Carbon intensity forecast, 24h of half-hour slots.
 *
 * One series, one axis. Renewable share is a separate chart below rather than
 * a second y-scale on this one. Windows (planned / run-now baseline) are
 * annotation bands, not series, so they carry status colour + a direct label.
 */
export default function ForecastChart({ slots, nowIso, windows = [], height = 268 }) {
  const [ref, { width }] = useMeasure()
  const [hover, setHover] = useState(null)

  const geom = useMemo(() => {
    if (!slots?.length || width < 80) return null
    const t0 = Date.parse(slots[0].timestamp)
    const t1 = Date.parse(slots[slots.length - 1].timestamp) + SLOT_MS
    const maxI = Math.max(...slots.map((s) => s.intensity_gco2_kwh))
    const yMax = Math.ceil((maxI * 1.12) / 50) * 50
    const iw = Math.max(10, width - M.left - M.right)
    const ih = Math.max(10, height - M.top - M.bottom)
    const x = (ms) => M.left + ((ms - t0) / (t1 - t0)) * iw
    const y = (v) => M.top + ih - (v / yMax) * ih
    return { t0, t1, yMax, iw, ih, x, y }
  }, [slots, width, height])

  if (!geom) return <div ref={ref} style={{ height }} />

  const { t0, t1, yMax, iw, ih, x, y } = geom

  // Step path: a half-hour slot is a flat price for that half hour, not a
  // point to interpolate between. Drawing it as a step tells the truth.
  const pts = []
  slots.forEach((s) => {
    const a = Date.parse(s.timestamp)
    pts.push([x(a), y(s.intensity_gco2_kwh)], [x(a + SLOT_MS), y(s.intensity_gco2_kwh)])
  })
  const line = pts.map(([px, py], i) => `${i ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`).join('')
  const area = `${line}L${x(t1).toFixed(1)},${(M.top + ih).toFixed(1)}L${x(t0).toFixed(1)},${(M.top + ih).toFixed(1)}Z`

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yMax * f))
  const xTicks = []
  for (let ms = Math.ceil(t0 / (3 * 3600e3)) * 3 * 3600e3; ms < t1; ms += 3 * 3600e3) xTicks.push(ms)

  const nowMs = nowIso ? Date.parse(nowIso) : null
  const nowX = nowMs != null && nowMs >= t0 && nowMs <= t1 ? x(nowMs) : null

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - box.left
    if (px < M.left || px > M.left + iw) return setHover(null)
    const ms = t0 + ((px - M.left) / iw) * (t1 - t0)
    const idx = Math.min(slots.length - 1, Math.max(0, Math.floor((ms - t0) / SLOT_MS)))
    setHover({ idx, x: x(Date.parse(slots[idx].timestamp) + SLOT_MS / 2) })
  }

  const hovered = hover ? slots[hover.idx] : null

  return (
    <div ref={ref} className="relative" style={{ height }}>
      <svg
        width="100%"
        height={height}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Carbon intensity forecast for the next 24 hours, in grams of CO2 per kilowatt hour"
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={M.left + iw} y1={y(v)} y2={y(v)} stroke="var(--color-hair)" strokeWidth="1" />
            <text x={M.left - 8} y={y(v) + 4} textAnchor="end" fontSize="10" fill="var(--color-ink-3)">
              {v}
            </text>
          </g>
        ))}
        <text
          x={12} y={M.top + ih / 2} fontSize="10" fill="var(--color-ink-3)"
          textAnchor="middle" transform={`rotate(-90 12 ${M.top + ih / 2})`}
        >
          gCO₂/kWh
        </text>

        {xTicks.map((ms) => (
          <text key={ms} x={x(ms)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--color-ink-3)">
            {hhmm(new Date(ms).toISOString())}
          </text>
        ))}

        {/* Annotation bands: where a job is planned to run, and where it would
            have run had it not been deferred. */}
        {windows.map((w, i) => {
          const a = Math.max(x(Date.parse(w.start)), M.left)
          const b = Math.min(x(Date.parse(w.end)), M.left + iw)
          if (!(b > a)) return null
          const color = w.kind === 'baseline' ? 'var(--color-critical)' : 'var(--color-good)'
          return (
            <g key={i}>
              <rect
                x={a} y={M.top} width={b - a} height={ih}
                fill={color} fillOpacity={w.kind === 'baseline' ? 0.09 : 0.14}
              />
              <line x1={a} x2={b} y1={M.top} y2={M.top} stroke={color} strokeWidth="2" />
              <text
                x={(a + b) / 2} y={M.top - 6} textAnchor="middle" fontSize="9"
                fill="var(--color-ink-2)" letterSpacing="0.06em"
              >
                {w.label}
              </text>
            </g>
          )
        })}

        <path d={area} fill="var(--color-carbon)" fillOpacity="0.1" />
        <path d={line} fill="none" stroke="var(--color-carbon)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

        {nowX != null && (
          <g>
            <line x1={nowX} x2={nowX} y1={M.top} y2={M.top + ih} stroke="var(--color-ink-2)" strokeWidth="1" />
            <circle cx={nowX} cy={M.top} r="3.5" fill="var(--color-ink)" stroke="var(--color-chart)" strokeWidth="2" />
            <text x={nowX + 5} y={M.top + 10} fontSize="9" fill="var(--color-ink-2)" letterSpacing="0.08em">
              NOW
            </text>
          </g>
        )}

        {hovered && (
          <g>
            <line x1={hover.x} x2={hover.x} y1={M.top} y2={M.top + ih} stroke="var(--color-ink-3)" strokeWidth="1" />
            <circle
              cx={hover.x} cy={y(hovered.intensity_gco2_kwh)} r="4.5"
              fill="var(--color-carbon)" stroke="var(--color-chart)" strokeWidth="2"
            />
          </g>
        )}
      </svg>

      {hovered && (
        <div
          className="pointer-events-none absolute z-10 rounded border border-hair bg-void/95 px-2.5 py-1.5 text-[11px] leading-relaxed shadow-lg"
          style={{
            left: Math.min(Math.max(hover.x - 66, 4), Math.max(4, width - 140)),
            top: 8,
          }}
        >
          <div className="text-ink-3">{hhmm(hovered.timestamp)}–{hhmm(new Date(Date.parse(hovered.timestamp) + SLOT_MS).toISOString())}</div>
          <div className="flex items-center gap-1.5 text-ink">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: 'var(--color-carbon)' }} />
            {hovered.intensity_gco2_kwh.toFixed(0)} gCO₂/kWh
          </div>
          <div className="text-ink-2">{hovered.renewable_pct.toFixed(0)}% renewable</div>
          <div className="text-ink-3">£{hovered.price.toFixed(2)}/MWh</div>
        </div>
      )}
    </div>
  )
}
