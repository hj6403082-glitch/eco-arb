export const hhmm = (iso) => (iso ? iso.slice(11, 16) : '--:--')
export const dayHhmm = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${iso.slice(11, 16)}` : '--')

export const pct = (v, digits = 1) =>
  `${v > 0 ? '' : ''}${Number(v ?? 0).toFixed(digits)}%`

/** Grams -> the unit a human reads without counting zeros. */
export function mass(grams) {
  const g = Number(grams ?? 0)
  if (Math.abs(g) >= 1_000_000) return { value: (g / 1_000_000).toFixed(2), unit: 't' }
  if (Math.abs(g) >= 1000) return { value: (g / 1000).toFixed(g >= 10_000 ? 0 : 1), unit: 'kg' }
  return { value: g.toFixed(0), unit: 'g' }
}

export const gbp = (v) => `£${Number(v ?? 0).toFixed(2)}`

export const STATUS_TONE = {
  QUEUED:  { fg: 'text-ink-2',   dot: 'var(--color-ink-3)' },
  WAITING: { fg: 'text-warning', dot: 'var(--color-warning)' },
  RUNNING: { fg: 'text-carbon',  dot: 'var(--color-carbon)' },
  DONE:    { fg: 'text-good',    dot: 'var(--color-good)' },
  FAILED:  { fg: 'text-critical',dot: 'var(--color-critical)' },
  MISSED:  { fg: 'text-critical',dot: 'var(--color-critical)' },
}

export const LEVEL_TONE = {
  OK:   'var(--color-good)',
  RUN:  'var(--color-carbon)',
  PLAN: 'var(--color-warning)',
  WARN: 'var(--color-serious)',
  ERR:  'var(--color-critical)',
  INFO: 'var(--color-ink-3)',
}
