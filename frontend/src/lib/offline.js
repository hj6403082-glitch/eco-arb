import recordedIndia from "../data/india_recorded.json";
/* In-browser stand-in for the FastAPI backend.
 *
 * Used only when no backend answers — a static deployment (GitHub Pages), or a
 * dropped local server. It is a faithful port of backend/app: the same
 * synthetic curve (carbon.py), the same breakpoint-enumerating engine
 * (engine.py), the same state payload (main.py). The decision numbers it
 * produces are identical to the server's for the same inputs.
 *
 * Two things stay real here rather than being faked:
 *   - the forecast is pulled from the live UK Carbon Intensity API, which is
 *     CORS-open, so a hosted page shows the same data the server would;
 *   - hash_grind burns actual CPU through WebCrypto and the artifact is
 *     recomputed from its seed to verify, exactly as the server does.
 */

const SLOT_MINUTES = 30;
const SLOTS_PER_DAY = 48;
const HORIZON_HOURS = 24;
const MIN_SAVING_PCT = 1.0;
const ALLOWED_SPEEDS = [1, 60, 360];
const PRICE_FLOOR = 35.0, PRICE_CEIL = 190.0;
const REN_AT_ZERO = 95.0, REN_AT_MAX = 5.0, CALIB_MAX = 400.0;
const LOG_RING = 200;
const SLOT_MS = SLOT_MINUTES * 60000;

const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const halfHourOfDay = (ms) => { const d = new Date(ms); return Math.floor((d.getUTCHours() * 60 + d.getUTCMinutes()) / SLOT_MINUTES); };
const floorToSlot = (ms) => Math.floor(ms / SLOT_MS) * SLOT_MS;
const round = (v, n) => { const f = 10 ** n; return Math.round(v * f) / f; };

function syntheticDayProfile() {
  const p = {};
  for (let hh = 0; hh < SLOTS_PER_DAY; hh++) {
    const hour = (hh * SLOT_MINUTES) / 60;
    const v = 210
      - 70 * Math.exp(-((hour - 3) ** 2) / 8)
      - 55 * Math.exp(-((hour - 13) ** 2) / 6)
      + 95 * Math.exp(-((hour - 18.5) ** 2) / 3.5)
      + 30 * Math.exp(-((hour - 8) ** 2) / 2.5);
    p[hh] = round(Math.max(20, v), 1);
  }
  return p;
}
const deriveRenewablePct = (i) =>
  round(REN_AT_ZERO - (REN_AT_ZERO - REN_AT_MAX) * Math.min(Math.max(i / CALIB_MAX, 0), 1), 1);
function modelPrice(intensity, startMs) {
  const frac = Math.min(Math.max(intensity / CALIB_MAX, 0), 1);
  const scarcity = PRICE_FLOOR + (PRICE_CEIL - PRICE_FLOOR) * frac;
  const d = new Date(startMs);
  const hour = d.getUTCHours() + d.getUTCMinutes() / 60;
  return round(scarcity * (1 + 0.18 * Math.exp(-((hour - 18) ** 2) / 6)), 2);
}

/* ---------- decision engine: a direct port of backend/app/engine.py ---------- */
function scoreWindow(slots, startMs, durationMinutes, energyKwh) {
  const endMs = startMs + durationMinutes * 60000;
  if (!slots.length || endMs > slots[slots.length - 1].t + SLOT_MS) return null;
  let carbon = 0, cost = 0, covered = 0;
  for (const s of slots) {
    const slotEnd = s.t + SLOT_MS;
    if (slotEnd <= startMs) continue;
    if (s.t >= endMs) break;
    const minutes = Math.max(0, (Math.min(endMs, slotEnd) - Math.max(startMs, s.t)) / 60000);
    if (minutes <= 0) continue;
    const share = minutes / durationMinutes;
    covered += minutes;
    carbon += energyKwh * share * s.intensity;
    cost += (energyKwh * share * s.price) / 1000;
  }
  if (covered + 1e-6 < durationMinutes) return null;
  return [carbon, cost];
}

function decide(job, slots, nowMs) {
  const deadline = Date.parse(job.deadline_iso);
  const durMs = job.duration_minutes * 60000;

  // Candidates: now, every slot top, and — because carbon over a fixed window
  // is piecewise-LINEAR in start time — every start whose END lands on a slot
  // edge, plus the last feasible start. Missing the end-aligned ones can put
  // the search 75% off the true optimum.
  const candidates = [nowMs];
  for (const s of slots) if (s.t > nowMs) candidates.push(s.t);
  for (const s of slots) { const ea = s.t - durMs; if (ea > nowMs) candidates.push(ea); }
  const latest = deadline - durMs;
  if (latest >= nowMs) candidates.push(latest);

  const base = scoreWindow(slots, nowMs, job.duration_minutes, job.energy_kwh);
  if (!base) {
    return { job_id: job.id, action: "RUN", run_at_iso: iso(nowMs), carbon_saved_pct: 0, cost_saved_pct: 0,
      reason: "Forecast horizon does not cover this job's duration; running now.",
      baseline_carbon_g: 0, optimal_carbon_g: 0, baseline_cost_gbp: 0, optimal_cost_gbp: 0,
      window_end_iso: iso(nowMs + durMs), decided_at_iso: iso(nowMs),
      slots_considered: slots.length, feasible_windows: 0 };
  }
  const [baseCarbon, baseCost] = base;
  let bestStart = nowMs, bestCarbon = baseCarbon, bestCost = baseCost, feasible = 0;
  for (const start of [...new Set(candidates)].sort((a, b) => a - b)) {
    if (start + durMs > deadline) continue;
    const scored = scoreWindow(slots, start, job.duration_minutes, job.energy_kwh);
    if (!scored) continue;
    feasible++;
    if (scored[0] < bestCarbon - 1e-9) { bestCarbon = scored[0]; bestCost = scored[1]; bestStart = start; }
  }
  const deadlineBinding = nowMs + durMs >= deadline - SLOT_MS;
  let carbonSavedPct = baseCarbon > 0 ? ((baseCarbon - bestCarbon) / baseCarbon) * 100 : 0;
  let costSavedPct = baseCost > 0 ? ((baseCost - bestCost) / baseCost) * 100 : 0;
  let action, runAt, reason;

  if (bestStart <= nowMs || carbonSavedPct < MIN_SAVING_PCT) {
    action = "RUN"; runAt = nowMs;
    bestCarbon = baseCarbon; bestCost = baseCost; carbonSavedPct = 0; costSavedPct = 0;
    reason = deadlineBinding
      ? `Deadline at ${job.deadline_iso} leaves no room to defer a ${job.duration_minutes.toFixed(0)}-minute job. Running now.`
      : `Grid is already near its cleanest reachable point (${slots[0].intensity.toFixed(0)} gCO2/kWh); no window before the deadline beats running now by more than ${MIN_SAVING_PCT.toFixed(0)}%.`;
  } else {
    action = "WAIT"; runAt = bestStart;
    const delayH = (bestStart - nowMs) / 3600000;
    const avgNow = job.energy_kwh ? baseCarbon / job.energy_kwh : 0;
    const avgThen = job.energy_kwh ? bestCarbon / job.energy_kwh : 0;
    reason = `Deferring ${delayH.toFixed(1)}h to ${iso(bestStart)} moves the job from ~${avgNow.toFixed(0)} to ~${avgThen.toFixed(0)} gCO2/kWh average intensity, cutting ${(baseCarbon - bestCarbon).toFixed(0)} gCO2 (${carbonSavedPct.toFixed(1)}%). Deadline ${job.deadline_iso} still met.`;
  }
  return { job_id: job.id, action, run_at_iso: iso(runAt),
    carbon_saved_pct: round(carbonSavedPct, 2), cost_saved_pct: round(costSavedPct, 2), reason,
    baseline_carbon_g: round(baseCarbon, 1), optimal_carbon_g: round(bestCarbon, 1),
    baseline_cost_gbp: round(baseCost, 4), optimal_cost_gbp: round(bestCost, 4),
    window_end_iso: iso(runAt + durMs), decided_at_iso: iso(nowMs),
    slots_considered: slots.length, feasible_windows: feasible };
}

/* ---------- ranked recommendations: a port of engine.recommend ---------- */
function candidateStarts(job, slots, nowMs) {
  const durMs = job.duration_minutes * 60000;
  const tagged = new Map([[nowMs, "now"]]);
  for (const s of slots) if (s.t > nowMs && !tagged.has(s.t)) tagged.set(s.t, "slot-start");
  for (const s of slots) { const ea = s.t - durMs; if (ea > nowMs && !tagged.has(ea)) tagged.set(ea, "slot-end"); }
  const latest = Date.parse(job.deadline_iso) - durMs;
  if (latest >= nowMs && !tagged.has(latest)) tagged.set(latest, "deadline");
  return [...tagged.entries()].sort((a, b) => a[0] - b[0]);
}

function evaluateCandidates(job, slots, nowMs) {
  const deadline = Date.parse(job.deadline_iso);
  const durMs = job.duration_minutes * 60000;
  const base = scoreWindow(slots, nowMs, job.duration_minutes, job.energy_kwh);
  const [baseCarbon, baseCost] = base || [0, 0];
  return candidateStarts(job, slots, nowMs).map(([start, why]) => {
    const feasible = start + durMs <= deadline;
    const scored = feasible ? scoreWindow(slots, start, job.duration_minutes, job.energy_kwh) : null;
    const row = { start_iso: iso(start), end_iso: iso(start + durMs), breakpoint: why,
      feasible: Boolean(scored), delay_hours: round((start - nowMs) / 3600000, 2) };
    if (scored) {
      row.carbon_g = round(scored[0], 1);
      row.cost_gbp = round(scored[1], 4);
      row.carbon_saved_pct = round(baseCarbon > 0 ? ((baseCarbon - scored[0]) / baseCarbon) * 100 : 0, 2);
      row.cost_saved_pct = round(baseCost > 0 ? ((baseCost - scored[1]) / baseCost) * 100 : 0, 2);
      row.avg_intensity = job.energy_kwh ? round(scored[0] / job.energy_kwh, 1) : 0;
    } else {
      Object.assign(row, { carbon_g: null, cost_gbp: null, carbon_saved_pct: null,
                           cost_saved_pct: null, avg_intensity: null });
    }
    return row;
  });
}

function rankWindows(job, slots, nowMs, limit = 4, spacingMinutes = 20, minGapPct = 1) {
  const trace = evaluateCandidates(job, slots, nowMs);
  const feasible = trace.filter((r) => r.feasible);
  const runNow = trace.find((r) => r.breakpoint === "now" && r.feasible) || null;
  const ceiling = runNow ? runNow.carbon_g : null;
  // Without a feasible window at "now" there is no baseline, so savings are
  // undefined rather than zero: rank on absolute carbon and separate options by
  // that, or every row reads "0.0%" and the list collapses to one entry.
  const hasBaseline = Boolean(runNow) && runNow.carbon_g > 0;
  const bestCarbon = feasible.length ? Math.min(...feasible.map((r) => r.carbon_g)) || 1 : 1;
  const tooClose = (row, chosen) => hasBaseline
    ? Math.abs(row.carbon_saved_pct - chosen.carbon_saved_pct) < minGapPct
    : Math.abs(row.carbon_g - chosen.carbon_g) < (bestCarbon * minGapPct) / 100;
  const picked = [];
  for (const row of [...feasible].sort((a, b) => a.carbon_g - b.carbon_g)) {
    if (row.breakpoint === "now") continue;
    if (ceiling != null && row.carbon_g >= ceiling - 1e-9) continue;
    const start = Date.parse(row.start_iso);
    if (picked.some((p) => Math.abs(start - Date.parse(p.start_iso)) < spacingMinutes * 60000
        || tooClose(row, p))) continue;
    picked.push(row);
    if (picked.length >= limit - 1) break;
  }
  const options = picked.map((row, rank) => ({ ...row, recommended: rank === 0,
    label: rank === 0 ? "Cleanest reachable window"
      : (Date.parse(row.start_iso) < Date.parse(picked[0].start_iso)
          ? "Near-optimal, earlier" : "Near-optimal alternative") }));
  if (runNow) options.push({ ...runNow, label: "Run immediately, no deferral", recommended: !picked.length });
  if (!hasBaseline) for (const o of options) { o.carbon_saved_pct = null; o.cost_saved_pct = null; }
  return { options, trace, baseline_available: hasBaseline,
    candidates_considered: trace.length, feasible_windows: feasible.length,
    baseline_carbon_g: runNow ? runNow.carbon_g : null,
    deadline_iso: job.deadline_iso, now_iso: iso(nowMs) };
}

// A Decision for a window the operator picked, scored by the same scoreWindow
// the engine optimises with, so the UI never reports a number the engine did
// not compute. Port of engine.decision_for_window.
function decisionForWindow(job, slots, nowMs, startMs) {
  const durMs = job.duration_minutes * 60000;
  const [baseCarbon, baseCost] = scoreWindow(slots, nowMs, job.duration_minutes, job.energy_kwh) || [0, 0];
  const chosen = scoreWindow(slots, startMs, job.duration_minutes, job.energy_kwh);
  const [carbon, cost] = chosen || [baseCarbon, baseCost];
  const savedPct = baseCarbon > 0 ? ((baseCarbon - carbon) / baseCarbon) * 100 : 0;
  const costSavedPct = baseCost > 0 ? ((baseCost - cost) / baseCost) * 100 : 0;
  const immediate = startMs <= nowMs;
  const runAt = immediate ? nowMs : startMs;
  return {
    job_id: job.id, action: immediate ? "RUN" : "WAIT", run_at_iso: iso(runAt),
    carbon_saved_pct: round(immediate ? 0 : savedPct, 2),
    cost_saved_pct: round(immediate ? 0 : costSavedPct, 2),
    reason: immediate
      ? "Operator chose to run immediately; no deferral."
      : `Operator selected the ${iso(startMs)} window from the ranked recommendations: deferring ${((startMs - nowMs) / 3600000).toFixed(1)}h cuts ${(baseCarbon - carbon).toFixed(0)} gCO2 (${savedPct.toFixed(1)}%). Deadline ${job.deadline_iso} still met.`,
    baseline_carbon_g: round(baseCarbon, 1),
    optimal_carbon_g: round(immediate ? baseCarbon : carbon, 1),
    baseline_cost_gbp: round(baseCost, 4),
    optimal_cost_gbp: round(immediate ? baseCost : cost, 4),
    window_end_iso: iso(runAt + durMs), decided_at_iso: iso(nowMs),
    slots_considered: slots.length,
    feasible_windows: evaluateCandidates(job, slots, nowMs).filter((r) => r.feasible).length,
  };
}

/* ---------- real work: chained SHA-256, same shape as executor.hash_grind ---------- */
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  return hex(await crypto.subtle.digest("SHA-256", data));
}
async function hashChain(seed, rounds) {
  let digest = seed;
  for (let i = 0; i < rounds; i++) digest = await sha256Hex(digest + ":" + i);
  return digest;
}

export function createOfflineBackend() {
  let profile = syntheticDayProfile();
  let live = false, lastFetchIso = null, lastError = null;
  let speed = 1, anchorReal = Date.now(), anchorVirtual = Date.now();
  const jobs = new Map(), decisions = new Map(), logs = [];
  const baselines = new Map(), actualCarbon = new Map();
  const baselineCosts = new Map(), actualCost = new Map();
  const artifacts = new Map();
  let seq = 0, running = 0;

  const vnow = () => anchorVirtual + (Date.now() - anchorReal) * speed;
  const log = (level, text) => {
    logs.push({ ts_iso: iso(Date.now()), virtual_iso: iso(vnow()), level, text });
    if (logs.length > LOG_RING) logs.shift();
  };
  const buildSlot = (t) => {
    const intensity = profile[halfHourOfDay(t)];
    const isLive = live && Boolean(liveRows[iso(t)]);
    return { t, timestamp: iso(t), intensity_gco2_kwh: round(intensity, 1), intensity,
             renewable_pct: deriveRenewablePct(intensity), price: modelPrice(intensity, t),
             live: isLive,
             source_kind: isLive ? "provider_forecast" : "synthetic_fallback",
             renewable_basis: "derived proxy" };
  };
  // Mirrors backend/app/india.py. The British renewable fit saturates at
  // 400 gCO2/kWh, below every value the Indian grid produces, so India needs
  // its own; this is fitted to five real paired observations.
  const indiaRenewablePct = (intensity) =>
    round(Math.min(Math.max(-0.13114 * intensity + 100.852, 0), 100), 1);
  // Replays the recorded real Indian forecast by UTC half-hour of day, the
  // same way the server does, so the hosted page and the backend agree.
  const indiaSlot = (t) => {
    const table = recordedIndia.intensity_by_half_hour_utc || {};
    const at = new Date(t);
    const key = String(at.getUTCHours()).padStart(2, "0") + ":" + (at.getUTCMinutes() < 30 ? "00" : "30");
    const intensity = table[key];
    if (intensity === undefined) return null;
    return { t, timestamp: iso(t), intensity_gco2_kwh: intensity, intensity,
             renewable_pct: indiaRenewablePct(intensity),
             price: round(25 + 35 * Math.min(Math.max((intensity - 450) / 250, 0), 1), 2),
             live: false, source_kind: "recorded_real",
             renewable_basis: "linear fit to 5 paired observations, 2026-09-19 (R^2 0.97)" };
  };
  const indiaAvailable = Object.keys(recordedIndia.intensity_by_half_hour_utc || {}).length > 0;

  let liveRows = {};
  const forecast = (fromMs) => {
    const first = floorToSlot(fromMs);
    const count = Math.floor((HORIZON_HOURS * 60) / SLOT_MINUTES) + 1;
    return Array.from({ length: count }, (_, k) => buildSlot(first + k * SLOT_MS));
  };
  const wire = (s) => ({ timestamp: s.timestamp, intensity_gco2_kwh: s.intensity_gco2_kwh,
                         renewable_pct: s.renewable_pct, price: s.price, live: s.live,
                         source_kind: s.source_kind, renewable_basis: s.renewable_basis });

  async function refresh() {
    try {
      const r = await fetch("https://api.carbonintensity.org.uk/intensity/fw24h",
        { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const rows = (await r.json()).data || [];
      const next = {}, exact = {};
      for (const row of rows) {
        const v = row?.intensity?.forecast;
        if (v == null) continue;
        const t = Date.parse(row.from);
        next[halfHourOfDay(t)] = Number(v);
        exact[iso(t)] = Number(v);
      }
      if (Object.keys(next).length < SLOTS_PER_DAY / 2) throw new Error("forecast too sparse");
      const known = Object.keys(next).map(Number);
      for (let hh = 0; hh < SLOTS_PER_DAY; hh++) {
        if (!(hh in next)) {
          const nearest = known.reduce((a, b) =>
            Math.min(Math.abs(b - hh), SLOTS_PER_DAY - Math.abs(b - hh)) <
            Math.min(Math.abs(a - hh), SLOTS_PER_DAY - Math.abs(a - hh)) ? b : a);
          next[hh] = next[nearest];
        }
      }
      profile = next; liveRows = exact; live = true;
      lastFetchIso = iso(Date.now()); lastError = null;
      log("INFO", "Live UK grid forecast loaded in-browser (48 half-hour slots).");
      return true;
    } catch (e) {
      lastError = `${e.name}: ${e.message}`; live = false;
      log("WARN", `Live forecast unavailable (${lastError}); using the offline curve.`);
      return false;
    }
  }
  refresh();

  function redecide(job) {
    const slots = forecast(vnow());
    const d = decide(job, slots, vnow());
    const prev = decisions.get(job.id);
    decisions.set(job.id, d);
    if (!baselines.has(job.id)) {
      baselines.set(job.id, d.baseline_carbon_g);
      baselineCosts.set(job.id, d.baseline_cost_gbp);
    }
    if (d.action === "WAIT") {
      job.status = "WAITING"; job.run_at_iso = d.run_at_iso;
      if (!prev) log("PLAN", `${job.name}: WAIT until ${d.run_at_iso} (-${d.carbon_saved_pct}% carbon).`);
      else if (prev.action === "WAIT" && prev.run_at_iso !== d.run_at_iso)
        log("REPLAN", `${job.name}: window moved to ${d.run_at_iso}.`);
    } else {
      job.run_at_iso = d.run_at_iso;
      if (job.status === "QUEUED" || job.status === "WAITING") job.status = "QUEUED";
      if (!prev) log("PLAN", `${job.name}: RUN now.`);
    }
    return d;
  }

  async function execute(job) {
    if (running >= 4) return;
    running++;
    try {
      await runWorkload(job);
    } catch (e) {
      // crypto.subtle is undefined on an insecure origin, among other things.
      // Without this the slot leaks and the job sticks on RUNNING forever,
      // which after four jobs stops execution and blocks reset entirely.
      job.status = "FAILED";
      job.progress = 0;
      job.result = { error: String(e && e.message ? e.message : e) };
      log("FAIL", `${job.name}: ${job.result.error}`);
    } finally {
      running--;
    }
  }

  async function runWorkload(job) {
    job.status = "RUNNING"; job.started_iso = iso(vnow()); job.progress = 0;
    log("EXEC", `${job.name}: started (${job.workload}).`);
    const seed = `${job.id}:${job.started_iso}`;
    const totalRounds = job.workload === "matrix_train" ? 600 : 1200;
    const chunk = 60;
    let digest = seed;
    for (let i = 0; i < totalRounds; i += chunk) {
      const upto = Math.min(chunk, totalRounds - i);
      for (let k = 0; k < upto; k++) digest = await sha256Hex(digest + ":" + (i + k));
      job.progress = round((i + upto) / totalRounds, 3);
      await new Promise((r) => setTimeout(r, 0));
    }
    const d = decisions.get(job.id);
    const slots = forecast(Date.parse(job.run_at_iso));
    const scored = scoreWindow(slots, Date.parse(job.run_at_iso), job.duration_minutes, job.energy_kwh);
    actualCarbon.set(job.id, scored ? scored[0] : d?.optimal_carbon_g ?? 0);
    actualCost.set(job.id, scored ? scored[1] : d?.optimal_cost_gbp ?? 0);
    artifacts.set(job.id, { seed, rounds: totalRounds, digest });
    job.result = { workload: job.workload, rounds: totalRounds, digest, seed };
    job.progress = 1; job.status = "DONE"; job.finished_iso = iso(vnow());
    log("DONE", `${job.name}: complete. Digest ${digest.slice(0, 16)}...`);
  }

  setInterval(() => {
    const now = vnow();
    for (const job of jobs.values()) {
      if (job.status === "WAITING" || job.status === "QUEUED") {
        // An operator-chosen window is a commitment; re-optimising would move a
        // job the user deliberately placed.
        if (!job.pinned) redecide(job);
        if (Date.parse(job.run_at_iso) <= now) {
          // Match the server: a job is missed when it cannot FINISH by the
          // deadline, not merely when the deadline has passed. The looser test
          // ran and credited jobs that could never have completed in time.
          if (now + job.duration_minutes * 60000 > Date.parse(job.deadline_iso)) {
            job.status = "MISSED";
            log("WARN", `${job.name}: no window remains before the deadline.`);
          }
          else execute(job);
        }
      }
    }
  }, 1000);

  const totals = () => {
    let saved = 0, emitted = 0, savedCost = 0, energy = 0, done = 0;
    for (const [id, actual] of actualCarbon) {
      const job = jobs.get(id);
      if (!job || job.status !== "DONE") continue;
      saved += (baselines.get(id) ?? actual) - actual;
      emitted += actual;
      savedCost += (baselineCosts.get(id) ?? 0) - (actualCost.get(id) ?? 0);
      energy += job.energy_kwh; done++;
    }
    if (Math.abs(saved) < 1e-9) saved = 0;
    if (Math.abs(savedCost) < 1e-12) savedCost = 0;
    return { carbon_saved_g: round(saved, 1), carbon_emitted_g: round(emitted, 1),
      carbon_saved_pct: round(saved + emitted > 0 ? (saved / (saved + emitted)) * 100 : 0, 2),
      cost_saved_gbp: round(savedCost, 4), energy_scheduled_kwh: round(energy, 2), jobs_completed: done };
  };

  const makeJob = (body) => {
    const now = vnow();
    const hours = body.deadline_hours ?? 12;
    return { id: `job-${String(++seq).padStart(3, "0")}`, name: body.name,
      energy_kwh: body.energy_kwh, duration_minutes: body.duration_minutes ?? 30,
      workload: body.workload ?? "hash_grind", status: "QUEUED",
      deadline_iso: body.deadline_iso ?? iso(now + hours * 3600000),
      home_region: body.home_region ?? "gb", target_region: body.home_region ?? "gb",
      allowed_regions: body.allowed_regions ?? [], allow_shift: false,
      forecast_method: "provider", data_mode: "live", pinned: false, baseline_plan: null,
      submitted_iso: iso(now), run_at_iso: null, started_iso: null,
      finished_iso: null, result: null, progress: 0 };
  };

  return {
    offline: true,
    async getState() {
      const now = vnow();
      const slots = forecast(now);
      const impacts = {};
      for (const [id, job] of jobs) {
        if (job.status !== "DONE" || !actualCarbon.has(id)) continue;
        const baseline = baselines.get(id) ?? 0, actual = actualCarbon.get(id);
        impacts[id] = { baseline_carbon_g: baseline, estimated_carbon_g: round(actual, 3),
          saved_carbon_g: round(baseline - actual, 3),
          saved_pct: baseline ? round(((baseline - actual) / baseline) * 100, 2) : 0,
          energy_basis: "operator estimate; not metered" };
      }
      return {
        clock: { virtual_iso: iso(now), real_iso: iso(Date.now()), speed,
                 allowed_speeds: ALLOWED_SPEEDS, compressed: speed > 1 },
        grid: {
          now: wire(buildSlot(floorToSlot(now))),
          forecast: slots.map(wire),
          status: { live, source: live ? "UK Carbon Intensity API /intensity/fw24h (fetched in-browser)"
                                       : (lastFetchIso ? "cached UK forecast" : "offline fallback curve"),
                    last_fetch_iso: lastFetchIso, last_error: lastError,
                    cached: Boolean(lastError && lastFetchIso), profile_extension: true },
          provenance: { intensity_gco2_kwh: speed > 1 ? "forecast replay"
                          : (live ? "live forecast with profile extension"
                                  : (lastFetchIso ? "cached forecast" : "synthetic fallback")),
                        renewable_pct: "derived from intensity",
                        price: "modelled (API carries no price)" },
        },
        jobs: [...jobs.values()].map((j) => ({ ...j })),
        decisions: Object.fromEntries(decisions),
        totals: totals(), impacts, logs: [...logs],
        workloads: ["hash_grind", "matrix_train"], horizon_hours: HORIZON_HOURS,
        // GB national and the Indian national capture are available without a
        // server. The zonal feeds need provider calls this page cannot make and
        // the model needs training data it cannot fetch; both say so rather
        // than faking it.
        regions: [
          { id: "gb", name: "Great Britain", country: "GB", available: true,
            current: wire(buildSlot(floorToSlot(now))),
            source: live ? "UK Carbon Intensity API (fetched in-browser)" : "offline fallback curve",
            error: null, execution: "local demonstration only" },
          // India carries a recorded real provider forecast, which is a static
          // file this page can read, so it is available here exactly as on the
          // server -- real data on a replayed clock, labelled as such.
          { id: "in", name: "India \u00b7 National grid", country: "IN",
            available: indiaAvailable,
            current: indiaAvailable ? wire(indiaSlot(floorToSlot(now))) : null,
            source: indiaAvailable
              ? "Electricity Maps forecast for zone IN, recorded 2026-09-19 and replayed by half-hour of day"
              : "No Indian data available",
            error: null, execution: "local demonstration only" },
          ...[["gb-london", "London", "GB"], ["gb-scotland", "North Scotland", "GB"],
              ["in-north", "India \u00b7 Northern grid", "IN"], ["in-south", "India \u00b7 Southern grid", "IN"]]
            .map(([id, name, country]) => ({
              id, name, country, available: false, current: null,
              source: "Needs the local backend; run start.ps1 for regional feeds",
              error: null, execution: "local demonstration only" })),
        ],
        model: { trained: false, algorithm: "seasonal ridge regression",
                 note: "Training needs the local backend; run start.ps1" },
        data_mode: "live",
        execution_mode: "browser demonstration; no remote cloud worker",
      };
    },

    async recommendWindows(body) {
      return rankWindows(makeJob(body), forecast(vnow()), vnow());
    },
    async previewJob(body) {
      const job = makeJob(body);
      return { ...decide(job, forecast(vnow()), vnow()), job_id: "preview" };
    },
    async createJob(body) {
      const job = makeJob(body);
      job.pinned = Boolean(body.run_at_iso);
      jobs.set(job.id, job);
      log("SUBMIT", `${job.name}: ${job.energy_kwh} kWh over ${job.duration_minutes} min.`);
      let d;
      if (job.pinned) {
        d = decisionForWindow(job, forecast(vnow()), vnow(), Date.parse(body.run_at_iso));
        decisions.set(job.id, d);
        baselines.set(job.id, d.baseline_carbon_g);
        baselineCosts.set(job.id, d.baseline_cost_gbp);
        job.run_at_iso = d.run_at_iso;
        job.status = d.action === "WAIT" ? "WAITING" : "QUEUED";
        log("PLAN", `${job.name}: operator chose ${d.run_at_iso}.`);
      } else {
        d = redecide(job);
      }
      if (d.action === "RUN") execute(job);
      return { job: { ...job }, decision: d };
    },
    async cancelJob(id) {
      const job = jobs.get(id);
      if (job && job.status !== "RUNNING") { jobs.delete(id); decisions.delete(id); log("CANCEL", `${job.name}: cancelled.`); }
      return { ok: true };
    },
    async setSpeed({ speed: s } = {}) {
      const next = Number(s);
      if (!ALLOWED_SPEEDS.includes(next)) throw new Error(`speed must be one of ${ALLOWED_SPEEDS.join(", ")}`);
      anchorVirtual = vnow(); anchorReal = Date.now(); speed = next;
      log("CLOCK", `TIME COMPRESSION ${next}x -- clock and grid feed only; workloads still run at real speed.`);
      return { speed: next };
    },
    async seedDemo() {
      const presets = [
        { name: "climate-model-validation", energy_kwh: 48, duration_minutes: 45, deadline_hours: 12, workload: "hash_grind" },
        { name: "renewable-scenario-matrix", energy_kwh: 12, duration_minutes: 30, deadline_hours: 12, workload: "matrix_train" },
        { name: "grid-data-integrity-check", energy_kwh: 4, duration_minutes: 30, deadline_hours: 0.75, workload: "hash_grind" },
      ];
      for (const p of presets) if (![...jobs.values()].some((j) => j.name === p.name)) await this.createJob(p);
      return { ok: true };
    },
    async resetAll() {
      if ([...jobs.values()].some((j) => j.status === "RUNNING")) throw new Error("Wait for running workloads to finish before resetting");
      jobs.clear(); decisions.clear(); baselines.clear(); actualCarbon.clear();
      baselineCosts.clear(); actualCost.clear(); artifacts.clear(); logs.length = 0; seq = 0;
      log("RESET", "Queue cleared.");
      return { ok: true };
    },
    async refreshGrid() { await refresh(); return { live }; },
    async getArtifact(id) {
      const a = artifacts.get(id);
      if (!a) throw new Error("No artifact for this job yet");
      const recomputed = await hashChain(a.seed, a.rounds);
      return { job_id: id, seed: a.seed, rounds: a.rounds, digest: a.digest,
               recomputed_digest: recomputed, independently_verified: recomputed === a.digest,
               note: "Recomputed in the browser from the recorded seed." };
    },
  };
}
