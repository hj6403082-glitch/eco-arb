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
from .engine import decide
from .executor import ARTIFACT_DIR, WORKLOADS, verify_hash_grind
from .models import Job, JobCreate, SpeedSet
from .store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.log("ECO-ARB online. Pulling UK Carbon Intensity forecast...", "OK")
    sched.refresh_grid()
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
        deadline = parse_iso(payload.deadline_iso)
    else:
        hours = payload.deadline_hours or config.DEADLINE_HORIZON_HOURS
        deadline = now + timedelta(hours=min(hours, config.DEADLINE_HORIZON_HOURS))
    horizon_cap = now + timedelta(hours=config.DEADLINE_HORIZON_HOURS)
    if deadline > horizon_cap:
        deadline = horizon_cap
    return iso(deadline)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "real_time": iso(real_now()), "virtual_time": iso(clock.now())}


@app.get("/api/state")
def state() -> dict:
    """Everything the terminal draws, in one poll."""
    vnow = clock.now()
    slots = feed.forecast(vnow)
    with store.lock:
        jobs = [j.model_dump() for j in store.jobs.values()]
        decisions = {k: v.model_dump() for k, v in store.decisions.items()}
        logs = [l.model_dump() for l in store.logs]
        totals = store.totals()
    return {
        "clock": {
            "virtual_iso": iso(vnow),
            "real_iso": iso(real_now()),
            "speed": clock.speed,
            "allowed_speeds": list(config.ALLOWED_SPEEDS),
            "compressed": clock.speed > 1,
        },
        "grid": {
            "now": feed.slot_at(vnow).model_dump(),
            "forecast": [s.model_dump() for s in slots],
            "status": feed.status(),
            "provenance": {
                "intensity_gco2_kwh": "live",
                "renewable_pct": "derived from intensity",
                "price": "modelled (API carries no price)",
            },
        },
        "jobs": jobs,
        "decisions": decisions,
        "totals": totals,
        "logs": logs,
        "workloads": sorted(WORKLOADS),
        "horizon_hours": config.DEADLINE_HORIZON_HOURS,
    }


@app.post("/api/jobs")
def create_job(payload: JobCreate) -> dict:
    if payload.workload not in WORKLOADS:
        raise HTTPException(400, f"unknown workload; expected one of {sorted(WORKLOADS)}")
    vnow = clock.now()
    job = Job(
        id=store.next_id(),
        name=payload.name,
        energy_kwh=payload.energy_kwh,
        deadline_iso=_resolve_deadline(payload, vnow),
        status="QUEUED",
        duration_minutes=payload.duration_minutes,
        workload=payload.workload,
        submitted_iso=iso(vnow),
    )
    store.add(job)
    store.log(
        f"{job.id} SUBMIT '{job.name}' {job.energy_kwh:g} kWh / "
        f"{job.duration_minutes:g} min, deadline {job.deadline_iso}",
        "INFO",
    )
    # Decide immediately so the terminal never shows an unexplained QUEUED row.
    decision = decide(job, feed.forecast(vnow), vnow)
    store.set_decision(decision)
    with store.lock:
        store.baselines.setdefault(job.id, decision.baseline_carbon_g)
        store.baseline_costs.setdefault(job.id, decision.baseline_cost_gbp)
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
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    if job.status == "RUNNING":
        raise HTTPException(409, "job is already executing; it runs at real speed")
    with store.lock:
        store.jobs.pop(job_id, None)
        store.decisions.pop(job_id, None)
    store.log(f"{job_id} CANCELLED '{job.name}'", "WARN")
    return {"cancelled": job_id}


@app.get("/api/jobs/{job_id}/artifact")
def job_artifact(job_id: str) -> dict:
    path = ARTIFACT_DIR / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(404, "no artifact yet; the job has not finished")
    payload = json.loads(path.read_text())
    result = payload.get("result", {})
    verified = None
    if result.get("workload") == "hash_grind":
        verified = verify_hash_grind(result)
    return {"artifact": payload, "independently_verified": verified}


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
            name="nightly-model-retrain",
            energy_kwh=48.0,
            duration_minutes=120.0,
            deadline_hours=24,
            workload="hash_grind",
        ),
        JobCreate(
            name="batch-video-transcode",
            energy_kwh=12.0,
            duration_minutes=60.0,
            deadline_hours=12,
            workload="matrix_train",
        ),
        JobCreate(
            name="hourly-etl-rollup",
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
        store.jobs.clear()
        store.decisions.clear()
        store.baselines.clear()
        store.baseline_costs.clear()
        store.actual_carbon.clear()
        store.actual_cost.clear()
        store.logs.clear()
    clock.reset()
    store.log("State cleared.", "INFO")
    return {"ok": True}
