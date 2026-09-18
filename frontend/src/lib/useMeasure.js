import { useCallback, useEffect, useRef, useState } from 'react'

/** Element width/height, so SVG text never gets scaled by a viewBox stretch. */
export function useMeasure() {
  const [rect, setRect] = useState({ width: 0, height: 0 })
  const nodeRef = useRef(null)

  const ref = useCallback((node) => { nodeRef.current = node }, [])

  useEffect(() => {
    const node = nodeRef.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setRect((prev) =>
        Math.abs(prev.width - width) < 0.5 && Math.abs(prev.height - height) < 0.5
          ? prev
          : { width, height },
      )
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return [ref, rect]
}
