"""Decision engine: exhaustive sliding window over the forecast slots.

For a job of duration D and energy E, every feasible start slot in the 24h
horizon is scored and the best is returned. "Feasible" means the window ends
on or before the deadline. Energy is spread evenly across the window, so a
window that straddles a slot boundary is weighted by the fraction of the slot
it actually occupies -- a 45-minute job does not get charged two full
half-hours of carbon.

Optimisation target is carbon, and only carbon. Cost is scored on the same
windows and reported alongside, but never breaks a tie.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from . import config
from .clock import iso, parse_iso
from .models import Decision, Grid, Job


def _overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0.0, (end - start).total_seconds() / 60.0)


def score_window(
    slots: List[Grid], start: datetime, duration_minutes: float, energy_kwh: float
) -> Optional[Tuple[float, float]]:
    """(carbon_g, cost_gbp) for running `energy_kwh` over [start, start+D).

    Returns None if the window runs off the end of the forecast.
    """
    end = start + timedelta(minutes=duration_minutes)
    slot_width = timedelta(minutes=config.SLOT_MINUTES)
    if not slots or end > parse_iso(slots[-1].timestamp) + slot_width:
        return None

    carbon_g = 0.0
    cost_gbp = 0.0
    covered = 0.0
    for slot in slots:
        slot_start = parse_iso(slot.timestamp)
        slot_end = slot_start + slot_width
        if slot_end <= start:
            continue
        if slot_start >= end:
            break
        minutes = _overlap_minutes(start, end, slot_start, slot_end)
        if minutes <= 0:
            continue
        share = minutes / duration_minutes
        covered += minutes
        energy_here = energy_kwh * share
        carbon_g += energy_here * slot.intensity_gco2_kwh
        # price is GBP/MWh, energy is kWh
        cost_gbp += energy_here * slot.price / 1000.0

    if covered + 1e-6 < duration_minutes:
        return None
    return carbon_g, cost_gbp


def decide(job: Job, slots: List[Grid], now: datetime) -> Decision:
    """Exhaustively slide the job's window across every forecast slot."""
    deadline = parse_iso(job.deadline_iso)
    slot_width = timedelta(minutes=config.SLOT_MINUTES)

    # Candidate starts: "right now", plus the top of every forecast slot at or
    # after now. Including `now` itself is what makes RUN a real option rather
    # than an artefact of slot alignment.
    candidates: List[datetime] = [now]
    for slot in slots:
        slot_start = parse_iso(slot.timestamp)
        if slot_start > now:
            candidates.append(slot_start)

    baseline = score_window(slots, now, job.duration_minutes, job.energy_kwh)
    if baseline is None:
        # Forecast does not even cover running immediately; nothing to reason
        # about, so run and say so.
        return Decision(
            job_id=job.id,
            action="RUN",
            run_at_iso=iso(now),
            carbon_saved_pct=0.0,
            cost_saved_pct=0.0,
            reason="Forecast horizon does not cover this job's duration; running now.",
            decided_at_iso=iso(now),
            slots_considered=len(slots),
            feasible_windows=0,
            window_end_iso=iso(now + timedelta(minutes=job.duration_minutes)),
        )

    baseline_carbon, baseline_cost = baseline
    best_start = now
    best_carbon, best_cost = baseline_carbon, baseline_cost
    feasible = 0

    for start in candidates:
        if start + timedelta(minutes=job.duration_minutes) > deadline:
            continue
        scored = score_window(slots, start, job.duration_minutes, job.energy_kwh)
        if scored is None:
            continue
        feasible += 1
        carbon, cost = scored
        if carbon < best_carbon - 1e-9:
            best_carbon, best_cost, best_start = carbon, cost, start

    deadline_binding = now + timedelta(minutes=job.duration_minutes) >= deadline - slot_width

    carbon_saved_pct = (
        (baseline_carbon - best_carbon) / baseline_carbon * 100.0 if baseline_carbon > 0 else 0.0
    )
    cost_saved_pct = (
        (baseline_cost - best_cost) / baseline_cost * 100.0 if baseline_cost > 0 else 0.0
    )

    if best_start <= now or carbon_saved_pct < config.MIN_SAVING_PCT:
        action = "RUN"
        run_at = now
        best_carbon, best_cost = baseline_carbon, baseline_cost
        carbon_saved_pct = 0.0
        cost_saved_pct = 0.0
        if deadline_binding:
            reason = (
                f"Deadline at {job.deadline_iso} leaves no room to defer "
                f"a {job.duration_minutes:.0f}-minute job. Running now."
            )
        else:
            reason = (
                f"Grid is already near its cleanest reachable point "
                f"({slots[0].intensity_gco2_kwh:.0f} gCO2/kWh); no window before the "
                f"deadline beats running now by more than {config.MIN_SAVING_PCT:.0f}%."
            )
    else:
        action = "WAIT"
        run_at = best_start
        delay_h = (best_start - now).total_seconds() / 3600.0
        avg_now = baseline_carbon / job.energy_kwh if job.energy_kwh else 0.0
        avg_then = best_carbon / job.energy_kwh if job.energy_kwh else 0.0
        reason = (
            f"Deferring {delay_h:.1f}h to {iso(best_start)} moves the job from "
            f"~{avg_now:.0f} to ~{avg_then:.0f} gCO2/kWh average intensity, "
            f"cutting {baseline_carbon - best_carbon:.0f} gCO2 "
            f"({carbon_saved_pct:.1f}%). Deadline {job.deadline_iso} still met."
        )

    return Decision(
        job_id=job.id,
        action=action,
        run_at_iso=iso(run_at),
        carbon_saved_pct=round(carbon_saved_pct, 2),
        cost_saved_pct=round(cost_saved_pct, 2),
        reason=reason,
        baseline_carbon_g=round(baseline_carbon, 1),
        optimal_carbon_g=round(best_carbon, 1),
        baseline_cost_gbp=round(baseline_cost, 4),
        optimal_cost_gbp=round(best_cost, 4),
        window_end_iso=iso(run_at + timedelta(minutes=job.duration_minutes)),
        decided_at_iso=iso(now),
        slots_considered=len(slots),
        feasible_windows=feasible,
    )
