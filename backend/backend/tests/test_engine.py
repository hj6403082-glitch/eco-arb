"""Decision-engine tests. Run: ./.venv/bin/python -m pytest tests -q"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app.carbon import feed
from app.clock import iso, parse_iso
from app.engine import decide, score_window
from app.models import Grid, Job

NOON = parse_iso("2026-09-18T12:00:00Z")


def flat_slots(n=48, intensity=200.0, price=100.0, start=NOON):
    return [
        Grid(
            timestamp=iso(start + timedelta(minutes=30 * k)),
            intensity_gco2_kwh=intensity,
            renewable_pct=50.0,
            price=price,
        )
        for k in range(n)
    ]


def job(**kw):
    base = dict(
        id="j1",
        name="test",
        energy_kwh=10.0,
        deadline_iso=iso(NOON + timedelta(hours=24)),
        duration_minutes=60.0,
    )
    base.update(kw)
    return Job(**base)


def test_score_window_is_energy_weighted_not_slot_counted():
    # 45 minutes over slots of 200 then 100 gCO2/kWh: 30min at 200, 15 at 100.
    slots = flat_slots()
    slots[1] = slots[1].model_copy(update={"intensity_gco2_kwh": 100.0})
    carbon, _ = score_window(slots, NOON, 45.0, 9.0)
    expected = 9.0 * (30 / 45) * 200 + 9.0 * (15 / 45) * 100
    assert abs(carbon - expected) < 1e-6, (carbon, expected)


def test_flat_grid_runs_now():
    d = decide(job(), flat_slots(), NOON)
    assert d.action == "RUN"
    assert d.carbon_saved_pct == 0.0


def test_defers_to_the_clean_trough():
    slots = flat_slots(intensity=300.0)
    for k in (10, 11, 12):  # 17:00-18:30 window is clean
        slots[k] = slots[k].model_copy(update={"intensity_gco2_kwh": 60.0})
    d = decide(job(duration_minutes=60.0), slots, NOON)
    assert d.action == "WAIT"
    assert d.run_at_iso == slots[10].timestamp
    # 10 kWh at 300 -> 3000g; at 60 -> 600g; 80% saved.
    assert abs(d.carbon_saved_pct - 80.0) < 0.01, d.carbon_saved_pct
    assert d.optimal_carbon_g < d.baseline_carbon_g


def test_tight_deadline_forces_run_and_says_so():
    slots = flat_slots(intensity=300.0)
    slots[6] = slots[6].model_copy(update={"intensity_gco2_kwh": 10.0})
    d = decide(
        job(duration_minutes=60.0, deadline_iso=iso(NOON + timedelta(minutes=70))),
        slots,
        NOON,
    )
    assert d.action == "RUN"
    assert "eadline" in d.reason


def test_never_schedules_past_the_deadline():
    slots = flat_slots(intensity=300.0)
    slots[40] = slots[40].model_copy(update={"intensity_gco2_kwh": 5.0})  # clean, but late
    deadline = NOON + timedelta(hours=4)
    d = decide(job(duration_minutes=60.0, deadline_iso=iso(deadline)), slots, NOON)
    assert parse_iso(d.window_end_iso) <= deadline


def test_saving_below_threshold_runs_now():
    slots = flat_slots(intensity=200.0)
    slots[5] = slots[5].model_copy(update={"intensity_gco2_kwh": 199.0})  # 0.5% better
    d = decide(job(duration_minutes=60.0), slots, NOON)
    assert d.action == "RUN"


def test_cost_is_reported_but_never_optimised():
    # Cheapest slot is NOT the cleanest; engine must pick the cleanest.
    slots = flat_slots(intensity=300.0, price=100.0)
    # The clean region must be at least as wide as the job, or a window
    # straddling its edge scores identically and the tie goes to the earlier start.
    for k in (8, 9):
        slots[k] = slots[k].model_copy(update={"intensity_gco2_kwh": 50.0, "price": 150.0})
    for k in (20, 21):
        slots[k] = slots[k].model_copy(update={"intensity_gco2_kwh": 290.0, "price": 1.0})
    d = decide(job(duration_minutes=60.0), slots, NOON)
    assert d.run_at_iso == slots[8].timestamp, "engine must follow carbon, not price"
    assert d.cost_saved_pct < 0, "honest reporting: this greener slot costs more"


def test_real_fallback_curve_defers_evening_job_to_overnight():
    evening = parse_iso("2026-09-18T18:00:00Z")
    slots = feed.forecast(evening)
    d = decide(
        Job(
            id="j",
            name="nightly",
            energy_kwh=50.0,
            deadline_iso=iso(evening + timedelta(hours=24)),
            duration_minutes=120.0,
        ),
        slots,
        evening,
    )
    assert d.action == "WAIT"
    hour = parse_iso(d.run_at_iso).hour
    assert 0 <= hour <= 6, f"expected an overnight window, got {d.run_at_iso}"
    assert d.carbon_saved_pct > 20.0


def test_ties_go_to_the_earlier_window():
    # A 60-minute job against a single clean 30-minute slot: starting at the
    # slot top and starting half an hour early are worth exactly the same,
    # and the engine should take the earlier one rather than drift later.
    slots = flat_slots(intensity=300.0)
    slots[8] = slots[8].model_copy(update={"intensity_gco2_kwh": 50.0})
    d = decide(job(duration_minutes=60.0), slots, NOON)
    assert d.run_at_iso == slots[7].timestamp
