import { gbp, mass } from '../lib/format'

/**
 * The dashboard's one hero figure: carbon actually avoided by jobs that have
 * already been dispatched, measured against each job's submit-time baseline.
 * Not a forecast — a tally of what the scheduler has banked.
 */
export default function Totals({ totals }) {
  const saved = mass(totals?.carbon_saved_g)
  return (
    <div className="flex flex-wrap items-end gap-x-8 gap-y-3 px-3 py-3">
      <div>
        <div className="text-[10px] tracking-[0.12em] text-ink-3 uppercase">CO₂ avoided this session</div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-5xl leading-none font-semibold text-good" style={{ fontVariantNumeric: 'proportional-nums' }}>
            {saved.value}
          </span>
          <span className="text-lg text-ink-2">{saved.unit}</span>
        </div>
        <div className="mt-1 text-[11px] text-ink-3">
          {totals?.carbon_saved_pct?.toFixed(1) ?? '0.0'}% below the run-immediately baseline
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[11px] sm:grid-cols-4">
        {[
          ['Emitted', `${mass(totals?.carbon_emitted_g).value} ${mass(totals?.carbon_emitted_g).unit}`],
          ['Cost saved', `${gbp(totals?.cost_saved_gbp)}`, 'modelled'],
          ['Energy', `${totals?.energy_scheduled_kwh ?? 0} kWh`],
          ['Completed', `${totals?.jobs_completed ?? 0} / ${totals?.jobs_total ?? 0}`],
        ].map(([label, value, note]) => (
          <div key={label}>
            <dt className="text-[10px] tracking-[0.1em] text-ink-3 uppercase">{label}</dt>
            <dd className="text-ink">
              {value}
              {note && <span className="ml-1 text-[10px] text-ink-3">({note})</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
