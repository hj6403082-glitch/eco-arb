import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import * as api from "./lib/api";
import { EnergyField, EnergyStage } from "./components/EnergyScene";
import { Intelligence, Regions } from "./components/Intelligence";

const fmt = (n, d = 0) =>
  (Math.abs(Number(n ?? 0)) < 0.5 * 10 ** -d
    ? 0
    : Number(n ?? 0)
  ).toLocaleString("en-GB", { maximumFractionDigits: d });
const time = (s) =>
  s
    ? new Date(s).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      })
    : "—";
const names = {
  hash_grind: "SHA-256 verification",
  matrix_train: "Matrix computation",
  shell: "Configured batch command",
};
function Icon({ name, size = 18 }) {
  const paths = {
    grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    bolt: "m13 2-9 12h7l-1 8 10-12h-7z",
    leaf: "M20 4C6 1 1 12 7 18s17 0 13-14Z M6 20l10-10",
    layers: "m12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5",
    chart: "M4 3v17h17 M7 14l4-5 4 3 5-7",
    clock: "M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    arrow: "M5 12h14 m-6-6 6 6-6 6",
    plus: "M12 5v14 M5 12h14",
    check: "m5 12 4 4L19 6",
    download: "M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5",
    activity: "M2 12h5l3-8 4 16 3-8h5",
    refresh: "M20 8a8 8 0 1 0 0 8 M20 3v5h-5",
    close: "m6 6 12 12 M6 18 18 6",
    info: "M12 11v6 M12 7h.01 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    search: "M21 21l-6-6 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.bolt} />
    </svg>
  );
}
const PAGES = {
  Overview: "overview",
  Grid: "grid",
  Workloads: "workloads",
  Impact: "impact",
  Activity: "activity",
  Simulation: "simulation",
  Regions: "regions",
  Intelligence: "intelligence",
};
const readPage = () =>
  Object.keys(PAGES).find(
    (name) => "#/" + PAGES[name] === window.location.hash,
  ) || "Overview";
function DetailDialog({ onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="detail-dialog"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-label="Workload decision"
    >
      <div className="detail-heading">
        <span className="eyebrow">WORKLOAD INTELLIGENCE</span>
        <button
          autoFocus
          className="icon-btn"
          aria-label="Close workload details"
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Badge({ children, tone = "" }) {
  return (
    <span className={"badge " + tone}>
      <i />
      {children}
    </span>
  );
}
function Panel({ title, kicker, extra, children, className = "" }) {
  return (
    <section className={"panel " + className}>
      <div className="panel-head">
        <div>
          {kicker && <span className="eyebrow">{kicker}</span>}
          <h2>{title}</h2>
        </div>
        {extra}
      </div>
      {children}
    </section>
  );
}
function download(data, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 500);
}
function Forecast({ slots, decision, horizon, setHorizon }) {
  const [hover, setHover] = useState(null);
  const data = slots.slice(0, horizon * 2 + 1);
  const W = 920,
    H = 260,
    left = 44,
    right = 20,
    top = 25,
    bottom = 38;
  const max =
    Math.ceil(Math.max(100, ...data.map((s) => s.intensity_gco2_kwh)) / 50) *
    50;
  const x = (i) =>
    left + (i * (W - left - right)) / Math.max(1, data.length - 1);
  const y = (n) => H - bottom - (n / max) * (H - top - bottom);
  const pts = data.map((s, i) => `${x(i)},${y(s.intensity_gco2_kwh)}`);
  const low = data.reduce(
    (best, s, i) =>
      s.intensity_gco2_kwh < data[best].intensity_gco2_kwh ? i : best,
    0,
  );
  const active = hover === null ? low : hover;
  const chosen = data[active];
  const start = Date.parse(data[0]?.timestamp);
  const px = (t) =>
    left +
    (((Date.parse(t) - start) / 1800000) * (W - left - right)) /
      Math.max(1, data.length - 1);
  return (
    <Panel
      title="The next clean window starts here."
      kicker="GRID INTELLIGENCE"
      extra={
        <div className="segmented">
          {[6, 12, 24].map((h) => (
            <button
              key={h}
              className={horizon === h ? "active" : ""}
              onClick={() => setHorizon(h)}
            >
              {h}H
            </button>
          ))}
        </div>
      }
      className="forecast"
    >
      <div className="chart-legend">
        <span>
          <i className="green-dot" />
          Carbon intensity <small>gCO₂/kWh</small>
        </span>
        <span>
          <i className="dashed-dot" />
          Visible average
        </span>
        <span className="chart-hint">Hover to explore forecast</span>
      </div>
      <div className="chart-wrap">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Carbon intensity forecast with optimal execution window"
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id="carbon-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#b4f569" stopOpacity=".22" />
              <stop offset="100%" stopColor="#b4f569" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <g key={f}>
              <line
                x1={left}
                x2={W - right}
                y1={y(max * f)}
                y2={y(max * f)}
                stroke="#26332f"
                strokeDasharray="3 6"
              />
              <text x={left - 12} y={y(max * f) + 4} textAnchor="end">
                {Math.round(max * f)}
              </text>
            </g>
          ))}
          {decision && px(decision.run_at_iso) < W - right && (
            <rect
              x={Math.max(left, px(decision.run_at_iso))}
              width={Math.max(
                3,
                Math.min(W - right, px(decision.window_end_iso)) -
                  Math.max(left, px(decision.run_at_iso)),
              )}
              y={top}
              height={H - top - bottom}
              fill="#b4f569"
              opacity=".1"
            />
          )}
          <path
            d={`M${pts.join(" L")} L${x(data.length - 1)},${H - bottom} L${left},${H - bottom}Z`}
            fill="url(#carbon-fill)"
          />
          <line
            x1={left}
            x2={W - right}
            y1={y(
              data.reduce((a, s) => a + s.intensity_gco2_kwh, 0) / data.length,
            )}
            y2={y(
              data.reduce((a, s) => a + s.intensity_gco2_kwh, 0) / data.length,
            )}
            stroke="#879789"
            strokeDasharray="5 6"
            opacity=".5"
          />
          <path
            d={`M${pts.join(" L")}`}
            stroke="#b4f569"
            strokeWidth="2.8"
            fill="none"
            strokeLinejoin="round"
          />
          {data.map(
            (s, i) =>
              i % Math.max(1, Math.round(data.length / 6)) === 0 && (
                <text key={i} x={x(i)} y={H - 12} textAnchor="middle">
                  {time(s.timestamp)}
                </text>
              ),
          )}
          {chosen && (
            <g>
              <line
                x1={x(active)}
                x2={x(active)}
                y1={top}
                y2={H - bottom}
                stroke="#b4f569"
                opacity=".35"
                strokeDasharray="4 4"
              />
              <circle
                cx={x(active)}
                cy={y(chosen.intensity_gco2_kwh)}
                r="5"
                fill="#b4f569"
                stroke="#12231a"
                strokeWidth="3"
              />
            </g>
          )}
          {data.map((s, i) => (
            <rect
              key={i}
              x={x(i) - 9}
              y={top}
              width={(W - left - right) / data.length + 10}
              height={H - top - bottom}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </svg>
        <div className="chart-readout">
          <span>
            {hover === null
              ? "CLEANEST INTERVAL"
              : time(chosen?.timestamp) + " UTC"}
          </span>
          <strong>
            {fmt(chosen?.intensity_gco2_kwh)} <small>gCO₂/kWh</small>
          </strong>
        </div>
      </div>
      <div className="forecast-footer">
        <span>
          <Icon name="leaf" size={15} />
          <b>{time(data[low]?.timestamp)} UTC</b> · cleanest visible interval
        </span>
        <span>
          Half-hour resolution <span className="muted">/ UTC</span>
        </span>
      </div>
    </Panel>
  );
}
/* The engine already enumerates every window that can be optimal and throws the
 * losers away. DecisionTheatre replays that real search: each candidate the
 * engine scored, in time order, with the running best. Nothing here is staged --
 * `trace` is exactly what the engine evaluated. */
function DecisionTheatre({ result, chosenIso, motion }) {
  const trace = useMemo(
    () => (result?.trace || []).filter((r) => r.feasible),
    [result],
  );
  // Reduced motion jumps straight to the answer; the parent remounts this with a
  // fresh key when the search changes, so the starting step is initial state
  // rather than an effect that resets it.
  const last = Math.max(0, trace.length - 1);
  const [step, setStep] = useState(() => (motion ? 0 : last));
  useEffect(() => {
    if (!motion || step >= last) return;
    const id = setTimeout(() => setStep((s) => s + 1), step < 4 ? 150 : 68);
    return () => clearTimeout(id);
  }, [step, last, motion]);

  if (!trace.length) return null;
  const seen = trace.slice(0, step + 1);
  const current = seen.at(-1);
  const best = seen.reduce((a, b) => (b.carbon_g < a.carbon_g ? b : a), seen[0]);
  const carbons = trace.map((r) => r.carbon_g);
  const lo = Math.min(...carbons), hi = Math.max(...carbons);
  const W = 560, H = 132, pad = 8;
  const x = (i) => pad + (i / Math.max(1, trace.length - 1)) * (W - pad * 2);
  const y = (c) => H - pad - ((c - lo) / Math.max(1e-9, hi - lo)) * (H - pad * 2);
  const done = step >= last;

  return (
    <div className="theatre">
      <div className="theatre-head">
        <span className="eyebrow">
          <i className={"pulse" + (done ? " done" : "")} />
          {done ? "SEARCH COMPLETE" : "ENUMERATING CANDIDATE WINDOWS"}
        </span>
        <span className="theatre-count">
          <b>{seen.length}</b> / {trace.length} scored
          <small> · {result.candidates_considered} breakpoints</small>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="theatre-plot"
        role="img"
        aria-label={`Decision search: ${trace.length} feasible windows scored, best ${Math.round(best.carbon_g)} grams CO2 at ${best.start_iso}`}
      >
        <line x1={pad} y1={y(best.carbon_g)} x2={W - pad} y2={y(best.carbon_g)} className="theatre-bestline" />
        {trace.map((r, i) => {
          const state = i > step ? "pending" : r.start_iso === best.start_iso ? "best" : "rejected";
          return (
            <circle key={r.start_iso} cx={x(i)} cy={y(r.carbon_g)} r={state === "best" ? 4.2 : 2.1}
                    className={"theatre-dot " + state} />
          );
        })}
        <line x1={x(step)} y1={pad} x2={x(step)} y2={H - pad} className="theatre-cursor" />
      </svg>
      <div className="theatre-rows">
        {[...seen].slice(-3).reverse().map((r) => (
          <div key={r.start_iso}
               className={"theatre-row" + (r.start_iso === best.start_iso ? " best" : "")}>
            <span className="t-time">{time(r.start_iso)}</span>
            <span className="t-carbon">{fmt(r.carbon_g, 0)} g</span>
            <span className="t-tag">{r.breakpoint}</span>
            <span className="t-verdict">
              {r.start_iso === best.start_iso ? "★ best so far" : "rejected"}
            </span>
          </div>
        ))}
      </div>
      <div className="theatre-foot">
        <span>
          {done ? "OPTIMUM " : "BEST SO FAR "}
          <b>{time(best.carbon_g === current?.carbon_g ? current.start_iso : best.start_iso)} UTC</b>
          <small> · {best.breakpoint === "slot-end" ? "end-aligned breakpoint" : best.breakpoint === "now" ? "run now" : best.breakpoint}</small>
        </span>
        <button type="button" className="text-btn" onClick={() => setStep(0)}>
          <Icon name="refresh" size={13} /> Replay search
        </button>
      </div>
      {chosenIso && chosenIso !== best.start_iso && (
        <p className="theatre-note">
          You picked {time(chosenIso)} — {fmt(
            (trace.find((r) => r.start_iso === chosenIso)?.carbon_g ?? 0) - best.carbon_g, 0,
          )} g above the optimum, and still well under running now.
        </p>
      )}
    </div>
  );
}
function Composer({ onClose, onSubmit, regions = [], model, motion }) {
  // Open on a region that actually has a forecast: only GB is available in
  // operational mode, and the Indian grids only once scenario mode is started.
  const firstAvailable =
    regions.find((r) => r.available)?.id ?? "gb";
  const [form, setForm] = useState({
    name: "nightly-climate-model",
    energy_kwh: 12,
    duration_minutes: 60,
    deadline_hours: 12,
    workload: "hash_grind",
    home_region: firstAvailable, allowed_regions: [], allow_shift: false, forecast_method: "provider",
  });
  const [preview, setPreview] = useState(null);
  const [rec, setRec] = useState(null);
  const [chosen, setChosen] = useState(null); // null = accept the engine's own plan
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.focus();
    const handle = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const els = [
          ...document.querySelectorAll(
            ".modal button,.modal input,.modal select",
          ),
        ].filter((el) => !el.disabled);
        if (e.shiftKey && document.activeElement === els[0]) {
          e.preventDefault();
          els.at(-1).focus();
        } else if (!e.shiftKey && document.activeElement === els.at(-1)) {
          e.preventDefault();
          els[0].focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [onClose]);
  useEffect(() => {
    let live = true;
    const id = setTimeout(
      () =>
        api
          .previewJob(form)
          .then((d) => {
            if (live) {
              setPreview(d);
              api.recommendWindows(form).then((r) => { if (live) setRec(r); }).catch(() => {});
              setErr("");
            }
          })
          .catch((e) => {
            if (live) setErr(e.message);
          }),
      350,
    );
    return () => {
      live = false;
      clearTimeout(id);
    };
  }, [form]);
  const updateForm = (patch) => {
    setPreview(null);
    setRec(null);
    setChosen(null);
    setErr("");
    setForm((f) => ({ ...f, ...patch }));
  };
  const field = (k, v) => updateForm({[k]: v});
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="compose-title"
      >
        <div className="panel-head">
          <div>
            <span className="eyebrow">CARBON-AWARE COMPUTE</span>
            <h2 id="compose-title">Give your workload a cleaner window.</h2>
          </div>
          <button
            className="icon-btn"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await onSubmit(chosen ? { ...form, run_at_iso: chosen } : form);
              onClose();
            } catch (e) {
              setErr(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Workload name
            <input
              ref={ref}
              required
              maxLength="100"
              value={form.name}
              onChange={(e) => field("name", e.target.value)}
            />
          </label>
          <label>
            Real workload
            <select
              value={form.workload}
              onChange={(e) => field("workload", e.target.value)}
            >
              {Object.entries(names)
                .filter(([k]) => k !== "shell")
                .map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
            </select>
          </label>
          <details className="strategy-options"><summary>Region & forecast strategy</summary>
            <label>Home region<select aria-label="Home region" value={form.home_region} onChange={e=>updateForm({home_region:e.target.value,forecast_method:'provider'})}>{regions.map(r=><option key={r.id} value={r.id} disabled={!r.available}>{r.name}{!r.available?' — unavailable':''}</option>)}</select></label>
            <label>Forecast method<select value={form.forecast_method} onChange={e=>field('forecast_method',e.target.value)}><option value="provider">Available forecast / scenario</option><option value="learned" disabled={!model?.trained||form.home_region!=='gb'||form.allow_shift}>Trained GB model</option></select></label>
            <label><input type="checkbox" checked={form.allow_shift} onChange={e=>updateForm({allow_shift:e.target.checked,forecast_method:'provider'})}/> Allow regional SHIFT recommendations</label>
            {form.allow_shift&&regions.filter(r=>r.id!==form.home_region&&r.available).map(r=><label key={r.id}><input type="checkbox" checked={form.allowed_regions.includes(r.id)} onChange={e=>field('allowed_regions',e.target.checked?[...form.allowed_regions,r.id]:form.allowed_regions.filter(id=>id!==r.id))}/>{r.name}</label>)}
            <p className="fine-print">Every job executes locally. Regional emissions are counterfactual estimates using your declared energy.</p>
          </details>
          <div className="form-grid">
            <label>
              Estimated energy · kWh
              <input
                type="number"
                min="0.01"
                max="10000"
                step="0.01"
                required
                value={form.energy_kwh}
                onChange={(e) => field("energy_kwh", Number(e.target.value))}
              />
            </label>
            <label>
              Planning duration · min
              <input
                type="number"
                min="1"
                max="1440"
                required
                value={form.duration_minutes}
                onChange={(e) =>
                  field("duration_minutes", Number(e.target.value))
                }
              />
            </label>
          </div>
          <label>
            Complete within <b>{form.deadline_hours} hours</b>
            <input
              type="range"
              min="1"
              max="24"
              value={form.deadline_hours}
              onChange={(e) => field("deadline_hours", Number(e.target.value))}
            />
            <span className="range-labels">
              <span>Urgent · 1h</span>
              <span>Flexible · 24h</span>
            </span>
          </label>
          <div className="preview-box">
            <span className="eyebrow">LIVE SCHEDULING PREVIEW</span>
            {preview ? (
              <>
                <div>
                  <Badge tone="green">
                    {preview.action === "WAIT"
                      ? "DEFER TO " + time(preview.run_at_iso) + " UTC"
                      : preview.action === "SHIFT" ? "SHIFT TO " + preview.target_region + " · " + time(preview.run_at_iso) : "RUN NOW"}
                  </Badge>
                  <strong>
                    {fmt(preview.carbon_saved_pct, 1)}% <small>less CO₂</small>
                  </strong>
                </div>
                <p>
                  {preview.feasible_windows} feasible windows evaluated.{" "}
                  {fmt(preview.baseline_carbon_g / 1000, 2)} →{" "}
                  {fmt(preview.optimal_carbon_g / 1000, 2)} kg estimated CO₂.
                </p>
              </>
            ) : (
              <p>{err || "Evaluating the cleanest feasible window…"}</p>
            )}
          </div>
          {rec && (
            <div className="rec-box">
              <span className="eyebrow">OR PICK A WINDOW YOURSELF</span>
              {rec.options.length === 0 && (
                <p className="rec-hint">
                  No feasible window in this region for that deadline.
                </p>
              )}
              <ul className="rec-list">
                {rec.options.map((o) => {
                  const isNow = o.breakpoint === "now";
                  return (
                    <li key={o.start_iso}>
                      <button
                        type="button"
                        className={"rec-option" + (chosen === o.start_iso ? " active" : "")}
                        aria-pressed={chosen === o.start_iso}
                        onClick={() =>
                          setChosen((c) => (c === o.start_iso ? null : o.start_iso))
                        }
                      >
                        <span className="rec-when">
                          <b>{isNow ? "Run now" : time(o.start_iso) + " UTC"}</b>
                          <small>{o.label}</small>
                        </span>
                        <span className="rec-num rec-carbon">
                          <b>{isNow ? "—" : "−" + fmt(o.carbon_saved_pct, 1) + "%"}</b>
                          <small>CO\u2082</small>
                        </span>
                        <span className="rec-num">
                          <b>{isNow ? "now" : "+" + fmt(o.delay_hours, 1) + "h"}</b>
                          <small>delay</small>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <p className="rec-hint">
                {chosen
                  ? "This window is pinned; the scheduler will not re-optimise it."
                  : "Leave unselected to accept the plan above."}
              </p>
              <DecisionTheatre
                key={rec.now_iso + ":" + rec.candidates_considered}
                result={rec}
                motion={motion}
                chosenIso={chosen}
              />
            </div>
          )}
          <p className="fine-print">
            Energy and duration are planning inputs. The bounded CPU demo runs
            in seconds; carbon and cost are scenario estimates, not metered
            measurements.
          </p>
          {err && (
            <p role="alert" className="error-text">
              {err}
            </p>
          )}
          <button
            className="btn primary wide"
            disabled={busy || !preview}
            type="submit"
          >
            {busy ? "Scheduling…" : "Schedule workload"}
            <Icon name="arrow" />
          </button>
        </form>
      </section>
    </div>
  );
}
export default function App() {
  const [motion, setMotion] = useState(
    () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [state, setState] = useState(null),
    [error, setError] = useState(""),
    [connectionError, setConnectionError] = useState(""),
    [selected, setSelected] = useState(null),
    [tab, setTabState] = useState(readPage),
    [horizon, setHorizon] = useState(24),
    [modal, setModal] = useState(false),
    [busy, setBusy] = useState(false),
    [filter, setFilter] = useState("All workloads"),
    [search, setSearch] = useState(""),
    [toast, setToast] = useState("");
  const poll = useCallback(async () => {
    try {
      const s = await api.getState();
      setState(s);
      setConnectionError("");
      setSelected((old) =>
        s.jobs.some((j) => j.id === old)
          ? old
          : (s.jobs.find((j) => s.decisions[j.id]?.action === "WAIT")?.id ??
            s.jobs[0]?.id ??
            null),
      );
    } catch (e) {
      setConnectionError(e.message);
    }
  }, []);
  useEffect(() => {
    let stop = false;
    let timer;
    const loop = async () => {
      await poll();
      if (!stop) timer = setTimeout(loop, 1500);
    };
    loop();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [poll]);
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(""), 4000);
      return () => clearTimeout(id);
    }
  }, [toast]);
  const act = async (fn, message) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await poll();
      if (message) setToast(message);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const [inspecting, setInspecting] = useState(false);
  const setTab = useCallback((name) => {
    window.location.hash = "/" + PAGES[name];
    setTabState(name);
    setInspecting(false);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);
  useEffect(() => {
    const sync = () => {
      setTabState(readPage());
      setInspecting(false);
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const closeModal = useCallback(() => setModal(false), []);
  if (!state)
    return (
      <div className="connecting">
        <div className="brand-mark">
          <Icon name="bolt" size={34} />
        </div>
        <h1>
          ECO<span>ARB</span>
        </h1>
        <p>
          {connectionError
            ? "Waiting for the local scheduler. Start the app with start.ps1."
            : "Connecting to your carbon-aware control room…"}
        </p>
        <button className="btn" onClick={poll}>
          Retry connection
        </button>
      </div>
    );
  const jobs = state.jobs,
    decision = state.decisions[selected],
    job = jobs.find((j) => j.id === selected),
    grid = state.grid.now,
    totals = state.totals;
  const pending = jobs.filter((j) => ["QUEUED", "WAITING"].includes(j.status));
  const potential = pending.reduce(
    (v, j) =>
      v +
      Math.max(
        0,
        (state.decisions[j.id]?.baseline_carbon_g ?? 0) -
          (state.decisions[j.id]?.optimal_carbon_g ?? 0),
      ),
    0,
  );
  const visible = jobs.filter(
    (j) =>
      (filter === "All workloads" || j.status === filter) &&
      j.name.toLowerCase().includes(search.toLowerCase()),
  );
  const mode = state.data_mode === "scenario" ? "Synthetic scenario" : state.clock.compressed
    ? "Forecast replay"
    : state.grid.status.live
      ? "Live forecast"
      : state.grid.status.cached
        ? "Cached forecast"
        : "Offline fallback";
  return (
    <div className={"app-shell " + (motion ? "motion-on" : "motion-off")}>
      <EnergyField active={motion} />
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          aria-label="ECO ARB home"
          onClick={(e) => {
            e.preventDefault();
            setTab("Overview");
          }}
        >
          <span className="brand-mark">
            <Icon name="bolt" size={25} />
          </span>
          <span>
            ECO<span className="brand-light">ARB</span>
            <small>COMPUTE WITH THE GRID.</small>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-avatar">E</span>
          <div>
            ECO-ARB workspace<small>VINHACK / Climate tech</small>
          </div>
          <span className="workspace-dot" />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {[
            ["Overview", "grid"],
            ["Grid", "chart"],
            ["Regions", "grid"],
            ["Intelligence", "bolt"],
            ["Workloads", "layers"],
            ["Impact", "leaf"],
            ["Activity", "activity"],
            ["Simulation", "clock"],
          ].map(([name, icon]) => (
            <button
              key={name}
              className={tab === name ? "nav-item active" : "nav-item"}
              aria-current={tab === name ? "page" : undefined}
              title={name}
              onClick={() => setTab(name)}
            >
              <Icon name={icon} />
              {name}
              {name === "Workloads" && (
                <span className="nav-count">{jobs.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="mission-card">
            <Icon name="leaf" />
            <h3>
              Small shifts.
              <br />
              Lighter footprints.
            </h3>
            <p>Let flexible compute follow cleaner electricity.</p>
            <div className="mission-bars">
              {[20, 35, 28, 46, 39, 58, 48, 67, 61, 80, 73, 95].map((h, i) => (
                <i key={i} style={{ height: h + "%" }} />
              ))}
            </div>
          </div>
          <div className="system">
            <i className={connectionError ? "dot warning" : "dot"} />
            <span>
              {connectionError
                ? "Connection interrupted"
                : "Scheduler connected"}
              <small>Local compute · UTC</small>
            </span>
            <Icon name="info" size={15} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            Workspace <span>/</span>
            <b>{tab}</b>
          </div>
          <div className="top-actions">
            <button
              className="motion-toggle"
              onClick={() => setMotion((v) => !v)}
              aria-pressed={motion}
              aria-label={
                motion ? "Pause visual motion" : "Enable visual motion"
              }
            >
              <Icon name="activity" size={14} />
              <span>Motion {motion ? "on" : "off"}</span>
            </button>
            <Badge
              tone={
                state.grid.status.live && !state.clock.compressed
                  ? "green"
                  : "amber"
              }
            >
              {mode}
            </Badge>
            <span className="clock">
              <Icon name="clock" size={14} />
              {time(state.clock.virtual_iso)} UTC
            </span>
            <span className="avatar">EA</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="tiny-line" /> AUTONOMOUS CARBON ARBITRAGE
              </div>
              <h1>
                {
                  {
                    Overview: "Your climate control room.",
                    Grid: "Follow the clean energy.",
                    Workloads: "Give your compute a cleaner window.",
                    Impact: "Make the shift count.",
                    Activity: "Every decision, in the open.",
                    Simulation: "Bring the demo to life.",
                    Regions: "Explore the regional decision.",
                    Intelligence: "See what the model learns.",
                  }[tab]
                }
              </h1>
              <p>
                {
                  {
                    Overview: "A little flexibility. A lighter footprint.",
                    Grid: "Explore carbon forecasts before you schedule.",
                    Regions: "Compare forecast sources and their availability.",
                    Intelligence: "Train, evaluate, and inspect a seasonal forecast.",
                    Workloads:
                      "Manage your queue. Select a job to inspect its decision.",
                    Impact:
                      "Trace estimated savings back to completed workloads.",
                    Activity:
                      "A complete timeline of scheduling and execution.",
                    Simulation:
                      "Control the demo clock and refresh your grid source.",
                  }[tab]
                }
              </p>
            </div>
            <div className="heading-actions">
              {tab === "Simulation" && (
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() =>
                    act(api.seedDemo, "Three demo workloads scheduled")
                  }
                >
                  <Icon name="bolt" size={16} />
                  Load demo
                </button>
              )}
              {["Overview", "Workloads"].includes(tab) && (
                <button className="btn primary" onClick={() => setModal(true)}>
                  <Icon name="plus" size={17} />
                  New workload
                </button>
              )}
            </div>
          </div>
          {(error || connectionError) && (
            <div className="error-banner" role="alert">
              {error ||
                "Connection lost. Displaying the last received state. " +
                  connectionError}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                ×
              </button>
            </div>
          )}
          {tab === "Overview" && (
            <EnergyStage
              intensity={grid.intensity_gco2_kwh}
              mode={mode}
              pending={pending.length}
              running={jobs.filter((j) => j.status === "RUNNING").length}
            />
          )}
          {tab === "Overview" && (
            <>
              <div className="metrics overview-metrics">
                <div className="metric">
                  <div className="metric-label">
                    Grid carbon intensity
                    <Icon name="activity" />
                  </div>
                  <div className="metric-value">
                    {fmt(grid.intensity_gco2_kwh)}
                    <small>gCO₂/kWh</small>
                  </div>
                  <div className="metric-foot">
                    <span>{mode}</span>
                  </div>
                </div>
                <div className="metric">
                  <div className="metric-label">
                    Estimated CO₂ avoided
                    <Icon name="leaf" />
                  </div>
                  <div className="metric-value">
                    {fmt(totals.carbon_saved_g / 1000, 2)}
                    <small>kg CO₂</small>
                  </div>
                  <div className="metric-foot">
                    <span>Completed workloads only</span>
                  </div>
                </div>
                <div className="metric">
                  <div className="metric-label">
                    Workloads completed
                    <Icon name="layers" />
                  </div>
                  <div className="metric-value">
                    {totals.jobs_completed}
                    <small>/ {jobs.length} submitted</small>
                  </div>
                  <div className="metric-foot">
                    <span>{pending.length} waiting for their window</span>
                  </div>
                </div>
              </div>
              <div className="page-shortcuts">
                {[
                  [
                    "Grid",
                    "chart",
                    "Explore the forecast",
                    "Find your next cleaner window.",
                  ],
                  [
                    "Workloads",
                    "layers",
                    "Manage workloads",
                    pending.length +
                      " pending · " +
                      fmt(potential / 1000, 2) +
                      " kg projected avoidance.",
                  ],
                  [
                    "Impact",
                    "leaf",
                    "See your impact",
                    "From completed work to estimated savings.",
                  ],
                ].map(([page, icon, title, description]) => (
                  <button
                    className="page-shortcut"
                    key={page}
                    onClick={() => setTab(page)}
                  >
                    <span className="shortcut-icon">
                      <Icon name={icon} />
                    </span>
                    <span>
                      <strong>{title}</strong>
                      <small>{description}</small>
                    </span>
                    <Icon name="arrow" size={16} />
                  </button>
                ))}
              </div>
            </>
          )}
          {tab === "Grid" && (
            <div className="grid-page">
              <div className="grid-selection">
                <label>
                  Highlight a workload window
                  <select
                    value={selected ?? ""}
                    onChange={(e) => setSelected(e.target.value || null)}
                  >
                    <option value="">No workload selected</option>
                    {jobs.map((j) => (
                      <option key={j.id} value={j.id}>
                        {j.name} · {j.id}
                      </option>
                    ))}
                  </select>
                </label>
                <span>
                  <Badge tone="green">{mode}</Badge>{" "}
                  <small>All times UTC</small>
                </span>
              </div>
              <Forecast
                slots={state.grid.forecast}
                decision={decision}
                horizon={horizon}
                setHorizon={setHorizon}
              />
              <p className="page-note">
                Carbon intensity is a forecast. Renewable share and price are
                derived estimates.{" "}
                <button
                  className="text-btn"
                  onClick={() => setTab("Simulation")}
                >
                  Grid source & demo controls <Icon name="arrow" size={14} />
                </button>
              </p>
            </div>
          )}
          {tab === "Workloads" && (
            <Panel
              title="Workload orchestration"
              kicker="COMPUTE, ON YOUR TERMS"
              extra={
                <div className="queue-tools">
                  <select
                    aria-label="Filter workloads"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    {[
                      "All workloads",
                      "WAITING",
                      "RUNNING",
                      "DONE",
                      "FAILED",
                      "MISSED",
                    ].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                  {tab === "Workloads" && (
                    <input
                      aria-label="Search workloads"
                      placeholder="Search workloads…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  )}
                </div>
              }
              className="queue"
            >
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>WORKLOAD</th>
                      <th>STATUS</th>
                      <th>ENERGY BUDGET</th>
                      <th>EXECUTION WINDOW</th>
                      <th>EST. CO₂ REDUCTION</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((j) => (
                      <tr
                        key={j.id}
                        className={selected === j.id ? "selected" : ""}
                      >
                        <td>
                          <button
                            className="job-select"
                            onClick={() => {
                              setSelected(j.id);
                              setInspecting(true);
                            }}
                          >
                            <span className="job-icon">
                              <Icon
                                name={
                                  j.workload === "matrix_train"
                                    ? "grid"
                                    : "layers"
                                }
                                size={17}
                              />
                            </span>
                            <span>
                              {j.name}
                              <small>
                                {j.id} · {names[j.workload]}
                              </small>
                            </span>
                          </button>
                        </td>
                        <td>
                          <Badge
                            tone={
                              j.status === "DONE"
                                ? "green"
                                : j.status === "RUNNING"
                                  ? "blue"
                                  : j.status === "FAILED" ||
                                      j.status === "MISSED"
                                    ? "red"
                                    : "amber"
                            }
                          >
                            {j.status === "WAITING" ? state.decisions[j.id]?.action === "SHIFT" ? "SHIFT PLANNED" : "DEFERRED" : j.status}
                          </Badge>
                          {j.status === "RUNNING" && (
                            <progress value={j.progress} max="1" />
                          )}
                        </td>
                        <td>
                          {fmt(j.energy_kwh, 2)}{" "}
                          <span className="muted">kWh</span>
                        </td>
                        <td>
                          {time(
                            j.run_at_iso ?? state.decisions[j.id]?.run_at_iso,
                          )}{" "}
                          <span className="muted">UTC</span>
                          <small className="cell-sub">
                            Due {time(j.deadline_iso)}
                          </small>
                        </td>
                        <td className="green-text">
                          {fmt(
                            j.status === "DONE"
                              ? state.impacts?.[j.id]?.saved_pct
                              : state.decisions[j.id]?.carbon_saved_pct,
                            1,
                          )}
                          %
                          <small className="cell-sub">
                            {j.status === "DONE"
                              ? "Completed - estimated"
                              : "Planning estimate"}
                          </small>
                        </td>
                        <td>
                          {j.status === "DONE" ? (
                            <button
                              className="icon-btn"
                              aria-label={"Download proof for " + j.name}
                              onClick={() =>
                                act(
                                  async () =>
                                    download(
                                      await api.getArtifact(j.id),
                                      j.id + "-proof.json",
                                    ),
                                  "Execution proof downloaded",
                                )
                              }
                            >
                              <Icon name="download" size={16} />
                            </button>
                          ) : ["QUEUED", "WAITING"].includes(j.status) ? (
                            <button
                              className="icon-btn"
                              aria-label={"Cancel " + j.name}
                              disabled={busy}
                              onClick={() =>
                                act(
                                  () => api.cancelJob(j.id),
                                  "Workload cancelled",
                                )
                              }
                            >
                              <Icon name="close" size={15} />
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!visible.length && (
                  <div className="empty">
                    <Icon name="layers" size={30} />
                    <h3>
                      {jobs.length
                        ? "No matching workloads"
                        : "Your next workload can run cleaner."}
                    </h3>
                    <p>
                      {jobs.length
                        ? "Try another status or search."
                        : "Load the demo or schedule your first workload to see the engine in action."}
                    </p>
                    {!jobs.length && (
                      <button
                        className="btn"
                        onClick={() => act(api.seedDemo, "Demo loaded")}
                        disabled={busy}
                      >
                        Load three demo workloads
                        <Icon name="arrow" size={15} />
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div className="table-footer">
                <span>
                  <i className="dot" /> {pending.length} pending ·{" "}
                  {totals.jobs_completed} completed
                </span>
                <span>Click a workload to inspect its decision</span>
              </div>
            </Panel>
          )}
          {tab === "Regions" && <Regions regions={state.regions || []} mode={state.data_mode} Forecast={Forecast} nowIso={state.clock.virtual_iso} onUpdate={poll}/>}
          {tab === "Intelligence" && <Intelligence model={state.model} onUpdate={poll}/>}
          {tab === "Impact" && <p className="region-disclosure">Counterfactual estimates using declared energy and forecast intensity. All work executes locally; electricity consumption and geographic carbon savings are not measured. Synthetic jobs retain their scenario labels in receipts.</p>}
          {tab === "Impact" && (
            <div className="impact-layout">
              <Panel
                title="From intention to evidence."
                kicker="COMPLETED WORKLOAD IMPACT"
              >
                <div className="impact-hero">
                  <Icon name="leaf" size={48} />
                  <strong>
                    {fmt(totals.carbon_saved_g / 1000, 3)}
                    <small>kg CO₂ avoided · estimated</small>
                  </strong>
                  <p>
                    Compared with running the same energy budget immediately at
                    submission.
                  </p>
                </div>
                <div className="impact-stats">
                  <div>
                    <span>Estimated emissions</span>
                    <strong>{fmt(totals.carbon_emitted_g / 1000, 3)} kg</strong>
                  </div>
                  <div>
                    <span>Modelled cost saving</span>
                    <strong>£{fmt(totals.cost_saved_gbp, 2)}</strong>
                  </div>
                  <div>
                    <span>Completed energy budgets</span>
                    <strong>{fmt(totals.energy_scheduled_kwh, 2)} kWh</strong>
                  </div>
                </div>
                <button
                  className="btn export"
                  onClick={() =>
                    download(
                      {
                        exported_at: new Date().toISOString(),
                        methodology:
                          "Counterfactual estimates from declared energy and recommended-region forecasts. All work executes locally; no metered electricity or verified regional avoidance. Completed jobs only. Per-job receipts retain data mode and forecast inputs.",
                        totals,
                        impacts: state.impacts,
                        jobs: jobs.filter((j) => j.status === "DONE"),
                        provenance: state.grid.provenance,
                      },
                      "eco-arb-impact.json",
                    )
                  }
                >
                  <Icon name="download" />
                  Export impact report
                </button>
              </Panel>
              <Panel
                title="Know what the numbers mean."
                kicker="TRANSPARENT BY DESIGN"
              >
                <div className="methodology">
                  {[
                    [
                      "01",
                      "Real execution",
                      "Bounded SHA-256 or matrix workloads run on the host CPU and write downloadable artifacts.",
                    ],
                    [
                      "02",
                      "Estimated impact",
                      "Your declared kWh budget is multiplied by duration-weighted forecast intensity. No power meter is connected.",
                    ],
                    [
                      "03",
                      "A fixed comparison",
                      "The immediate-execution baseline is frozen when each job is submitted. Only completed jobs enter the impact totals.",
                    ],
                    [
                      "04",
                      "Honest grid signals",
                      "UK provider, imported, learned and synthetic signals carry separate labels. Indian demo values are assumptions. Prices are modelled, and regional SHIFT executes locally.",
                    ],
                  ].map(([n, t, d]) => (
                    <div key={n}>
                      <span>{n}</span>
                      <article>
                        <h3>{t}</h3>
                        <p>{d}</p>
                      </article>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          )}
          {tab === "Activity" && (
            <div className="activity-page">
              {" "}
              <Panel
                title="Scheduler activity"
                extra={
                  <span className="live-label">
                    <i className="dot" />
                    AUTO-UPDATING
                  </span>
                }
              >
                <div
                  className={
                    "activity-list " + (tab === "Activity" ? "full" : "")
                  }
                >
                  {state.logs
                    .slice(tab === "Activity" ? -100 : -4)
                    .reverse()
                    .map((l, i) => (
                      <div className="log" key={l.ts_iso + i}>
                        <span className={"log-dot " + l.level} />
                        <time>{time(l.virtual_iso)}</time>
                        <span>{l.text}</span>
                        <b>{l.level}</b>
                      </div>
                    ))}
                </div>
              </Panel>
            </div>
          )}
          {tab === "Simulation" && (
            <div className="simulation-page">
              <section className="panel learning-intro"><span className="eyebrow">SELF-CONTAINED DEMONSTRATION</span><h2>Three decisions. Real local computation.</h2><p>Start a labelled synthetic RUN / WAIT / SHIFT scenario at 360×. The Indian regional values are assumptions, and no workload moves to a remote cloud.</p><div className="learning-actions"><button className="btn primary" disabled={busy} onClick={()=>act(api.startScenario,"Guided scenario started")}>Start guided scenario</button><button className="btn" disabled={busy} onClick={()=>{if(window.confirm('Clear all session jobs and reset the clock? Running work must finish first.'))act(api.resetAll,'Session reset')}}>Reset session</button></div><p className="fine-print">Finish or cancel pending workloads before starting. The WAIT job becomes eligible after roughly 20 seconds of wall time.</p></section>
              {" "}
              <Panel title="Grid & simulation" extra={<Icon name="activity" />}>
                <div className="grid-controls">
                  <div>
                    <span>Demo clock</span>
                    <div className="segmented">
                      {state.clock.allowed_speeds.map((s) => (
                        <button
                          disabled={busy}
                          key={s}
                          className={s === state.clock.speed ? "active" : ""}
                          onClick={() => act(() => api.setSpeed(s))}
                        >
                          {s}×
                        </button>
                      ))}
                    </div>
                  </div>
                  <p>
                    {state.clock.compressed
                      ? "Accelerated forecast replay. CPU workloads still execute at real speed."
                      : "Real-time clock. Increase speed to demonstrate deferred execution."}
                  </p>
                  <div className="grid-models">
                    <span>
                      Renewables{" "}
                      <b>
                        {fmt(grid.renewable_pct, 1)}% <small>derived</small>
                      </b>
                    </span>
                    <span>
                      Energy price{" "}
                      <b>
                        £{fmt(grid.price, 2)} <small>/MWh · modelled</small>
                      </b>
                    </span>
                  </div>
                  <button
                    className="text-btn"
                    disabled={busy}
                    onClick={() =>
                      act(api.refreshGrid, "Grid refresh completed")
                    }
                  >
                    <Icon name="refresh" size={14} />
                    Refresh grid feed
                  </button>
                </div>
              </Panel>
              <Panel title="A quick demo, at your pace." kicker="HOW IT WORKS">
                <ol className="demo-steps">
                  <li>
                    <strong>Load three workloads.</strong>
                    <p>Explore an urgent job and two flexible compute tasks.</p>
                  </li>
                  <li>
                    <strong>Watch time move.</strong>
                    <p>
                      At 360×, one forecast hour passes in ten seconds. CPU work
                      still runs at real speed.
                    </p>
                  </li>
                  <li>
                    <strong>Follow the result.</strong>
                    <p>
                      Open Workloads to watch execution, then Impact to inspect
                      completed-job estimates.
                    </p>
                  </li>
                </ol>
                <button
                  className="btn demo-link"
                  onClick={() => setTab("Workloads")}
                >
                  Go to workloads
                  <Icon name="arrow" size={15} />
                </button>
              </Panel>
            </div>
          )}
          <footer>
            <span>
              <Icon name="leaf" size={13} /> ECO-ARB · Built for a lighter
              footprint.
            </span>
            <span>Labelled grid data · Local execution · Estimated impact</span>
          </footer>
        </main>
      </div>
      {inspecting && (
        <DetailDialog onClose={() => setInspecting(false)}>
          {" "}
          <Panel
            title="Timing is everything."
            kicker="ARBITRAGE ENGINE"
            extra={
              <span className="engine-icon">
                <Icon name="bolt" />
              </span>
            }
            className="decision"
          >
            <div className="decision-status">
              <Badge tone="green">
                {job?.status === "DONE"
                  ? "EXECUTION COMPLETE"
                  : decision
                    ? decision.action === "WAIT"
                      ? "CLEANER WINDOW FOUND"
                      : decision.action === "SHIFT" ? "REGION SHIFT RECOMMENDED" : "READY TO EXECUTE"
                    : "ENGINE READY"}
              </Badge>
            </div>
            <div className="decision-main">
              {job?.status === "DONE"
                ? "Execution complete."
                : decision
                  ? decision.action === "WAIT"
                    ? "Wait for greener."
                    : decision.action === "SHIFT" ? "A cleaner region." : "The time is now."
                  : "A little flexibility.\nA lot of possibility."}
            </div>
            <p>
              {job
                ? job.name
                : "Submit a workload to find its cleanest execution window."}
            </p>
            {decision ? (
              <>
                <div className="saving-number">
                  {fmt(
                    job?.status === "DONE"
                      ? state.impacts?.[selected]?.saved_pct
                      : decision.carbon_saved_pct,
                    1,
                  )}
                  <span>%</span>
                  <small>
                    {job?.status === "DONE"
                      ? "estimated completed-job reduction"
                      : "potential carbon reduction"}
                  </small>
                </div>
                <div className="decision-details">
                  <div><span>Region recommendation</span><b>{decision.source_region} → {decision.target_region}</b></div>
                  <div><span>Data basis</span><b>{decision.data_basis}</b></div>
                  <p className="fine-print">Real computation runs locally. Energy is declared; regional emissions are counterfactual estimates.</p>
                  <div>
                    <span>Scheduled start</span>
                    <b>{time(decision.run_at_iso)} UTC</b>
                  </div>
                  <div>
                    <span>Feasible windows</span>
                    <b>{decision.feasible_windows}</b>
                  </div>
                  <div>
                    <span>Estimated cost change</span>
                    <b>
                      {decision.cost_saved_pct >= 0 ? "−" : "+"}
                      {fmt(Math.abs(decision.cost_saved_pct), 1)}%
                    </b>
                  </div>
                </div>
                <details>
                  <summary>Why this decision?</summary>
                  <p>{decision.reason}</p>
                </details>
              </>
            ) : (
              <div className="orbit">
                <div />
                <Icon name="leaf" size={40} />
              </div>
            )}
            <div className="engine-footer">
              <span className="dot" />
              Carbon-first · deadline-constrained
            </div>
          </Panel>
        </DetailDialog>
      )}
      {modal && (
        <Composer
          regions={state.regions} model={state.model} motion={motion}
          onClose={closeModal}
          onSubmit={async (f) => {
            await api.createJob(f);
            await poll();
            setTab("Workloads");
            setToast("Workload scheduled");
          }}
        />
      )}
      {toast && (
        <div className="toast" role="status">
          <Icon name="check" />
          {toast}
        </div>
      )}
    </div>
  );
}
