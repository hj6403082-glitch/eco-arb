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
    scheduler._dispatch(queued,[])
    assert queued.status=="QUEUED"

def test_zero_dispatch_slack_is_rejected():
    p=payload();p['duration_minutes']=60;p['deadline_hours']=1
    assert client.post('/api/jobs',json=p).status_code==422
