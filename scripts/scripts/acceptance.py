"""Run against a fresh isolated server: python scripts/acceptance.py [base URL]."""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta

BASE = sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8001'
def request(path, body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(BASE+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)

state=request('/api/state')
assert not state['jobs'], 'Use a fresh isolated server; this test does not clear your jobs'
print('Initial sources:', [(r['id'],r['available'],r['source']) for r in state['regions']],flush=True)
model=request('/api/model/train',{'dataset':'synthetic_demo'})
assert model['trained'] and model['test_samples']==48
print('Synthetic validation:',json.dumps(model),flush=True)
result=request('/api/demo/scenario',{})
decisions=[j['decision']['action'] for j in result['seeded']]
assert decisions==['RUN','WAIT','SHIFT'],decisions
print('Decisions:',decisions,flush=True)
started=time.monotonic()
while time.monotonic()-started<90:
    state=request('/api/state')
    if all(j['status']=='DONE' for j in state['jobs']):break
    assert not any(j['status'] in ('MISSED','FAILED') for j in state['jobs']),state['jobs']
    time.sleep(.5)
else:raise AssertionError('Jobs did not complete within 90 seconds')
for job in state['jobs']:
    proof=request('/api/jobs/'+job['id']+'/artifact')
    assert proof['independently_verified'] is True,proof
    assert job['execution_plan']['execution']=='local CPU demo'
    assert job['execution_plan']['data_mode']=='scenario'
    artifact=proof['artifact']
    assert artifact['baseline_plan']['forecast']
    plan=artifact['execution_plan']
    start=datetime.fromisoformat(plan['dispatched_at'].replace('Z','+00:00'))
    end=start+timedelta(minutes=plan['duration_minutes'])
    recomputed=0
    for row in plan['forecast']:
        slot=datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
        minutes=max(0,(min(end,slot+timedelta(minutes=30))-max(start,slot)).total_seconds()/60)
        recomputed+=row['intensity_gco2_kwh']*plan['energy_kwh']*minutes/plan['duration_minutes']
    assert abs(recomputed-plan['estimated_carbon_g'])<.01
print('All three CPU jobs completed and all three receipts independently verified.',flush=True)
print('Estimated scenario totals:',json.dumps(state['totals']),flush=True)
assert state['totals']['jobs_completed']==3
assert state['totals']['carbon_saved_g']>0
print('PASS: self-contained scenario acceptance')
