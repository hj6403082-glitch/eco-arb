import { useState } from 'react'

const FIELD =
  'w-full rounded border border-hair bg-chart px-2 py-1 text-xs text-ink outline-none focus:border-carbon'
const LABEL = 'text-[10px] tracking-[0.1em] text-ink-3 uppercase'

export default function SubmitForm({ workloads, onSubmit }) {
  const [form, setForm] = useState({
    name: 'ml-training-batch',
    energy_kwh: 25,
    duration_minutes: 90,
    deadline_hours: 24,
    workload: 'hash_grind',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        name: form.name.trim() || 'unnamed-job',
        energy_kwh: Number(form.energy_kwh),
        duration_minutes: Number(form.duration_minutes),
        deadline_hours: Number(form.deadline_hours),
        workload: form.workload,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2.5 px-3 py-3">
      <div>
        <label className={LABEL} htmlFor="job-name">Name</label>
        <input id="job-name" className={FIELD} value={form.name} onChange={set('name')} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={LABEL} htmlFor="job-kwh">Energy kWh</label>
          <input id="job-kwh" className={FIELD} type="number" min="0.1" step="0.1" value={form.energy_kwh} onChange={set('energy_kwh')} />
        </div>
        <div>
          <label className={LABEL} htmlFor="job-dur">Duration min</label>
          <input id="job-dur" className={FIELD} type="number" min="1" step="1" value={form.duration_minutes} onChange={set('duration_minutes')} />
        </div>
        <div>
          <label className={LABEL} htmlFor="job-dl">Deadline h</label>
          <input id="job-dl" className={FIELD} type="number" min="0.25" max="24" step="0.25" value={form.deadline_hours} onChange={set('deadline_hours')} />
        </div>
        <div>
          <label className={LABEL} htmlFor="job-wl">Workload</label>
          <select id="job-wl" className={FIELD} value={form.workload} onChange={set('workload')}>
            {workloads.map((w) => <option key={w} value={w}>{w}</option>)}
          </select>
        </div>
      </div>
      {error && <p className="text-[11px] text-critical">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-carbon px-3 py-1.5 text-xs font-semibold text-black transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {busy ? 'Submitting…' : 'Submit job'}
      </button>
    </form>
  )
}
