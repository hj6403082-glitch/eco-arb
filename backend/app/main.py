"""ECO-ARB API. One snapshot endpoint, polled by the terminal at 1 Hz."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config, scheduler as sched
from .carbon import feed
from .clock import clock, iso, parse_iso, real_now
from .engine import decide, decision_for_window, recommend
from .executor import ARTIFACT_DIR, WORKLOADS, verify_hash_grind
from .models import Job, JobCreate, SpeedSet, ModelTraining, ForecastImport
from .store import store
from .regions import registry, REGIONS
from .learning import learned, synthetic_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.log("ECO-ARB online. Pulling UK Carbon Intensity forecast...", "OK")
    sched.refresh_grid()
    # A replay's virtual epoch is intentionally not restored across restarts.
    with store.lock:
        for job in store.jobs.values():
            if job.data_mode == "scenario" and job.status in ("QUEUED", "WAITING"):
                job.status = "FAILED"
                job.result = {"error": "Scenario interrupted by restart; start a fresh guided scenario"}
    sched.start()
    try:
        yield
    finally:
        sched.shutdown()


app = FastAPI(title="ECO-ARB", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_deadline(payload: JobCreate, now) -> str:
    if payload.deadline_iso:
        try:
            deadline = parse_iso(payload.deadline_iso)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "Use a valid ISO deadline") from exc
    else:
        hours = payload.deadline_hours or config.DEADLINE_HORIZON_HOURS
        deadline = now + timedelta(hours=min(hours, config.DEADLINE_HORIZON_HOURS))
    horizon_cap = now + timedelta(hours=config.DEADLINE_HORIZON_HOURS)
    if deadline > horizon_cap:
        deadline = horizon_cap
    if deadline < now + timedelta(minutes=payload.duration_minutes, seconds=config.TICK_SECONDS * clock.speed + 1):
        raise HTTPException(422, "The deadline must allow the full workload duration plus one scheduler tick")
    return iso(deadline)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "real_time": iso(real_now()), "virtual_time": iso(clock.now())}


@app.get("/api/state")
def state() -> dict:
    """Everything the terminal draws, in one poll."""
    vnow = clock.now()
    primary_region = "in-north" if registry.mode == "scenario" else "gb"
    slots = registry.forecast(primary_region, vnow)
    with store.lock:
        jobs = [j.model_dump() for j in store.jobs.values()]
        decisions = {k: v.model_dump() for k, v in store.decisions.items()}
        logs = [l.model_dump() for l in store.logs]
        totals = store.totals()
        impacts = {}
        for jid, j in store.jobs.items():
            if j.status == "DONE" and jid in store.actual_carbon:
                baseline = store.baselines.get(jid, 0)
                actual = store.actual_carbon[jid]
                impacts[jid] = {"baseline_carbon_g": baseline, "estimated_carbon_g": round(actual, 3),
                               "saved_carbon_g": round(baseline - actual, 3),
                               "saved_pct": round((baseline - actual) / baseline * 100, 2) if baseline else 0,
                               "energy_basis": "operator estimate; not metered"}
    return {
        "clock": {
            "virtual_iso": iso(vnow),
            "real_iso": iso(real_now()),
            "speed": clock.speed,
            "allowed_speeds": list(config.ALLOWED_SPEEDS),
            "compressed": clock.speed > 1,
        },
        "grid": {
            "now": slots[0].model_dump(),
            "forecast": [s.model_dump() for s in slots],
            "status": {**feed.status(), "mode": registry.mode,
                       "live": registry.mode != "scenario" and slots[0].live,
                       "source": "synthetic India regional scenario" if registry.mode == "scenario" else feed.status()["source"]},
            "provenance": {
                "intensity_gco2_kwh": ", ".join(sorted({s.source_kind for s in slots})),
                "renewable_pct": "derived from intensity",
                "price": "modelled (API carries no price)",
            },
        },
        "jobs": jobs,
        "decisions": decisions,
        "totals": totals,
        "impacts": impacts,
        "logs": logs,
        "workloads": sorted(WORKLOADS),
        "horizon_hours": config.DEADLINE_HORIZON_HOURS,
        "regions": registry.describe(vnow),
        "model": learned.status(),
        "data_mode": registry.mode,
        "execution_mode": "local demonstration; no remote cloud worker",
    }


def build_job(payload, now, job_id):
    if payload.home_region not in REGIONS or any(r not in REGIONS for r in payload.allowed_regions):
        raise HTTPException(422, "Choose a supported region")
    if payload.allow_shift and not payload.allowed_regions:
        raise HTTPException(422, "Choose at least one allowed destination for SHIFT")
    if payload.forecast_method == "learned" and (payload.home_region != "gb" or payload.allow_shift):
        raise HTTPException(422, "Learned forecasts support GB national without region shifting")
    return Job(id=job_id, name=payload.name, energy_kwh=payload.energy_kwh,
               deadline_iso=_resolve_deadline(payload, now), duration_minutes=payload.duration_minutes,
               workload=payload.workload, submitted_iso=iso(now), home_region=payload.home_region,
               target_region=payload.home_region, allow_shift=payload.allow_shift,
               allowed_regions=payload.allowed_regions, forecast_method=payload.forecast_method,
               data_mode=registry.mode)


def plan_or_error(job, now):
    try:
        return registry.plan(job, now)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/recommend")
def recommend_windows(payload: JobCreate) -> dict:
    """Rank the windows worth offering for a job, without queueing anything.

    Returns the options the operator picks from plus the full scored candidate
    trace, which is what the decision view animates. Read-only, like /api/preview.
    """
    vnow = clock.now()
    probe = build_job(payload, vnow, "recommend")
    slots = registry.forecast(probe.home_region, vnow, probe.data_mode, probe.forecast_method)
    return recommend(probe, slots, vnow)


@app.post("/api/jobs")
def create_job(payload: JobCreate) -> dict:
    if payload.workload not in WORKLOADS:
        raise HTTPException(400, f"unknown workload; expected one of {sorted(WORKLOADS)}")
    vnow = clock.now()
    job = build_job(payload, vnow, store.next_id())
    if payload.run_at_iso is None:
        decision = plan_or_error(job, vnow)
    else:
        # The operator picked a window from /api/recommend. Score exactly that
        # window with the same function the engine optimises with, so the UI can
        # never report a saving the engine did not compute.
        try:
            chosen = parse_iso(payload.run_at_iso)
        except (ValueError, TypeError):
            raise HTTPException(422, "run_at_iso is not a valid ISO-8601 timestamp")
        if chosen + timedelta(minutes=job.duration_minutes) > parse_iso(job.deadline_iso):
            raise HTTPException(422, "the chosen window would finish after the deadline")
        if chosen < vnow - timedelta(minutes=config.SLOT_MINUTES):
            raise HTTPException(422, "the chosen window is already in the past")
        slots = registry.forecast(job.home_region, vnow, job.data_mode, job.forecast_method)
        decision = decision_for_window(job, slots, vnow, chosen)
        decision.source_region = decision.target_region = job.home_region
        decision.data_basis = ", ".join(sorted({r.source_kind for r in slots}))
        job.pinned = True
    job.baseline_plan = {
        "at": iso(vnow), "region": job.home_region, "energy_kwh": job.energy_kwh,
        "duration_minutes": job.duration_minutes, "forecast_method": job.forecast_method,
        "forecast": [r.model_dump() for r in registry.forecast(job.home_region, vnow, job.data_mode, job.forecast_method)],
        "model": learned.status() if job.forecast_method == "learned" else None,
    }
    with store.lock:
        store.add(job)
        store.log(
            f"{job.id} SUBMIT '{job.name}' {job.energy_kwh:g} kWh / "
            f"{job.duration_minutes:g} min, deadline {job.deadline_iso}",
            "INFO",
        )
        # Decide immediately so the terminal never shows an unexplained QUEUED row.
        job.run_at_iso = decision.run_at_iso
        if decision.action == "WAIT":
            job.status = "WAITING"
        store.set_decision(decision)
        with store.lock:
            store.baselines.setdefault(job.id, decision.baseline_carbon_g)
            store.baseline_costs.setdefault(job.id, decision.baseline_cost_gbp)
            store.checkpoint()
        return {"job": job.model_dump(), "decision": decision.model_dump()}



@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    decision = store.decisions.get(job_id)
    return {
        "job": job.model_dump(),
        "decision": decision.model_dump() if decision else None,
    }


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    with store.lock:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        if job.status not in ("QUEUED", "WAITING"):
            raise HTTPException(409, "Only pending jobs can be cancelled; execution records are retained")
        with store.lock:
            store.jobs.pop(job_id, None)
            store.decisions.pop(job_id, None)
        store.log(f"{job_id} CANCELLED '{job.name}'", "WARN")
        store.checkpoint()
        return {"cancelled": job_id}



@app.get("/api/jobs/{job_id}/artifact")
def job_artifact(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None or job.status != "DONE":
        raise HTTPException(404, "No completed execution record for this job")
    path = ARTIFACT_DIR / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(404, "no artifact yet; the job has not finished")
    payload = json.loads(path.read_text())
    result = payload.get("result", {})
    verified = None
    if result.get("workload") == "hash_grind":
        verified = verify_hash_grind(result)
    return {"artifact": payload, "independently_verified": verified,
            "verification_scope": "hash chain and Merkle root; does not verify geographic location or electricity consumption"}


@app.post("/api/speed")
def set_speed(payload: SpeedSet) -> dict:
    try:
        speed = clock.set_speed(payload.speed)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.log(
        f"TIME COMPRESSION {speed}x -- clock and grid feed only; workloads still "
        f"run at real speed",
        "INFO",
    )
    return {"speed": speed, "virtual_iso": iso(clock.now())}


@app.post("/api/grid/refresh")
def force_refresh() -> dict:
    sched.refresh_grid()
    return feed.status()


@app.post("/api/demo/seed")
def seed_demo() -> dict:
    """Three jobs that exercise all three outcomes: defer, run now, deadline-bound."""
    vnow = clock.now()
    specs = [
        JobCreate(
            name="climate-model-validation",
            energy_kwh=48.0,
            duration_minutes=120.0,
            deadline_hours=24,
            workload="hash_grind",
        ),
        JobCreate(
            name="renewable-scenario-matrix",
            energy_kwh=12.0,
            duration_minutes=60.0,
            deadline_hours=12,
            workload="matrix_train",
        ),
        JobCreate(
            name="grid-data-integrity-check",
            energy_kwh=4.0,
            duration_minutes=30.0,
            deadline_hours=0.75,
            workload="hash_grind",
        ),
    ]
    return {"seeded": [create_job(s) for s in specs]}


@app.post("/api/reset")
def reset() -> dict:
    with store.lock:
        if any(j.status == "RUNNING" for j in store.jobs.values()):
            raise HTTPException(409, "Wait for running workloads to finish before resetting")
        store.jobs.clear()
        store.decisions.clear()
        store.baselines.clear()
        store.baseline_costs.clear()
        store.actual_carbon.clear()
        store.actual_cost.clear()
        store.logs.clear()
    clock.reset()
    clock.set_speed(1)
    registry.mode = "operational"
    store.log("State cleared.", "INFO")
    store.checkpoint()
    return {"ok": True}


@app.post("/api/preview")
def preview(payload: JobCreate) -> dict:
    if payload.workload not in WORKLOADS:
        raise HTTPException(400, "Unknown workload")
    now = clock.now()
    return plan_or_error(build_job(payload, now, "preview"), now).model_dump()


@app.get("/api/regions/{region}/forecast")
def regional_forecast(region: str):
    if region not in REGIONS:
        raise HTTPException(404, "Unknown region")
    return {"region": region, "forecast": [r.model_dump() for r in registry.forecast(region, clock.now())]}


@app.post("/api/regions/import")
def import_forecast(payload: ForecastImport):
    try:
        if max(parse_iso(r.timestamp) for r in payload.rows) <= clock.now():
            raise ValueError("Import must include future forecast intervals")
        registry.ingest(payload.region, payload.rows, payload.source_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"imported": len(payload.rows), "region": payload.region,
            "basis": "operator-supplied forecast; provider authenticity is not verified"}


@app.post("/api/model/train")
def train_model(payload: ModelTraining):
    try:
        report = (learned.train_public() if payload.dataset == "public_history"
                  else learned.train(synthetic_history(), "synthetic demonstration"))
        store.log(f"Forecast model trained on {report['dataset']}; validation MAE {report['mae_gco2_kwh']} gCO2/kWh", "OK")
        return report
    except Exception as exc:
        raise HTTPException(502, "Training failed: " + type(exc).__name__ + ". Check connectivity or use the labelled synthetic training fixture.") from exc


@app.get("/api/model/forecast")
def model_forecast():
    try:
        rows = registry.forecast("gb", clock.now(), "scenario", "learned")
        return {"forecast": [r.model_dump() for r in rows], "model": learned.status()}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/demo/scenario")
def guided_scenario():
    with store.lock:
        if any(j.status in ("QUEUED", "WAITING", "RUNNING") for j in store.jobs.values()):
            raise HTTPException(409, "Finish or cancel pending work, or reset the demo session before changing the clock")
        clock.reset()
        clock.set_speed(360)
        registry.mode = "scenario"
        registry.scenario_anchor = clock.now().replace(minute=0, second=0, microsecond=0)
        # Anchor the clean trough to the current half-hour for repeatable deferral.
        from .carbon import floor_to_slot
        registry.scenario_anchor = floor_to_slot(clock.now())
        specs = [JobCreate(name="Urgent integrity check", energy_kwh=1, duration_minutes=1, deadline_hours=.2),
                 JobCreate(name="Flexible climate validation", energy_kwh=5, duration_minutes=30, deadline_hours=6),
                 JobCreate(name="India regional SHIFT scenario", energy_kwh=3, duration_minutes=30, deadline_hours=6,
                           home_region="in-north", allow_shift=True, allowed_regions=["in-south"])]
        seeded = [create_job(s) for s in specs]
        store.log("GUIDED SCENARIO: synthetic regional data; real CPU work executes on this host", "WARN")
        return {"seeded": seeded, "data_mode": "synthetic demonstration", "execution": "local CPU only"}


# Production build and API share one origin; Vite remains available for development.
from fastapi.staticfiles import StaticFiles
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
