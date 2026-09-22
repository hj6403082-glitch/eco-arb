"""APScheduler wiring: the loop that turns decisions into executed work.

Two background jobs, both on the REAL clock:
  * refresh_grid -- re-pull the forecast from the UK Carbon Intensity API.
  * tick -- compare the VIRTUAL clock against every pending job and dispatch
    anything now due.

The tick re-runs the decision engine for waiting jobs on every pass, so a job
already deferred to 02:00 will move if a fresh forecast finds something
cleaner. Only a genuine change is logged, or the tape would be unreadable.
"""
from __future__ import annotations

from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import logging

from . import config
from .carbon import feed
from .clock import clock, iso, parse_iso
from .engine import decide, score_window
from .executor import pool, run_job
from .models import Job
from .store import store

log = logging.getLogger("eco_arb.scheduler")
from .regions import registry
from .learning import learned

scheduler = BackgroundScheduler(timezone="UTC")


def _zero_clean(value: float) -> float:
    """Kill -0.0 and float dust so the tape never reads '-0 gCO2 avoided'."""
    return 0.0 if abs(value) < 1e-9 else value


def refresh_grid() -> None:
    was_live = feed.live
    ok = feed.refresh()
    if ok and not was_live:
        store.log("Grid feed LIVE: UK Carbon Intensity API /intensity/fw24h", "OK")
    elif not ok and was_live:
        store.log(
            f"Grid feed degraded to cached forecast ({feed.status()['last_error']})", "WARN"
        )
    elif not ok:
        store.log(
            f"Carbon API unreachable, serving fallback curve "
            f"({feed.status()['last_error']})",
            "WARN",
        )
    registry.refresh()


def _on_finished(job_id: str, future) -> None:
    job = store.get(job_id)
    if job is None:
        return
    with store.lock:
        try:
            result = future.result()
            job.result = result
            job.status = "DONE"
            job.progress = 1.0
            job.finished_iso = iso(clock.now())
            store.log(
                f"{job.id} DONE '{job.name}' in {result.get('real_seconds', 0):.1f}s real "
                f"-> execution proof saved",
                "OK",
            )
        except Exception as exc:  # noqa: BLE001
            job.status = "FAILED"
            job.result = {"error": f"{type(exc).__name__}: {exc}"}
            job.finished_iso = iso(clock.now())
            store.log(f"{job.id} FAILED '{job.name}': {exc}", "ERR")

    store.checkpoint()

def _dispatch(job: Job) -> None:
    """Start the real workload. Called with store.lock held."""
    if sum(j.status == "RUNNING" for j in store.jobs.values()) >= 4:
        return
    vnow = clock.now()
    decision = store.decisions.get(job.id)
    job.target_region = decision.target_region if decision else job.home_region
    try:
        slots = registry.forecast(job.target_region, vnow, job.data_mode,
                                  job.forecast_method if job.target_region == job.home_region else "provider")
    except ValueError as exc:
        # An untrained learned model or a region that lost its feed. Hold the
        # job rather than letting the exception escape tick() and stall every
        # other job in the queue.
        job.status = "WAITING"
        store.log(f"{job.id}: cannot dispatch yet ({exc})", "WARN")
        return

    scored = score_window(slots, vnow, job.duration_minutes, job.energy_kwh)
    if scored is None:
        job.status = "WAITING"
        store.log(f"{job.id}: selected region forecast expired; awaiting refresh", "WARN")
        return
    job.status = "RUNNING"
    job.started_iso = iso(vnow)
    job.run_at_iso = iso(vnow)
    job.progress = 0.0
    job.execution_plan = {
        "baseline_carbon_g": store.baselines.get(job.id), "estimated_carbon_g": scored[0],
        "baseline_cost_gbp": store.baseline_costs.get(job.id), "modelled_cost_gbp": scored[1],
        "scheduled_at": decision.run_at_iso if decision else iso(vnow),
        "dispatched_at": iso(vnow), "target_region": job.target_region,
        "forecast_method": job.forecast_method, "data_mode": job.data_mode,
        "source_kinds": sorted({s.source_kind for s in slots}),
        "execution": "local CPU demo", "energy_basis": "declared energy budget",
        "energy_kwh": job.energy_kwh, "duration_minutes": job.duration_minutes,
        "forecast": [s.model_dump() for s in slots],
        "model": learned.status() if job.forecast_method == "learned" else None,
    }
    if scored:
        actual_carbon, actual_cost = scored
        store.actual_carbon[job.id] = actual_carbon
        store.actual_cost[job.id] = actual_cost
        baseline = store.baselines.get(job.id, actual_carbon)
        saved = _zero_clean(baseline - actual_carbon)
        store.log(
            f"{job.id} EXECUTE '{job.name}' at {slots[0].intensity_gco2_kwh:.0f} gCO2/kWh "
            f"-> {actual_carbon:.1f} gCO2 estimated emissions, {saved:.1f} gCO2 avoided vs submit-time baseline",
            "RUN",
        )
    else:
        store.log(f"{job.id} EXECUTE '{job.name}'", "RUN")

    def progress(p: float) -> None:
        job.progress = round(p, 3)

    future = pool.submit(run_job, job, progress)
    future.add_done_callback(lambda f, jid=job.id: _on_finished(jid, f))


def tick() -> None:
    try:
        _tick()
    except Exception:  # noqa: BLE001 - the scheduler thread must never die
        log.exception("Scheduler tick failed; the queue continues on the next tick")


def _tick() -> None:
    vnow = clock.now()
    slots = feed.forecast(vnow)
    if not slots:
        return

    with store.lock:
        for job in list(store.jobs.values()):
            if job.status in ("RUNNING", "DONE", "FAILED", "MISSED"):
                continue

            deadline = parse_iso(job.deadline_iso)
            if vnow + timedelta(minutes=job.duration_minutes) > deadline:
                # The last moment we could have started and still finished in
                # time has passed. Record the missed deadline without executing late.
                store.log(
                    f"{job.id} DEADLINE MISSED '{job.name}': {job.deadline_iso} is no longer feasible",
                    "WARN",
                )
                job.status = "MISSED"
                store.log(f"{job.id} MISSED: no execution window remains before the deadline", "WARN")
                continue

            previous = store.decisions.get(job.id)

            # An operator-chosen window is a commitment, not a suggestion. Leave
            # it where they put it and just wait for it; re-optimising would
            # silently move a job the user deliberately placed.
            if job.pinned and previous is not None:
                job.status = "WAITING"
                job.run_at_iso = previous.run_at_iso
                if parse_iso(previous.run_at_iso) <= vnow:
                    _dispatch(job)
                continue

            if previous and previous.action in ("WAIT", "SHIFT") and parse_iso(previous.run_at_iso) <= vnow:
                _dispatch(job)
                continue
            try:
                decision = registry.plan(job, vnow)
            except ValueError as exc:
                if job.status != "WAITING":
                    store.log(f"{job.id}: waiting for usable forecast coverage: {exc}", "WARN")
                job.status = "WAITING"
                continue
            previous = store.decisions.get(job.id)

            if job.id not in store.baselines:
                store.baselines[job.id] = decision.baseline_carbon_g
                store.baseline_costs[job.id] = decision.baseline_cost_gbp

            # A RUN decision's run_at is always "now", which moves every tick,
            # so only a WAIT window shifting counts as a real change.
            changed = previous is None or previous.action != decision.action or (
                decision.action in ("WAIT", "SHIFT") and (previous.run_at_iso != decision.run_at_iso or previous.target_region != decision.target_region)
            )
            store.set_decision(decision)

            if decision.action == "RUN" or (decision.action == "SHIFT" and parse_iso(decision.run_at_iso) <= vnow):
                if previous is not None and previous.action == "WAIT":
                    store.log(
                        f"{job.id} REPLAN -> RUN NOW: {decision.reason}", "PLAN"
                    )
                _dispatch(job)
                continue

            job.status = "WAITING"
            job.run_at_iso = decision.run_at_iso
            if changed:
                verb = "REPLAN" if previous is not None else "PLAN"
                store.log(
                    f"{job.id} {verb} -> {decision.action} ({decision.target_region}) until {decision.run_at_iso} "
                    f"(-{decision.carbon_saved_pct:.1f}% CO2, "
                    f"-{decision.cost_saved_pct:.1f}% cost)",
                    "PLAN",
                )

            if parse_iso(decision.run_at_iso) <= vnow:
                _dispatch(job)

    store.checkpoint()

def start() -> None:
    scheduler.add_job(
        refresh_grid,
        "interval",
        seconds=config.GRID_REFRESH_SECONDS,
        id="refresh_grid",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tick,
        "interval",
        seconds=config.TICK_SECONDS,
        id="tick",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
