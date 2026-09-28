# ECO-ARB — Compute with the grid

A carbon-aware workload scheduler for VINHACK Climate Tech & Resilience. Give a flexible compute job an energy budget, duration and deadline. ECO-ARB finds a cleaner feasible window, waits autonomously, executes real bounded CPU work, and saves an inspectable artifact.

## Run on Windows

Requires Python 3.10+ for Windows. This release includes the built React frontend.

```powershell
./start.ps1
```

If PowerShell blocks scripts on Windows, double-click `start.cmd` instead. It launches the same app without changing execution policy. Open http://127.0.0.1:8000 after the console says “Application startup complete.”

Open http://127.0.0.1:8000. First launch creates a virtual environment and installs backend dependencies. If necessary, pass `-Python 'C:/path/to/python.exe'`. Use `-Port 8001` if 8000 is occupied. Use `-Rebuild` after editing the frontend; rebuilding requires Node.js 22.12+ and npm. On macOS/Linux, use `bash start.sh` with Python 3.10+.

API documentation: http://127.0.0.1:8000/docs.

## Three-minute demo

1. Open **Simulation → Start guided scenario** on a fresh session. It creates labelled RUN / WAIT / SHIFT decisions using a repeatable synthetic regional scenario; every workload executes locally.
2. Select the flexible climate-validation job. Explain its suggested start, estimated reduction, deadline and feasible-window count. Expand **Why this decision?**
3. Click **New workload**. Change energy, planning duration and deadline. The preview updates without creating a job. Submit to enter the real scheduler.
4. Choose **360x** in Grid & simulation. This accelerates the forecast timeline, not CPU execution. One virtual hour takes ten real seconds; a full day takes four minutes. The header changes to **Forecast replay**.
5. Watch a deferred workload move through RUNNING to DONE. Download its proof from the queue. SHA-256 results are independently recomputed by the proof endpoint.
6. Open **Impact**. Only completed jobs contribute to totals. Export the JSON report with methodology and provenance.

Deferral and savings depend on the forecast. Zero savings are a valid outcome. The scheduler does not invent savings for the presentation.

## What is real and what is estimated?

The self-contained scenario does not claim Indian live telemetry or remote cloud execution. India is unavailable in operational mode until a provider forecast is connected or an operator imports future half-hour rows. Regional SHIFT is a recommendation demonstrated with local CPU work. Every receipt preserves its data mode, baseline forecast, dispatch forecast, energy basis and computational proof.

- **Real:** public UK Carbon Intensity API requests, queue, deadline checks, scheduling, bounded CPU work, progress, artifacts and hash verification.
- **Forecast:** public half-hour carbon intensity. Missing intervals and times beyond the fetched horizon use a daily profile extension. Accelerated time explicitly replays this profile.
- **Estimated:** operator-supplied energy and duration. These are planning budgets, not readings of host electricity use. The bounded CPU demo runs in seconds independently of its planning duration.
- **Derived/modelled:** renewable share is an intensity-derived proxy; GBP/MWh is a scarcity model. Neither is live market telemetry. Cost is reported, not optimized.
- **Impact:** declared kWh multiplied by duration-weighted forecast intensity at dispatch, compared with the immediate-execution baseline frozen at submission. Only DONE jobs enter totals. Savings may be negative if conditions worsen.
- **AI scope:** an explainable deterministic optimizer consumes a public grid forecast. No proprietary forecasting model, LLM or reinforcement-learning agent is claimed.
- **Region:** the UK is an accessible reference feed, not Indian telemetry. Cross-region SHIFT is not implemented because this prototype has one execution region.

## Indian grid data

India publishes generation by fuel in MW — CEA's dashboards and Grid-India's
regional dispatch reports — not carbon intensity. There is no *free* public Indian
carbon-intensity forecast comparable to the UK's, so the app offers four routes
and labels which one produced every figure:

0. **The recorded capture, which needs nothing at all.** `in` (India · National
   grid) is backed by a real Electricity Maps forecast for zone `IN`, recorded
   on 2026-09-19 and committed to the repo as
   `backend/app/data/india_recorded.json`. It is a full 24 hours, 487–667
   gCO₂/kWh, replayed by UTC half-hour of day so the recorded diurnal shape
   lines up with the displayed clock. The intensities are exactly as the
   provider returned them — nothing interpolated, nothing smoothed — and every
   row is flagged `recorded_real` and never `live`. **This is real data on a
   replayed clock; it is not a live pull, and the UI never says it is.** The
   hosted static build bundles the identical file, so the page on GitHub Pages
   shows the same real Indian numbers with no backend at all.

1. **Derive it from a generation mix.** Regions → *Import an Indian generation
   mix (CEA / Grid-India)*, or `POST /api/regions/import-mix` with consecutive
   UTC half-hour rows of `{fuel: MW}`. The server multiplies the mix by
   published direct-combustion emission factors — the same basis the UK Carbon
   Intensity API uses, so the two are comparable — and marks the result
   `derived_from_generation_mix`. Renewable share here is **measured from the
   mix**, which is stronger provenance than the UK national feed, where it is
   back-calculated from intensity. `GET /api/emission-factors` returns the exact
   factors so the arithmetic is inspectable. Unrecognised fuel labels fall back
   to a generic factor and are reported, never silently absorbed.
2. **Connect a provider.** Set `ELECTRICITY_MAPS_TOKEN` and the Indian regions
   pull live forecasts directly. Setting `ATLAS_API_KEY` additionally unlocks
   EnergyMap India's national fuel mix and — the one that matters — **real IEX
   real-time-market clearing prices**. Everywhere else in this system `price` is
   modelled; with an IEX key, India's is measured.
3. **Import intensity you already have.** `POST /api/regions/import` takes
   gCO₂/kWh rows directly.

The national region `in` always has the recorded capture to fall back on. The
zonal regions (`in-north`, `in-south`) read "Not connected" in operational mode
until one of routes 1–3 supplies data, because the capture is national and
relabelling it as zonal would be a claim the data does not support. The guided scenario on Simulation does show Indian numbers,
but they are a hardcoded fixture flagged `synthetic_scenario` — never describe
them as measured.

### Renewable share in India

`carbon.derive_renewable_pct` is calibrated to the British grid and saturates at
400 gCO₂/kWh. Every value the Indian grid produces is above that, so before this
was fixed **every Indian slot reported a flat 5% renewable** when the real figure
runs 13–41%. `app/india.py` carries a separate fit, least-squares over five real
paired (intensity, renewable share) observations from 2026-09-19: R² 0.97, every
point within 1.6 percentage points. Five points is a small sample and the ends
are extrapolation, so it is labelled *derived*, never *measured*. A generation-mix
import (route 1) gives a genuinely measured share and should be preferred when
you have one.

An imported forecast often begins after the current half-hour, so there is no
window to run in immediately. Savings are then reported as unavailable rather
than zero, and windows are ranked by absolute carbon instead.

## Architecture

React 19 + Vite + Tailwind/CSS → FastAPI → window optimizer → APScheduler → bounded worker pool → JSON execution proofs.

The optimizer evaluates now, slot starts, end-aligned breakpoints and the latest feasible start. It integrates each half-hour in proportion to overlap with the job. Lowest carbon wins; ties choose the earliest time. Improvements below 1% run immediately. Waiting jobs are re-evaluated until their window opens. Jobs that cannot finish within their planning deadline become MISSED.

Session state is saved atomically in `backend/data/state.json`: jobs, baselines, decisions and accounting. Logs retain 200 entries. On restart, interrupted RUNNING jobs become FAILED; completed records survive. The clock restarts at real time, so accelerated plans may wait again. Run one backend worker.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | /api/health | Clock and service health |
| GET | /api/state | Grid, jobs, decisions, impact, logs |
| POST | /api/preview | Evaluate without scheduling |
| POST | /api/jobs | Validate and schedule |
| DELETE | /api/jobs/{id} | Cancel pending work |
| GET | /api/jobs/{id}/artifact | Proof and hash verification |
| POST | /api/speed | 1x, 60x or 360x clock |
| POST | /api/grid/refresh | Refresh provider data |
| POST | /api/demo/seed | Three demonstration workloads |
| POST | /api/reset | Clear session when no job is running |

Example payload:
```json
{"name":"climate-validation","energy_kwh":12,"duration_minutes":60,"deadline_hours":12,"workload":"hash_grind"}
```

`hash_grind` performs chained SHA-256 with a Merkle root. `matrix_train` performs bounded numeric computation. The optional shell runner is registered only when the server operator configures `ECO_ARB_SHELL_CMD`; nonzero exits fail the job.

## Development and checks

One command runs everything CI runs -- engine tests, lint, build, and the
end-to-end browser smoke -- and exits non-zero if anything fails:

```powershell
.\verify.cmd            # everything
.\verify.cmd --quick    # skip the browser smoke
```

```bash
python scripts/verify.py           # macOS / Linux
```

Prefer this over reading the Actions tab. GitHub only starts a workflow run for
a push authored by a human account -- a push made with an app token deliberately
does not trigger one -- so the Actions tab can sit several commits behind while
the code is perfectly healthy. `verify.py` runs against the working tree in
front of you, which is the thing that actually matters before a demo.

The individual steps, if you want them separately:

```powershell
./.venv/Scripts/python.exe -m pip install pytest
./.venv/Scripts/python.exe -m pytest backend/tests -q
npm ci --prefix frontend
npm run dev --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

Vite runs at port 5173 and proxies `/api` to port 8000. FastAPI serves `frontend/dist` directly. Restart the backend after the initial build.

## Publishing

The site deploys to GitHub Pages from `.github/workflows/pages.yml` on every
push to `main`. There is nothing to run by hand: push, and the workflow builds
`frontend/dist`, copies the standalone page to `/demo/`, and deploys.

    https://hj6403082-glitch.github.io/eco-arb/

One-time setup, in the repository's Settings:

- **Pages -> Source:** GitHub Actions

That is the whole setup while the site lives at the `github.io` URL.

### Putting it on a custom domain

The order matters, and getting it wrong makes the site look broken for an hour.
A `CNAME` file tells GitHub to **301 the `github.io` URL to the custom domain**,
so if it is written before DNS resolves, *both* URLs fail: the domain does not
answer, and the `github.io` one only redirects to it. The workflow therefore
writes `CNAME` only when a repository variable says the domain is ready.

1. Add the DNS records below at the registrar, deleting any pre-existing record
   on `@` first -- parked domains usually ship with one, and a leftover keeps
   the domain failing verification no matter what else is correct.
2. Wait for them to resolve (minutes to about an hour).
3. Set the repository variable **`CUSTOM_DOMAIN`** to the domain, under
   Settings -> Secrets and variables -> Actions -> Variables.
4. Push anything, or run the workflow by hand. The next deploy writes `CNAME`.
5. Settings -> Pages -> **Enforce HTTPS**, once the certificate is issued.

| Type | Name | Value |
|---|---|---|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| CNAME | `www` | `hj6403082-glitch.github.io.` |

All four A records are needed; they are GitHub's anycast addresses, not
alternatives to choose between.

To move the site back off the custom domain, clear the `CUSTOM_DOMAIN` variable
and clear the **Custom domain** box in Pages settings -- GitHub stores that
server-side and will otherwise restore `CNAME` on its own.

### The manual fallback

`scripts/publish.py` builds the site and force-pushes it to the `gh-pages`
branch, bypassing Actions entirely. It exists because this project spent a week
on an account where GitHub created no workflow runs at all -- not for CI, and
not for its own internal Pages builder -- which made every Actions-based route
impossible. Actions works on the current account and the workflow above is the
real path, so `publish.py` is a fallback, not the normal way to deploy.

## Prototype boundary

The service binds to loopback. It has no authentication, tenant isolation, measured-electricity integration or distributed queue. Keep one backend worker. Add those controls before public deployment. The CPU workload is real but illustrative, not a production cloud training service.

The original archives remain untouched. The separate backend archive contained empty source stubs and was not used as an implementation.



## Electric Biosphere visual system

The interface combines electric violet, cyan, acid lime and coral. A procedural particle field, flowing energy traces, rotating reactor rings, breathing ambient light, staggered card entrances and hover feedback bring the control room to life. Decorative motion does not represent extra telemetry. Use the header Motion toggle to pause it; system reduced-motion preferences are respected. The particle canvas is capped at 30 frames per second and skips rendering when the tab is hidden.
