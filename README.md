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

```powershell
./.venv/Scripts/python.exe -m pip install pytest
./.venv/Scripts/python.exe -m pytest backend/tests -q
npm ci --prefix frontend
npm run dev --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

Vite runs at port 5173 and proxies `/api` to port 8000. FastAPI serves `frontend/dist` directly. Restart the backend after the initial build.

## Prototype boundary

The service binds to loopback. It has no authentication, tenant isolation, measured-electricity integration or distributed queue. Keep one backend worker. Add those controls before public deployment. The CPU workload is real but illustrative, not a production cloud training service.

The original archives remain untouched. The separate backend archive contained empty source stubs and was not used as an implementation.


## Electric Biosphere visual system

The interface combines electric violet, cyan, acid lime and coral. A procedural particle field, flowing energy traces, rotating reactor rings, breathing ambient light, staggered card entrances and hover feedback bring the control room to life. Decorative motion does not represent extra telemetry. Use the header Motion toggle to pause it; system reduced-motion preferences are respected. The particle canvas is capped at 30 frames per second and skips rendering when the tab is hidden.
