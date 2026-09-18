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

    # Piecewise-constant curves change slope when either end crosses a slot edge.
    # Include end-aligned windows as well as start-aligned windows.
    for slot in slots:
        end_aligned = parse_iso(slot.timestamp) - timedelta(minutes=job.duration_minutes)
        if end_aligned > now:
            candidates.append(end_aligned)
    latest = deadline - timedelta(minutes=job.duration_minutes)
    if latest >= now:
        candidates.append(latest)
    candidates = sorted(set(candidates))

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


def _candidate_starts(job: Job, slots: List[Grid], now: datetime) -> List[Tuple[datetime, str]]:
    """Every start that can be optimal, tagged with why it is a breakpoint.

    Identical set to the one `decide` searches -- this is the same enumeration,
    just kept rather than discarded, so the UI can show the real search.
    """
    deadline = parse_iso(job.deadline_iso)
    tagged: dict[datetime, str] = {now: "now"}
    for slot in slots:
        start = parse_iso(slot.timestamp)
        if start > now:
            tagged.setdefault(start, "slot-start")
    for slot in slots:
        end_aligned = parse_iso(slot.timestamp) - timedelta(minutes=job.duration_minutes)
        if end_aligned > now:
            tagged.setdefault(end_aligned, "slot-end")
    latest = deadline - timedelta(minutes=job.duration_minutes)
    if latest >= now:
        tagged.setdefault(latest, "deadline")
    return sorted(tagged.items())


def evaluate_candidates(job: Job, slots: List[Grid], now: datetime) -> List[dict]:
    """Score every candidate start. This is the trace the decision theatre draws."""
    deadline = parse_iso(job.deadline_iso)
    baseline = score_window(slots, now, job.duration_minutes, job.energy_kwh)
    baseline_carbon = baseline[0] if baseline else 0.0
    baseline_cost = baseline[1] if baseline else 0.0

    rows: List[dict] = []
    for start, why in _candidate_starts(job, slots, now):
        feasible = start + timedelta(minutes=job.duration_minutes) <= deadline
        scored = score_window(slots, start, job.duration_minutes, job.energy_kwh) if feasible else None
        row = {
            "start_iso": iso(start),
            "end_iso": iso(start + timedelta(minutes=job.duration_minutes)),
            "breakpoint": why,
            "feasible": bool(scored),
            "delay_hours": round((start - now).total_seconds() / 3600.0, 2),
        }
        if scored:
            carbon, cost = scored
            row.update(
                carbon_g=round(carbon, 1),
                cost_gbp=round(cost, 4),
                carbon_saved_pct=round(
                    (baseline_carbon - carbon) / baseline_carbon * 100.0 if baseline_carbon > 0 else 0.0, 2
                ),
                cost_saved_pct=round(
                    (baseline_cost - cost) / baseline_cost * 100.0 if baseline_cost > 0 else 0.0, 2
                ),
                avg_intensity=round(carbon / job.energy_kwh, 1) if job.energy_kwh else 0.0,
            )
        else:
            row.update(carbon_g=None, cost_gbp=None, carbon_saved_pct=None,
                       cost_saved_pct=None, avg_intensity=None)
        rows.append(row)
    return rows


def recommend(
    job: Job,
    slots: List[Grid],
    now: datetime,
    limit: int = 4,
    spacing_minutes: float = 20.0,
    min_gap_pct: float = 1.0,
) -> dict:
    """Top-N genuinely distinct windows, best first, with 'run now' always offered.

    Adjacent breakpoints often differ by a minute and a fraction of a gram, which
    is not a choice. An option has to be both `spacing_minutes` away from every
    option already picked AND at least `min_gap_pct` percentage points different
    in savings -- two rows that both read "-30.7%" are noise, not alternatives.
    """
    trace = evaluate_candidates(job, slots, now)
    feasible = [r for r in trace if r["feasible"]]
    run_now = next((r for r in trace if r["breakpoint"] == "now" and r["feasible"]), None)

    # Only windows that actually beat running now are worth offering. Most
    # breakpoints are worse than the status quo; presenting those as
    # "recommendations" would be actively misleading.
    ceiling = run_now["carbon_g"] if run_now else None
    picked: List[dict] = []
    for row in sorted(feasible, key=lambda r: r["carbon_g"]):
        if row["breakpoint"] == "now":
            continue
        if ceiling is not None and row["carbon_g"] >= ceiling - 1e-9:
            continue
        start = parse_iso(row["start_iso"])
        if any(
            abs((start - parse_iso(p["start_iso"])).total_seconds()) < spacing_minutes * 60
            or abs(row["carbon_saved_pct"] - p["carbon_saved_pct"]) < min_gap_pct
            for p in picked
        ):
            continue
        picked.append(row)
        if len(picked) >= limit - 1:
            break

    options = []
    for rank, row in enumerate(picked):
        label = "Cleanest reachable window" if rank == 0 else (
            "Near-optimal, earlier" if parse_iso(row["start_iso"]) < parse_iso(picked[0]["start_iso"])
            else "Near-optimal alternative"
        )
        options.append({**row, "label": label, "recommended": rank == 0})
    if run_now:
        options.append({**run_now, "label": "Run immediately, no deferral", "recommended": not picked})

    return {
        "options": options,
        "trace": trace,
        "candidates_considered": len(trace),
        "feasible_windows": len(feasible),
        "baseline_carbon_g": run_now["carbon_g"] if run_now else None,
        "deadline_iso": job.deadline_iso,
        "now_iso": iso(now),
    }


def decision_for_window(job: Job, slots: List[Grid], now: datetime, start: datetime) -> Decision:
    """A Decision describing a window the operator picked, scored the same way.

    Used when a recommendation is accepted: the numbers must come from the same
    `score_window` the engine optimises with, or the UI would report savings the
    engine never computed.
    """
    baseline = score_window(slots, now, job.duration_minutes, job.energy_kwh)
    chosen = score_window(slots, start, job.duration_minutes, job.energy_kwh)
    baseline_carbon, baseline_cost = baseline if baseline else (0.0, 0.0)
    carbon, cost = chosen if chosen else (baseline_carbon, baseline_cost)

    saved_pct = (baseline_carbon - carbon) / baseline_carbon * 100.0 if baseline_carbon > 0 else 0.0
    cost_saved_pct = (baseline_cost - cost) / baseline_cost * 100.0 if baseline_cost > 0 else 0.0
    immediate = start <= now
    if immediate:
        reason = "Operator chose to run immediately; no deferral."
    else:
        delay_h = (start - now).total_seconds() / 3600.0
        reason = (
            f"Operator selected the {iso(start)} window from the ranked "
            f"recommendations: deferring {delay_h:.1f}h cuts "
            f"{baseline_carbon - carbon:.0f} gCO2 ({saved_pct:.1f}%). "
            f"Deadline {job.deadline_iso} still met."
        )
    return Decision(
        job_id=job.id,
        action="RUN" if immediate else "WAIT",
        run_at_iso=iso(now if immediate else start),
        carbon_saved_pct=round(0.0 if immediate else saved_pct, 2),
        cost_saved_pct=round(0.0 if immediate else cost_saved_pct, 2),
        reason=reason,
        baseline_carbon_g=round(baseline_carbon, 1),
        optimal_carbon_g=round(baseline_carbon if immediate else carbon, 1),
        baseline_cost_gbp=round(baseline_cost, 4),
        optimal_cost_gbp=round(baseline_cost if immediate else cost, 4),
        window_end_iso=iso((now if immediate else start) + timedelta(minutes=job.duration_minutes)),
        decided_at_iso=iso(now),
        slots_considered=len(slots),
        feasible_windows=sum(1 for r in evaluate_candidates(job, slots, now) if r["feasible"]),
    )
