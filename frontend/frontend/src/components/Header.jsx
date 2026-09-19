import { dayHhmm } from '../lib/format'

function SpeedButton({ value, active, onClick }) {
  return (
    <button
      onClick={() => onClick(value)}
      aria-pressed={active}
      className={`px-3 py-1 text-xs font-semibold tracking-wide transition-colors ${
        active
          ? 'bg-warning text-black'
          : 'text-ink-2 hover:bg-hair hover:text-ink'
      }`}
    >
      {value}×
    </button>
  )
}

export default function Header({ clock, feedStatus, onSpeed, children }) {
  const compressed = clock?.compressed
  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 border-b border-hair bg-surface px-4 py-2.5">
      <div className="flex items-baseline gap-2.5">
        <span className="text-base font-bold tracking-[0.2em] text-ink">ECO-ARB</span>
        <span className="hidden text-[10px] tracking-[0.14em] text-ink-3 uppercase sm:inline">
          Carbon-Aware Compute Scheduler
        </span>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-[10px] tracking-[0.14em] text-ink-3 uppercase">Grid clock</span>
        <span className="text-lg font-semibold text-ink">{dayHhmm(clock?.virtual_iso)}</span>
        <span className="text-[10px] text-ink-3">UTC</span>
      </div>

      {/* The compression state is never implicit — it is the one thing a viewer
          must not misread as real elapsed time. */}
      <div className="flex items-center gap-2">
        <div className="flex overflow-hidden rounded border border-hair">
          {(clock?.allowed_speeds ?? [1, 60, 360]).map((s) => (
            <SpeedButton key={s} value={s} active={clock?.speed === s} onClick={onSpeed} />
          ))}
        </div>
        {compressed ? (
          <span className="pulse rounded-sm bg-warning px-2 py-1 text-[10px] font-bold tracking-[0.1em] text-black uppercase">
            ⚠ Time-compressed {clock.speed}× — demo clock, real workloads
          </span>
        ) : (
          <span className="rounded-sm border border-hair px-2 py-1 text-[10px] tracking-[0.1em] text-ink-3 uppercase">
            Real time
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${feedStatus?.live ? 'pulse' : ''}`}
          style={{ background: feedStatus?.live ? 'var(--color-good)' : 'var(--color-serious)' }}
        />
        <span className="text-[10px] tracking-[0.1em] text-ink-2 uppercase">
          {feedStatus?.live ? 'Live · UK Carbon Intensity API' : 'Offline fallback curve'}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2">{children}</div>
    </header>
  )
}
