import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from './lib/api'
import ForecastChart from './components/ForecastChart'
import RenewableStrip from './components/RenewableStrip'
import Panel from './components/Panel'
import Header from './components/Header'
import JobQueue from './components/JobQueue'
import DecisionPanel from './components/DecisionPanel'
import Tape from './components/Tape'
import SubmitForm from './components/SubmitForm'
import Totals from './components/Totals'

const POLL_MS = 1000

const BTN =
  'rounded border border-hair px-2.5 py-1 text-[11px] text-ink-2 transition-colors hover:border-ink-3 hover:text-ink'

export default function App() {
  const [state, setState] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState(null)

  const poll = useCallback(async () => {
    try {
      const next = await api.getState()
      setState(next)
      setError(null)
      setSelectedId((prev) => {
        const ids = next.jobs.map((j) => j.id)
        // Only auto-select when there is no live selection, so an operator
        // inspecting a job is never yanked away by the poll.
        if (prev && ids.includes(prev)) return prev
        // Otherwise lead with the biggest deferral: a WAIT decision is the one
        // that shows the scheduler earning its keep.
        const bestDeferral = next.jobs
          .filter((j) => next.decisions[j.id]?.action === 'WAIT')
          .sort((a, b) => next.decisions[b.id].carbon_saved_pct - next.decisions[a.id].carbon_saved_pct)[0]
        const running = next.jobs.find((j) => j.status === 'RUNNING')
        return bestDeferral?.id ?? running?.id ?? ids[ids.length - 1] ?? null
      })
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => clearInterval(id)
  }, [poll])

  const act = (fn) => async (...args) => {
    try {
      await fn(...args)
      await poll()
    } catch (err) {
      setError(err.message)
    }
  }

  const virtualIso = state?.clock?.virtual_iso
  const slots = state?.grid?.forecast ?? []
  const jobs = state?.jobs ?? []
  const decisions = state?.decisions ?? {}
  const selected = jobs.find((j) => j.id === selectedId) ?? null
  const decision = selectedId ? decisions[selectedId] : null

  // Annotation bands for the selected job: where it is planned to run, and
  // where it would have run had the scheduler not deferred it.
  const windows = useMemo(() => {
    if (!selected || !decision) return []
    const out = [{
      start: decision.run_at_iso,
      end: decision.window_end_iso,
      kind: 'planned',
      label: decision.action === 'WAIT' ? 'DEFERRED WINDOW' : 'RUNNING NOW',
    }]
    if (decision.action === 'WAIT' && virtualIso) {
      const base = Date.parse(virtualIso)
      out.push({
        start: virtualIso,
        end: new Date(base + selected.duration_minutes * 60000).toISOString(),
        kind: 'baseline',
        label: 'IF RUN NOW',
      })
    }
    return out
  }, [selected, decision, virtualIso])

  if (!state) {
    return (
      <div className="grid h-full place-items-center text-sm text-ink-3">
        {error ? (
          <div className="text-center">
            <p className="text-critical">Backend unreachable — {error}</p>
            <p className="mt-2 text-[11px]">Start it with <code className="text-ink-2">./backend/run.sh</code></p>
          </div>
        ) : (
          'Connecting to scheduler…'
        )}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <Header clock={state.clock} feedStatus={state.grid.status} onSpeed={act(api.setSpeed)}>
        <button className={BTN} onClick={act(api.seedDemo)}>Seed demo</button>
        <button className={BTN} onClick={act(api.refreshGrid)}>Refresh grid</button>
        <button className={BTN} onClick={act(api.resetAll)}>Reset</button>
      </Header>

      {error && (
        <div className="shrink-0 border-b border-hair bg-critical/15 px-4 py-1 text-[11px] text-critical">
          {error}
        </div>
      )}

      <main className="grid min-h-0 flex-1 gap-2 p-2 lg:grid-cols-[minmax(0,1fr)_384px]">
        <div className="flex min-h-0 flex-col gap-2">
          <Panel
            title="Carbon intensity forecast · next 24h"
            right={
              <div className="flex items-center gap-3 text-[10px] text-ink-3">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: 'var(--color-carbon)' }} />
                  gCO₂/kWh · {state.grid.status.live ? 'live' : 'fallback'}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: 'var(--color-renew)' }} />
                  renewable % · derived
                </span>
              </div>
            }
            bodyClass="px-1 pt-1 pb-2"
          >
            <ForecastChart slots={slots} nowIso={state.clock.virtual_iso} windows={windows} />
            <RenewableStrip slots={slots} nowIso={state.clock.virtual_iso} />
          </Panel>

          <Panel title="Session totals" className="shrink-0">
            <Totals totals={state.totals} />
          </Panel>

          <Panel title="Scheduler tape" className="min-h-[140px] flex-1" bodyClass="min-h-0">
            <Tape logs={state.logs} />
          </Panel>
        </div>

        <div className="flex min-h-0 flex-col gap-2">
          <Panel
            title="Job queue"
            right={<span className="text-[10px] text-ink-3">{jobs.length} jobs</span>}
            className="max-h-[34%] shrink-0"
            bodyClass="min-h-0"
          >
            <JobQueue
              jobs={jobs}
              decisions={decisions}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onCancel={act(api.cancelJob)}
            />
          </Panel>

          <Panel title="Decision" className="min-h-[260px] flex-1" bodyClass="min-h-0">
            <DecisionPanel job={selected} decision={decision} />
          </Panel>

          <Panel title="Submit job" className="shrink-0">
            <SubmitForm workloads={state.workloads} onSubmit={act(api.createJob)} />
          </Panel>
        </div>
      </main>
    </div>
  )
}
