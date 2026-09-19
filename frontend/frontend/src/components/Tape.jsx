import { useEffect, useRef } from 'react'
import { LEVEL_TONE } from '../lib/format'

export default function Tape({ logs }) {
  const endRef = useRef(null)
  const boxRef = useRef(null)

  // Follow the tape only while the operator is already at the bottom, so
  // scrolling back to read something doesn't get yanked away.
  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60
    if (atBottom) endRef.current?.scrollIntoView({ block: 'end' })
  }, [logs])

  return (
    <div ref={boxRef} className="h-full overflow-y-auto px-3 py-2 text-[11px] leading-[1.6]">
      {logs.map((l, i) => (
        <div key={`${l.ts_iso}-${i}`} className="flex gap-2">
          <span className="shrink-0 text-ink-3">{l.virtual_iso.slice(11, 19)}</span>
          <span className="w-9 shrink-0 font-semibold" style={{ color: LEVEL_TONE[l.level] ?? LEVEL_TONE.INFO }}>
            {l.level}
          </span>
          <span className="text-ink-2">{l.text}</span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
