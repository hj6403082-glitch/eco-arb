"""Decision, data provenance, and chronological learning acceptance checks."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.clock import iso, parse_iso
from app.models import Grid, Job
from app.learning import LearnedForecast, synthetic_history, fit, predict
from app.regions import RegionRegistry
from app.engine import decide

NOW = datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc)

def job(**kw):
    return Job(**(dict(id='test', name='test', energy_kwh=1, duration_minutes=30,
                      deadline_iso=iso(NOW+timedelta(hours=6)), data_mode='scenario') | kw))

def rows(values):
    return [Grid(timestamp=iso(NOW+timedelta(minutes=30*i)), intensity_gco2_kwh=v) for i,v in enumerate(values)]

def test_three_distinct_decisions():
    registry = RegionRegistry();registry.scenario_anchor=NOW
    urgent=registry.plan(job(duration_minutes=1,deadline_iso=iso(NOW+timedelta(minutes=12))),NOW)
    flexible=registry.plan(job(),NOW)
    shifted=registry.plan(job(home_region='in-north',allow_shift=True,allowed_regions=['in-south']),NOW)
    assert [urgent.action,flexible.action,shifted.action]==['RUN','WAIT','SHIFT']
    assert parse_iso(flexible.run_at_iso)==NOW+timedelta(hours=2)
    assert shifted.target_region=='in-south'
    assert shifted.optimal_carbon_g==140
    assert shifted.baseline_carbon_g==780
    assert shifted.data_basis=='synthetic_scenario'
    assert shifted.execution_mode=='local_demo'

def test_shift_never_escapes_allowlist():
    registry=RegionRegistry();registry.scenario_anchor=NOW
    d=registry.plan(job(home_region='in-north',allow_shift=True,allowed_regions=['gb-london']),NOW)
    assert d.target_region=='gb-london'
    assert {a['region'] for a in d.alternatives}=={'gb-london'}

def test_no_provider_means_no_india_operational_forecast():
    registry=RegionRegistry()
    assert registry.forecast('in-north',NOW)==[]
    with pytest.raises(ValueError,match='coverage'):
        registry.plan(job(home_region='in-north',data_mode='operational'),NOW)

@pytest.mark.parametrize('stamps', [[0,0],[0,60],[0,31]])
def test_import_rejects_duplicates_gaps_and_unaligned(stamps):
    registry=RegionRegistry()
    data=[Grid(timestamp=iso(NOW+timedelta(minutes=n)),intensity_gco2_kwh=500) for n in stamps]
    with pytest.raises(ValueError):registry.ingest('in-north',data,'test import')

def test_import_persists_as_unverified_not_live(tmp_path):
    path=tmp_path/'regions.json';registry=RegionRegistry(path)
    registry.ingest('in-north',list(reversed(rows([500,400,300]))),'operator file')
    restored=RegionRegistry(path)
    result=restored.forecast('in-north',NOW)
    assert len(result)==3
    assert all(r.source_kind=='imported' and not r.live for r in result)
    assert restored.sources['in-north']=='operator file'
    assert restored.forecast('in-north',NOW+timedelta(hours=2))==[]

def test_end_aligned_optimum_is_not_skipped():
    d=decide(job(duration_minutes=45,data_mode='operational'),rows([100,10,200,200]),NOW)
    assert parse_iso(d.run_at_iso)==NOW+timedelta(minutes=15)
    assert d.optimal_carbon_g==40

def test_learning_uses_unseen_holdout_and_persists(tmp_path):
    data=synthetic_history();path=tmp_path/'model.json'
    model=LearnedForecast(path);report=model.train(data,'synthetic demonstration')
    expected_weights=fit(data[:-48])
    expected=sum(abs(predict(expected_weights,parse_iso(r['timestamp']))-r['intensity']) for r in data[-48:])/48
    assert report['mae_gco2_kwh']==round(expected,3)
    assert report['test_samples']==48 and report['train_samples']==624
    assert parse_iso(report['training_end'])<parse_iso(report['validation_start'])
    assert report['mae_gco2_kwh']<10
    restored=LearnedForecast(path)
    assert restored.status()==report
    assert restored.intensity(NOW)==model.intensity(NOW)

def test_learning_rejects_invalid_history():
    data=synthetic_history();data[1]=data[0]
    with pytest.raises(ValueError):LearnedForecast().train(data,'test')

def test_synthetic_model_cannot_drive_operational_jobs(monkeypatch):
    import app.regions as regions
    model=LearnedForecast();model.train(synthetic_history(),'synthetic demonstration')
    monkeypatch.setattr(regions,'learned',model)
    registry=RegionRegistry()
    with pytest.raises(ValueError,match='restricted'):
        registry.forecast('gb',NOW,'operational','learned')
    assert len(registry.forecast('gb',NOW,'scenario','learned'))==49
    with pytest.raises(ValueError,match='GB national'):
        registry.forecast('in-north',NOW,'scenario','learned')

def test_public_training_excludes_forecasts(monkeypatch):
    import app.learning as learning
    data=synthetic_history()
    class Response:
        def raise_for_status(self):pass
        def json(self):
            return {'data':[{'from':r['timestamp'],'intensity':{'actual':r['intensity'],'forecast':1499}} for r in data]+
                    [{'from':iso(NOW),'intensity':{'actual':None,'forecast':100}}]}
    monkeypatch.setattr(learning.httpx,'get',lambda *a,**k:Response())
    public=LearnedForecast().train_public()
    direct=LearnedForecast().train(data,'test')
    assert public['mae_gco2_kwh']==direct['mae_gco2_kwh']
    assert public['train_samples']==624

def test_restored_provider_cache_is_not_live(tmp_path):
    registry=RegionRegistry(tmp_path/'regions.json')
    registry.ingest('gb-london',rows([100,200]),'provider',imported=False)
    restored=RegionRegistry(registry.path)
    assert all(not r.live and r.source_kind=='cached' for r in restored.forecast('gb-london',NOW))
