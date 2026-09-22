"""Regression checks for API validation, accounting, persistence and execution."""
import sys
from pathlib import Path
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.store import store, Store
from app.clock import clock, iso, parse_iso
from app.models import Job, Grid
from app.engine import decide
from app.executor import hash_grind, verify_hash_grind
from app import scheduler, executor
from app.carbon import GridFeed

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'path', tmp_path/'state.json')
    for key in ('jobs','decisions','baselines','baseline_costs','actual_carbon','actual_cost'):
        getattr(store,key).clear()
    store.logs.clear()
    clock.set_speed(1)
    clock.reset()
    yield
    for key in ('jobs','decisions','baselines','baseline_costs','actual_carbon','actual_cost'):
        getattr(store,key).clear()

client=TestClient(app)
def payload(**kw):
    return dict(name='climate-validation', energy_kwh=4, duration_minutes=30, deadline_hours=12, **kw)

@pytest.mark.parametrize('field,value', [('name',''),('name','   '),('energy_kwh',0),('energy_kwh',-4),('duration_minutes',1500),('deadline_hours',25),('deadline_iso','yesterday')])
def test_invalid_submission_is_422(field,value):
    p=payload();p[field]=value
    assert client.post('/api/jobs',json=p).status_code==422
    assert not store.jobs

def test_impossible_deadline_rejected():
    p=payload();p['duration_minutes']=120;p['deadline_hours']=1
    assert client.post('/api/jobs',json=p).status_code==422

def test_preview_does_not_create_jobs():
    r=client.post('/api/preview',json=payload())
    assert r.status_code==200
    assert r.json()['feasible_windows']>0
    assert not store.jobs

def test_submit_freezes_baseline_and_persists():
    r=client.post('/api/jobs',json=payload());assert r.status_code==200
    job_id=r.json()['job']['id']
    assert store.baselines[job_id]==r.json()['decision']['baseline_carbon_g']
    assert store.path.exists()

def test_only_completed_jobs_count_toward_impact():
    j=Job(id='t',name='test',energy_kwh=10,deadline_iso=iso(clock.now()+timedelta(hours=1)),status='RUNNING')
    store.add(j);store.baselines['t']=2000;store.actual_carbon['t']=1000
    assert store.totals()['carbon_saved_g']==0
    j.status='FAILED';assert store.totals()['carbon_saved_g']==0
    j.status='DONE';assert store.totals()['carbon_saved_g']==1000
    assert store.totals()['jobs_completed']==1

def test_reset_and_cancel_preserve_running_work():
    r=client.post('/api/jobs',json=payload()).json();jid=r['job']['id'];store.jobs[jid].status='RUNNING'
    assert client.delete('/api/jobs/'+jid).status_code==409
    assert client.post('/api/reset').status_code==409
    assert jid in store.jobs

def test_cancel_pending_work():
    jid=client.post('/api/jobs',json=payload()).json()['job']['id']
    assert client.delete('/api/jobs/'+jid).status_code==200
    assert jid not in store.jobs

def test_persistence_restores_and_marks_interrupted_work(tmp_path,monkeypatch):
    jid=client.post('/api/jobs',json=payload()).json()['job']['id']
    store.jobs[jid].status='RUNNING';store.checkpoint()
    monkeypatch.setenv('ECO_ARB_STATE',str(store.path))
    restored=Store();assert restored.jobs[jid].status=='FAILED'
    assert restored.baselines==store.baselines
    assert restored.next_id()!=jid

def test_scheduler_does_not_execute_impossible_work(monkeypatch):
    j=Job(id='late',name='late',energy_kwh=1,deadline_iso=iso(clock.now()-timedelta(minutes=1)))
    store.add(j)
    monkeypatch.setattr(scheduler,'_dispatch',lambda *a: pytest.fail('Must not execute missed job'))
    scheduler.tick();assert j.status=='MISSED'

def test_end_aligned_window_is_considered():
    now=parse_iso('2026-01-01T00:00:00Z')
    slots=[Grid(timestamp=iso(now+timedelta(minutes=i*30)),intensity_gco2_kwh=v,renewable_pct=50,price=100) for i,v in enumerate([300,50,200,500])]
    job=Job(id='edge',name='edge',energy_kwh=1,duration_minutes=45,deadline_iso=iso(now+timedelta(hours=2)))
    d=decide(job,slots,now)
    assert d.action=='WAIT'
    assert d.run_at_iso==iso(now+timedelta(minutes=30))

def test_real_hash_work_can_be_independently_verified(monkeypatch):
    monkeypatch.setattr(executor,'_rounds_for',lambda _:10000)
    j=Job(id='proof',name='proof',energy_kwh=1,deadline_iso=iso(clock.now()+timedelta(hours=1)))
    result=hash_grind(j,lambda _:None)
    assert verify_hash_grind(result)
    root=result['merkle_root'];result['merkle_root']='bad'
    assert not verify_hash_grind(result)
    result['merkle_root']=root
    result['final_digest']='bad';assert not verify_hash_grind(result)

def test_feed_failure_clears_live_label(monkeypatch):
    f=GridFeed();f._live=True;f._last_fetch_iso=iso(clock.now())
    def fail(*a,**kw):raise RuntimeError('offline')
    monkeypatch.setattr('app.carbon.httpx.get',fail)
    assert not f.refresh()
    assert not f.status()['live']
    assert f.status()['cached']


def test_worker_capacity_does_not_mark_queued_work_running():
    for i in range(4):
        store.add(Job(id=str(i),name="busy",energy_kwh=1,status="RUNNING",deadline_iso=iso(clock.now()+timedelta(hours=1))))
    queued=Job(id="next",name="next",energy_kwh=1,deadline_iso=iso(clock.now()+timedelta(hours=1)))
    store.add(queued)
    scheduler._dispatch(queued)
    assert queued.status=="QUEUED"

def test_zero_dispatch_slack_is_rejected():
    p=payload();p['duration_minutes']=60;p['deadline_hours']=1
    assert client.post('/api/jobs',json=p).status_code==422


# --- ranked recommendations and operator-chosen windows -----------------------

def _ramp_slots(now, values):
    from app.models import Grid
    from app.clock import iso
    from datetime import timedelta
    return [
        Grid(timestamp=iso(now + timedelta(minutes=30 * i)), intensity_gco2_kwh=v,
             renewable_pct=50.0, price=50.0)
        for i, v in enumerate(values)
    ]


def test_recommend_top_option_matches_the_engine_optimum():
    """The ranked list must agree with decide(); two answers would be one too many."""
    from datetime import datetime, timedelta, timezone
    from app.engine import recommend, decide
    from app.models import Job
    from app.clock import iso
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    slots = _ramp_slots(now, [100, 10, 200, 200, 200, 150, 120, 90, 80, 200, 200, 200])
    job = Job(id="j", name="j", energy_kwh=9, duration_minutes=45,
              deadline_iso=iso(now + timedelta(hours=5)))
    best = recommend(job, slots, now)["options"][0]
    assert best["start_iso"] == decide(job, slots, now).run_at_iso


def test_recommend_never_offers_a_window_worse_than_running_now():
    from datetime import datetime, timedelta, timezone
    from app.engine import recommend
    from app.models import Job
    from app.clock import iso
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    slots = _ramp_slots(now, [100, 10, 200, 200, 200, 150, 120, 90, 80, 200, 200, 200])
    job = Job(id="j", name="j", energy_kwh=9, duration_minutes=45,
              deadline_iso=iso(now + timedelta(hours=5)))
    result = recommend(job, slots, now)
    run_now = [o for o in result["options"] if o["breakpoint"] == "now"][0]
    for option in result["options"]:
        assert option["carbon_g"] <= run_now["carbon_g"] + 1e-9


def test_flat_curve_offers_only_running_now():
    """Nothing beats the status quo on a flat curve, so nothing else is offered."""
    from datetime import datetime, timedelta, timezone
    from app.engine import recommend
    from app.models import Job
    from app.clock import iso
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    job = Job(id="j", name="j", energy_kwh=9, duration_minutes=45,
              deadline_iso=iso(now + timedelta(hours=5)))
    options = recommend(job, _ramp_slots(now, [150] * 12), now)["options"]
    assert len(options) == 1 and options[0]["breakpoint"] == "now"


def test_trace_covers_every_candidate_the_engine_searches():
    from datetime import datetime, timedelta, timezone
    from app.engine import recommend, decide
    from app.models import Job
    from app.clock import iso
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    slots = _ramp_slots(now, [100, 10, 200, 200, 200, 150, 120, 90, 80, 200, 200, 200])
    job = Job(id="j", name="j", energy_kwh=9, duration_minutes=45,
              deadline_iso=iso(now + timedelta(hours=5)))
    result = recommend(job, slots, now)
    assert sum(1 for r in result["trace"] if r["feasible"]) == decide(job, slots, now).feasible_windows


def test_chosen_window_is_scored_by_the_same_function():
    from datetime import datetime, timedelta, timezone
    from app.engine import decision_for_window, score_window
    from app.models import Job
    from app.clock import iso, parse_iso
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    slots = _ramp_slots(now, [100, 10, 200, 200, 200, 150, 120, 90, 80, 200, 200, 200])
    job = Job(id="j", name="j", energy_kwh=9, duration_minutes=45,
              deadline_iso=iso(now + timedelta(hours=5)))
    start = now + timedelta(hours=3)
    decision = decision_for_window(job, slots, now, start)
    expected, _ = score_window(slots, start, job.duration_minutes, job.energy_kwh)
    assert decision.optimal_carbon_g == round(expected, 1)
    assert decision.run_at_iso == iso(start)


def test_pinned_job_keeps_its_window_when_the_scheduler_replans():
    """A window the operator picked must survive an actual scheduler tick.

    The earlier version of this test only asserted back the arguments it had
    just passed to the Job constructor, so the pinned branch in scheduler.tick
    was never executed.
    """
    from datetime import timedelta
    from app import scheduler
    from app.clock import clock, iso, parse_iso
    from app.models import Decision, Job
    from app.store import store

    with store.lock:
        store.jobs.clear()
        store.decisions.clear()

    vnow = clock.now()
    chosen = parse_iso(iso(vnow + timedelta(hours=3)))
    job = Job(id="pinned-1", name="pinned", energy_kwh=1, duration_minutes=30,
              deadline_iso=iso(vnow + timedelta(hours=8)), pinned=True,
              run_at_iso=iso(chosen), status="WAITING")
    with store.lock:
        store.add(job)
        store.set_decision(Decision(
            job_id=job.id, action="WAIT", run_at_iso=iso(chosen),
            carbon_saved_pct=12.0, cost_saved_pct=8.0, reason="operator choice",
            window_end_iso=iso(chosen + timedelta(minutes=30)), decided_at_iso=iso(vnow)))

    scheduler.tick()          # the real scheduler, not a stand-in

    kept = store.get("pinned-1")
    assert kept.pinned is True
    assert kept.run_at_iso == iso(chosen), "the scheduler moved an operator-chosen window"
    assert store.decisions["pinned-1"].run_at_iso == iso(chosen)

    with store.lock:
        store.jobs.clear()
        store.decisions.clear()


# --- persistence must never take the app down -------------------------------

def test_checkpoint_survives_a_locked_target(tmp_path, monkeypatch):
    """Windows raises PermissionError when anything holds the target file.

    OneDrive watches C:/Users/<name>/Documents by default, so this fired during
    a live demo and 500'd job creation. A checkpoint is a convenience; losing one
    must never fail the request that triggered it.
    """
    import os
    from app.fsutil import write_json_atomic

    target = tmp_path / "state.json"
    assert write_json_atomic(target, {"v": 1}, label="test") is True

    def always_locked(src, dst):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(os, "replace", always_locked)
    assert write_json_atomic(target, {"v": 2}, label="test") is False
    assert target.read_text() == '{"v": 1}'          # previous state left intact
    assert not (tmp_path / "state.tmp").exists()      # no litter


def test_checkpoint_retries_a_transient_lock(tmp_path, monkeypatch):
    import os
    from app.fsutil import write_json_atomic

    target = tmp_path / "state.json"
    real, attempts = os.replace, {"n": 0}

    def flaky(src, dst):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    assert write_json_atomic(target, {"v": 9}, label="test") is True
    assert attempts["n"] == 3
    assert target.read_text() == '{"v": 9}'


def test_job_creation_succeeds_when_the_state_file_cannot_be_written(monkeypatch):
    """The original failure: create_job 500'd because checkpoint raised."""
    import os
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(os, "replace", lambda src, dst: (_ for _ in ()).throw(
        PermissionError(5, "Access is denied")))
    with TestClient(app) as client:
        response = client.post("/api/jobs", json={
            "name": "locked-disk-job", "energy_kwh": 1,
            "duration_minutes": 30, "deadline_hours": 6})
    assert response.status_code == 200, response.text
    assert response.json()["job"]["name"] == "locked-disk-job"


# --- India: carbon intensity derived from a published generation mix ---------

def test_intensity_from_mix_matches_hand_calculation():
    """The arithmetic must be exactly mix-weighted factors, not an approximation."""
    from app.emissions import EMISSION_FACTORS, intensity_from_mix
    mix = {"Coal": 1000.0, "Solar": 1000.0}
    intensity, renewable, _ = intensity_from_mix(mix)
    assert intensity == round((1000 * EMISSION_FACTORS["coal"] + 1000 * 0.0) / 2000, 1)
    assert renewable == 50.0


def test_mix_renewable_share_is_measured_not_derived():
    """Unlike the UK national path, renewable % here comes from the mix itself."""
    from app.emissions import intensity_from_mix
    _, renewable, _ = intensity_from_mix(
        {"Coal": 5000, "Hydro": 2000, "Wind": 2000, "Solar": 1000})
    assert renewable == 50.0


def test_mix_rejects_empty_and_negative_generation():
    from app.emissions import intensity_from_mix
    import pytest
    with pytest.raises(ValueError):
        intensity_from_mix({"Coal": 0})
    with pytest.raises(ValueError):
        intensity_from_mix({"Coal": -10})


def test_unknown_fuel_labels_are_flagged_not_silently_counted():
    """An unrecognised fuel gets the generic factor, and the caller is told."""
    from app.emissions import normalise_fuel, unknown_fuels
    assert normalise_fuel("Fusion Reactor") == "other"
    assert unknown_fuels(["Coal", "Fusion Reactor", "Solar"]) == ["Fusion Reactor"]
    assert unknown_fuels(["Coal", "Other"]) == []


def test_cea_style_fuel_labels_are_recognised():
    from app.emissions import normalise_fuel
    for label, expected in [("Large Hydro", "hydro"), ("Small hydro", "hydro"),
                            ("Solar PV", "solar"), ("Thermal (Coal)", "other"),
                            ("coal", "coal"), ("LIGNITE", "lignite"),
                            ("Gas Turbine", "gas"), ("Bagasse", "bagasse")]:
        assert normalise_fuel(label) == expected, label


def test_recommend_without_an_immediate_baseline_reports_undefined_savings():
    """An imported forecast can start after 'now'; savings are then undefined.

    Reporting 0% would be a claim we cannot support, and it collapsed the ranked
    list to a single row because every option looked identical.
    """
    from datetime import datetime, timedelta, timezone
    from app.engine import recommend
    from app.models import Job
    from app.clock import iso
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    # Forecast begins two hours after "now", so nothing can run immediately.
    slots = _ramp_slots(now + timedelta(hours=2),
                        [300, 280, 210, 160, 120, 140, 190, 240, 260, 280, 300, 320])
    job = Job(id="j", name="j", energy_kwh=9, duration_minutes=45,
              deadline_iso=iso(now + timedelta(hours=9)))
    result = recommend(job, slots, now)
    assert result["baseline_available"] is False
    assert all(o["carbon_saved_pct"] is None for o in result["options"])
    assert len(result["options"]) > 1, "ranking must not collapse without a baseline"
    carbons = [o["carbon_g"] for o in result["options"]]
    assert carbons == sorted(carbons), "options must still be ordered by carbon"


# --- the app must survive its own bad files and one bad job -----------------

def test_a_corrupt_state_file_does_not_stop_the_app_starting(tmp_path):
    """An interrupted write is exactly what atomic saving exists to survive.

    Refusing to boot because of one turned a recoverable glitch into a dead
    application -- and the Windows file-locking path makes truncated writes a
    real possibility rather than a theoretical one.
    """
    from app.store import Store
    broken = tmp_path / "state.json"
    broken.write_text('{"seq":', encoding="utf-8")
    store = Store(path=broken) if "path" in Store.__init__.__code__.co_varnames else None
    if store is None:                       # Store reads its path from the environment
        import os
        os.environ["ECO_ARB_STATE"] = str(broken)
        store = Store()
    assert store.jobs == {}
    assert (tmp_path / "state.json.unreadable").exists(), "the bad file should be kept, not deleted"


def test_a_corrupt_region_cache_does_not_stop_the_app_starting(tmp_path):
    from app.regions import RegionRegistry
    broken = tmp_path / "regions.json"
    broken.write_text('{"rows": {"in-north": [{"bogus": 1}]}, "sources": {}}', encoding="utf-8")
    registry = RegionRegistry(path=broken)
    assert registry.rows == {}
    assert (tmp_path / "regions.json.unreadable").exists()


def test_one_undispatchable_job_does_not_stall_the_whole_queue(monkeypatch):
    """registry.forecast raising inside _dispatch used to escape tick().

    Every later job in the loop was then skipped, and so was the checkpoint, on
    that tick and every tick after it.
    """
    from datetime import timedelta
    from app import scheduler
    from app.clock import clock, iso
    from app.models import Job
    from app.store import store

    with store.lock:
        store.jobs.clear()
        store.decisions.clear()

    vnow = clock.now()
    job = Job(id="bad-1", name="bad", energy_kwh=1, duration_minutes=30,
              deadline_iso=iso(vnow + timedelta(hours=6)), status="QUEUED")
    with store.lock:
        store.add(job)

    def explode(*args, **kwargs):
        raise ValueError("region feed vanished")

    monkeypatch.setattr(scheduler.registry, "forecast", explode)
    scheduler._dispatch(job)                      # must not raise
    assert store.get("bad-1").status == "WAITING"

    scheduler.tick()                              # must not raise either

    with store.lock:
        store.jobs.clear()
        store.decisions.clear()


def test_speeding_up_only_refuses_when_it_would_strand_a_waiting_job():
    """Compressing time is the demo. Only a speed-up that outruns a job's
    remaining slack is refused; a roomy deadline, and slowing down, are not."""
    from datetime import timedelta
    from fastapi.testclient import TestClient
    from app import config
    from app.clock import clock, iso
    from app.main import app
    from app.models import Job
    from app.store import store

    # One tick at 360x advances this much virtual time.
    tick = timedelta(seconds=config.TICK_SECONDS * 360)

    def queue(slack: timedelta) -> None:
        with store.lock:
            store.jobs.clear()
            store.decisions.clear()
            store.add(Job(id="hold-1", name="hold", energy_kwh=1, duration_minutes=30,
                          deadline_iso=iso(clock.now() + timedelta(minutes=30) + slack),
                          status="WAITING"))

    try:
        # Slack smaller than one tick: the next tick would jump past the
        # deadline, so the speed-up is refused.
        queue(tick / 2)
        with TestClient(app) as client:
            assert client.post("/api/speed", json={"speed": 360}).status_code == 409
            assert clock.speed == 1

        # Plenty of slack: this is the ordinary demo flow and must work.
        queue(timedelta(hours=6))
        with TestClient(app) as client:
            assert client.post("/api/speed", json={"speed": 360}).status_code == 200
            assert clock.speed == 360
            # Slowing down can never strand anything, even with work pending.
            assert client.post("/api/speed", json={"speed": 1}).status_code == 200
            assert clock.speed == 1
    finally:
        clock.set_speed(1)
        with store.lock:
            store.jobs.clear()
            store.decisions.clear()


def test_indian_intensities_do_not_collapse_to_the_british_renewable_floor():
    """carbon.derive_renewable_pct saturates at 400 gCO2/kWh, which is below
    every value the Indian grid produces, so it returned a flat 5% for all of
    them. India has its own fit."""
    from app.carbon import derive_renewable_pct as gb_fit
    from app.india import derive_renewable_pct as in_fit

    indian_range = (487.0, 550.0, 574.0, 667.0)

    # The British calibration is saturated across the whole Indian range.
    assert len({gb_fit(v) for v in indian_range}) == 1

    # The India fit is monotonic in the right direction and spans real ground.
    shares = [in_fit(v) for v in indian_range]
    assert shares == sorted(shares, reverse=True)
    assert 10.0 < min(shares) and max(shares) < 45.0

    # It reproduces the paired observations it was fitted to, within the
    # residual quoted in india.RENEWABLE_BASIS.
    for intensity, measured in ((457.0, 40.73), (461.0, 40.02), (550.0, 28.31)):
        assert abs(in_fit(intensity) - measured) < 2.0


def test_the_recorded_indian_forecast_is_real_data_and_says_so():
    from app.carbon import floor_to_slot
    from app.clock import real_now
    from app.india import recorded_india

    assert recorded_india.available
    rows = recorded_india.forecast(floor_to_slot(real_now()))

    # A full horizon of contiguous half-hours.
    assert len(rows) == 49
    assert all(r.source_kind == "recorded_real" for r in rows)

    # Replayed, so never flagged live -- the clock is not the capture's.
    assert not any(r.live for r in rows)

    # The real curve, unsmoothed: the provider's own range for that day.
    values = [r.intensity_gco2_kwh for r in rows]
    assert min(values) == 487.0 and max(values) == 667.0


def test_the_indian_national_region_has_data_without_a_key_or_network():
    """The point of the recorded capture: India is not an empty page for
    anyone who has no API key, and is never labelled as a live pull."""
    from app.clock import real_now
    from app.regions import registry

    described = {r["id"]: r for r in registry.describe(real_now())}
    india = described["in"]

    assert india["available"]
    assert india["current"]["source_kind"] == "recorded_real"
    assert "recorded" in india["source"].lower()
    assert not india["current"]["live"]


def test_the_browser_copy_of_the_indian_capture_matches_the_server_copy():
    """The hosted page bundles its own copy of the recorded capture. If the two
    drift, the static build and the backend quietly disagree about real data,
    which is exactly the failure the capture exists to prevent."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    server = root / "backend" / "app" / "data" / "india_recorded.json"
    browser = root / "frontend" / "src" / "data" / "india_recorded.json"

    assert browser.exists(), "the browser bundle is missing its copy of the capture"
    assert json.loads(server.read_text(encoding="utf-8")) == \
           json.loads(browser.read_text(encoding="utf-8"))
