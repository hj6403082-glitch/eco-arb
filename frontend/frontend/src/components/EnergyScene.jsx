import { useEffect, useRef } from "react";

// Decorative energy field. It carries no telemetry and never changes the data.
export function EnergyField({ active }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let width = 0,
      height = 0,
      frame = 0,
      last = 0;
    const pointer = { x: -1000, y: -1000 };
    const resize = () => {
      width = innerWidth;
      height = innerHeight;
      const ratio = Math.min(devicePixelRatio || 1, 1.5);
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    const move = (e) => {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
    };
    const draw = (stamp) => {
      if (active) frame = requestAnimationFrame(draw);
      if (stamp - last < 33 && active) return;
      last = stamp;
      if (document.hidden) return;
      const t = active ? stamp / 1000 : 0;
      ctx.clearRect(0, 0, width, height);
      const points = Array.from({ length: 36 }, (_, i) => ({
        x: ((i * 137.51 + t * (2 + (i % 4))) % (width + 80)) - 40,
        y: (i * 79.37 + Math.sin(t * 0.18 + i) * 36) % (height + 80),
        color: i % 3 === 0 ? "#b179ff" : i % 3 === 1 ? "#39e7f3" : "#ddff71",
      }));
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        const near = Math.hypot(p.x - pointer.x, p.y - pointer.y) < 190;
        ctx.fillStyle = p.color;
        ctx.globalAlpha = near ? 0.8 : 0.3;
        ctx.beginPath();
        ctx.arc(p.x, p.y, near ? 2.1 : 1.25, 0, Math.PI * 2);
        ctx.fill();
        for (let j = i + 1; j < points.length; j++) {
          const q = points[j],
            d = Math.hypot(p.x - q.x, p.y - q.y);
          if (d < 150) {
            ctx.globalAlpha = (1 - d / 150) * 0.13;
            ctx.strokeStyle = p.color;
            ctx.lineWidth = 0.7;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;
    };
    resize();
    draw(100);
    window.addEventListener("resize", resize);
    if (active) window.addEventListener("pointermove", move, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", move);
    };
  }, [active]);
  return (
    <div className="energy-background" aria-hidden="true">
      <div className="aurora aurora-violet" />
      <div className="aurora aurora-cyan" />
      <div className="aurora aurora-coral" />
      <canvas ref={canvasRef} />
      <div className="perspective-grid" />
    </div>
  );
}

export function EnergyStage({ intensity, mode, pending, running }) {
  return (
    <section className="energy-stage" aria-label="Carbon-aware compute network">
      <div className="stage-copy">
        <span className="stage-kicker">
          <i />
          THE FUTURE RUNS CLEANER
        </span>
        <h2>
          Less carbon.
          <br />
          <em>More possibility.</em>
        </h2>
        <p>Real workloads. Smarter timing. A lighter footprint.</p>
        <div className="stage-tags">
          <span>
            <i />
            {mode}
          </span>
          <span>
            {pending} pending · {running} executing
          </span>
        </div>
      </div>
      <div className="reactor" aria-hidden="true">
        <div className="reactor-halo" />
        <svg viewBox="0 0 500 220">
          <defs>
            <linearGradient id="reactor-gradient">
              <stop stopColor="#ad79ff" />
              <stop offset=".5" stopColor="#39e7f3" />
              <stop offset="1" stopColor="#dcff72" />
            </linearGradient>
            <radialGradient id="reactor-core">
              <stop stopColor="#6a47ca" stopOpacity=".8" />
              <stop offset="1" stopColor="#160d30" stopOpacity=".2" />
            </radialGradient>
          </defs>
          <g className="reactor-paths">
            <path d="M0 40h90l45 45h80 M0 175h95l40-40h80 M290 85h75l40-45h95 M290 135h75l40 45h95" />
            <path d="M0 110h185 M315 110h185" />
          </g>
          <g className="reactor-flow">
            <path d="M0 40h90l45 45h80 M0 175h95l40-40h80 M290 85h75l40-45h95 M290 135h75l40 45h95" />
          </g>
          <circle
            cx="250"
            cy="110"
            r="81"
            fill="none"
            stroke="#453264"
            strokeWidth=".6"
          />
          <g className="ring ring-outer">
            <circle
              cx="250"
              cy="110"
              r="75"
              fill="none"
              stroke="url(#reactor-gradient)"
              strokeWidth="2"
              strokeDasharray="90 45 7 12"
            />
            <circle cx="250" cy="35" r="4" fill="#dfff74" />
          </g>
          <g className="ring ring-middle">
            <ellipse
              cx="250"
              cy="110"
              rx="96"
              ry="41"
              fill="none"
              stroke="#a67bff"
              strokeWidth="1.3"
            />
            <circle cx="346" cy="110" r="3" fill="#b99aff" />
          </g>
          <g className="ring ring-inner">
            <circle
              cx="250"
              cy="110"
              r="55"
              fill="none"
              stroke="#43e4f3"
              strokeWidth="1"
              strokeDasharray="3 9"
            />
          </g>
          <circle
            cx="250"
            cy="110"
            r="44"
            fill="url(#reactor-core)"
            stroke="#9075bf"
            strokeWidth=".5"
          />
          <path
            className="core-bolt"
            d="m257 79-29 38h20l-4 25 29-40h-20z"
            fill="#dfff74"
          />
          <g className="reactor-nodes">
            <circle cx="90" cy="40" r="4" fill="#af7bff" />
            <circle cx="95" cy="175" r="4" fill="#45e7f0" />
            <circle cx="405" cy="40" r="4" fill="#ff9779" />
            <circle cx="405" cy="180" r="4" fill="#dfff74" />
          </g>
        </svg>
        <span className="reactor-label label-left">GRID INTELLIGENCE</span>
        <span className="reactor-label label-right">CLEANER COMPUTE</span>
        <span className="reactor-signal">
          {Math.round(intensity)} <small>gCO₂/kWh · forecast</small>
        </span>
      </div>
      <div className="stage-edge" />
    </section>
  );
}
