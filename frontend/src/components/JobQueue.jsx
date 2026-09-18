import { hhmm, STATUS_TONE } from '../lib/format'

export default function JobQueue({ jobs, decisions, selectedId, onSelect, onCancel }) {
  if (!jobs.length) {
    return (
      <p className="px-3 py-6 text-center text-xs text-ink-3">
        No jobs queued. Submit one, or press <span className="text-ink-2">Seed demo</span>.
      </p>
    )
  }
  return (
    <div className="overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-surface text-[10px] tracking-[0.1em] text-ink-3 uppercase">
          <tr className="border-b border-hair">
            <th className="px-3 py-1.5 text-left font-medium">Job</th>
            <th className="px-2 py-1.5 text-right font-medium">kWh</th>
            <th className="px-2 py-1.5 text-left font-medium">Status</th>
            <th className="px-2 py-1.5 text-left font-medium">Runs</th>
            <th className="px-1.5 py-1.5 text-right font-medium whitespace-nowrap">CO₂</th>
            <th className="w-5" />
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const d = decisions[job.id]
            const tone = STATUS_TONE[job.status] ?? STATUS_TONE.QUEUED
            const selected = job.id === selectedId
            return (
              <tr
                key={job.id}
                onClick={() => onSelect(job.id)}
                className={`cursor-pointer border-b border-hair/60 transition-colors ${
                  selected ? 'bg-chart' : 'hover:bg-chart/60'
                }`}
              >
                <td className="px-3 py-1.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${job.status === 'RUNNING' ? 'pulse' : ''}`}
                      style={{ background: tone.dot }}
                    />
                    <span className="truncate text-ink" title={job.name}>{job.name}</span>
                  </div>
                  {job.status === 'RUNNING' && (
                    <div className="mt-1 ml-3.5 h-1 w-24 overflow-hidden rounded-full bg-hair">
                      <div
                        className="h-full rounded-full bg-carbon transition-[width] duration-500"
                        style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }}
                      />
                    </div>
                  )}
                </td>
                <td className="px-2 py-1.5 text-right text-ink-2">{job.energy_kwh}</td>
                <td className={`px-2 py-1.5 ${tone.fg}`}>{job.status}</td>
                <td className="px-1.5 py-1.5 text-ink-2">{hhmm(job.run_at_iso)}</td>
                <td className="px-1.5 py-1.5 text-right whitespace-nowrap">
                  {d && d.action === 'WAIT' ? (
                    <span className="text-good">−{d.carbon_saved_pct.toFixed(0)}%</span>
                  ) : (
                    <span className="text-ink-3">—</span>
                  )}
                </td>
                <td className="pr-1">
                  {['QUEUED', 'WAITING'].includes(job.status) && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onCancel(job.id) }}
                      title={`Cancel ${job.name}`}
                      aria-label={`Cancel ${job.name}`}
                      className="px-1 text-ink-3 hover:text-critical"
                    >
                      ×
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
