import { dayHhmm, gbp } from '../lib/format'

function Stat({ label, value, tone = 'text-ink', sub }) {
  return (
    <div>
      <div className="text-[10px] tracking-[0.1em] text-ink-3 uppercase">{label}</div>
      <div className={`text-sm ${tone}`}>{value}</div>
      {sub && <div className="text-[10px] text-ink-3">{sub}</div>}
    </div>
  )
}

export default function DecisionPanel({ job, decision }) {
  if (!job || !decision) {
    return <p className="px-3 py-6 text-center text-xs text-ink-3">Select a job to see its decision.</p>
  }

  const waiting = decision.action === 'WAIT'
  const color = waiting ? 'var(--color-warning)' : 'var(--color-good)'

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm text-ink">{job.name}</div>
          <div className="text-[10px] text-ink-3">
            {job.id} · {job.energy_kwh} kWh · {job.duration_minutes} min · {job.workload}
          </div>
        </div>
        <span
          className="shrink-0 rounded px-2.5 py-1 text-xs font-bold tracking-[0.12em]"
          style={{ background: color, color: '#0e0e0d' }}
        >
          {decision.action}
        </span>
      </div>

      {/* The headline of this panel: what deferring actually bought. */}
      <div className="rounded border border-hair bg-chart px-3 py-2.5">
        <div className="text-[10px] tracking-[0.1em] text-ink-3 uppercase">Carbon saved vs running now</div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-3xl font-semibold" style={{ color: waiting ? 'var(--color-good)' : 'var(--color-ink-2)' }}>
            {decision.carbon_saved_pct.toFixed(1)}
          </span>
          <span className="text-sm text-ink-2">%</span>
          <span className="ml-2 text-[11px] text-ink-3">
            {decision.baseline_carbon_g.toFixed(0)} → {decision.optimal_carbon_g.toFixed(0)} gCO₂
          </span>
        </div>
        <div className="mt-1 text-[11px] text-ink-3">
          Cost {decision.cost_saved_pct >= 0 ? 'saved' : 'premium'}{' '}
          <span className="text-ink-2">{Math.abs(decision.cost_saved_pct).toFixed(1)}%</span>
          {' · '}
          {gbp(decision.baseline_cost_gbp)} → {gbp(decision.optimal_cost_gbp)}
          <span className="ml-1 text-ink-3">(modelled)</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Stat label="Run at" value={dayHhmm(decision.run_at_iso)} tone={waiting ? 'text-warning' : 'text-good'} />
        <Stat label="Window ends" value={dayHhmm(decision.window_end_iso)} />
        <Stat label="Deadline" value={dayHhmm(job.deadline_iso)} />
        <Stat
          label="Windows searched"
          value={`${decision.feasible_windows} / ${decision.slots_considered}`}
          sub="feasible / slots"
        />
      </div>

      <div>
        <div className="text-[10px] tracking-[0.1em] text-ink-3 uppercase">Reason</div>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-2">{decision.reason}</p>
      </div>

      {job.result && (
        <details className="shrink-0">
          <summary className="cursor-pointer text-[10px] tracking-[0.1em] text-ink-3 uppercase hover:text-ink-2">
            Execution result
          </summary>
          <pre className="mt-1 max-h-40 overflow-auto rounded border border-hair bg-chart p-2 text-[10px] leading-relaxed text-ink-2">
{JSON.stringify(job.result, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
