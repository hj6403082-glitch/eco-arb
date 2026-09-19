export default function Panel({ title, right, children, className = '', bodyClass = '' }) {
  return (
    <section className={`flex min-h-0 flex-col rounded-md border border-hair bg-surface ${className}`}>
      {(title || right) && (
        <header className="flex shrink-0 items-center justify-between border-b border-hair px-3 py-2">
          <h2 className="text-[10px] font-semibold tracking-[0.18em] text-ink-3 uppercase">{title}</h2>
          {right}
        </header>
      )}
      <div className={`min-h-0 flex-1 ${bodyClass}`}>{children}</div>
    </section>
  )
}
