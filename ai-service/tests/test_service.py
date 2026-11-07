"""Real HF/local runtime integration; development fixtures and approved gallery.

Water replay/golden checks require the explicitly mounted private fixture/seed.
"""
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.cache'
CACHE.mkdir(exist_ok=True)
STATE = tempfile.TemporaryDirectory(prefix='api_test_',dir=CACHE)
os.environ.setdefault('FISCYCLE_MODEL_SOURCE','local')
os.environ.setdefault('FISCYCLE_HF_OFFLINE','1')
os.environ.setdefault('FISCYCLE_DATABASE_PATH',str(Path(STATE.name)/'bsf.sqlite3'))
if (ROOT/'.local_data/replay/water/water_replay_v1.csv').exists():
    os.environ.setdefault('FISCYCLE_WATER_REPLAY_CSV',str(ROOT/'.local_data/replay/water/water_replay_v1.csv'))
from app.main import app
from app.core.model_registry import REPORTS, resolve_bundle, validate_hf_entry
from app.services.bsf_models import fixed_canvas, a2_tensor


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope='module')
def golden():
    return json.loads((ROOT/'tests/fixtures/golden_reference.json').read_text())


def test_startup_docs_registry(client):
    health=client.get('/health')
    assert health.status_code==200 and health.json()['ready'],health.json()
    assert health.headers['x-request-id']==health.json()['request_id']
    assert client.get('/docs').status_code==200
    models=client.get('/api/v1/models').json()['models']
    assert len(models)==4 and all(m['artifacts_verified'] for m in models.values())
    if os.getenv('FISCYCLE_MODEL_SOURCE')=='huggingface':
        assert all(m['requested_revision']==m['resolved_revision'] for m in models.values())
        assert all(m['cache_behavior']=='HF_CACHE_OFFLINE' for m in models.values())
    schema=client.get('/openapi.json').json()
    assert 'ServiceBearer' in schema['components']['securitySchemes']
    required=['/api/v1/water/analyze','/api/v1/water/replay/periods','/api/v1/water/scenario',
              '/api/v1/water/rules','/api/v1/bsf/segment','/api/v1/bsf/estimate-weight',
              '/api/v1/bsf/analyze-photo','/api/v1/bsf/forecast','/api/v1/bsf/demo-gallery']
    assert all(p in schema['paths'] for p in required)


def test_a1_raw_and_multipart_real(client,golden):
    raw=(ROOT/'tests/fixtures/a1_development_train.jpg').read_bytes()
    a=client.post('/api/v1/bsf/segment',content=raw,headers={'Content-Type':'image/jpeg'})
    b=client.post('/api/v1/bsf/segment',files={'file':('a.jpg',raw,'image/jpeg')})
    assert a.status_code==b.status_code==200,(a.text,b.text)
    assert a.json()['visible_instance_count']==b.json()['visible_instance_count']==golden['a1_visible_instance_count']
    assert a.json()['instances']==b.json()['instances']
    assert 'NOT_FIELD_VALIDATED' in a.json()['status']
    assert a.json()['model_revision']['bsf_a1']==REPORTS['bsf_a1']['resolved_revision']


def test_a2_exact_preprocessing_and_real_prediction(client,golden):
    meta=json.loads((ROOT/'tests/fixtures/fixture_metadata.json').read_text())
    raw=(ROOT/'tests/fixtures/a2_development_train.jpg').read_bytes()
    roi=meta['a2']['roi_bbox']
    with Image.open(io.BytesIO(raw)) as image:
        prepared,geometry=fixed_canvas(image,roi,2048)
    assert hashlib.sha256(prepared.tobytes()).hexdigest()==golden['a2_prepared_sha256']
    assert hashlib.sha256(a2_tensor(prepared,224).numpy().tobytes()).hexdigest()==golden['a2_tensor_sha256']
    params=dict(zip(['x0','y0','x1','y1'],roi));params['reviewed_roi']='true'
    response=client.post('/api/v1/bsf/estimate-weight',params=params,files={'file':('a.jpg',raw,'image/jpeg')})
    assert response.status_code==200,response.text
    assert math.isclose(response.json()['predicted_measured_weight_mg'],golden['a2_predicted_measured_weight_mg'],abs_tol=1e-4)
    params['reviewed_roi']='false'
    assert client.post('/api/v1/bsf/estimate-weight',params=params,content=raw,headers={'Content-Type':'image/jpeg'}).status_code==422


def test_a1_a2_pipeline_photo_dss(client):
    raw=(ROOT/'tests/fixtures/a1_development_train.jpg').read_bytes()
    response=client.post('/api/v1/bsf/analyze-photo',files={'file':('a.jpg',raw,'image/jpeg')})
    assert response.status_code==200,response.text
    result=response.json(); summary=result['summary']
    assert summary['analyzed']>0 and summary['detected']==summary['analyzed']+summary['rejected']
    assert math.isclose(sum(r['predicted_weight_mg'] for r in result['instances'] if r['predicted_weight_mg'] is not None),summary['analyzed_visible_mass_mg'])
    assert all(i['geometry']['scale_factor']==224/2048 for i in result['instances'] if i['geometry'])
    assert result['decision_support']['status']=='ABSTAIN_OPERATIONAL'
    assert result['b1_link']=='NOT_USED_NOT_SCIENTIFICALLY_VALIDATED'


def test_b1_prediction_replay_and_dss(client,golden):
    response=client.post('/api/v1/bsf/forecast',json={**golden['b1_features'],'input_provenance':'SYNTHETIC_SCENARIO'})
    assert response.status_code==200,response.text
    assert math.isclose(response.json()['predicted_next_weight_mg'],golden['b1_predicted_next_weight_mg'],abs_tol=1e-8)
    trajectories=client.get('/api/v1/bsf/replay/trajectories').json()['trajectories']
    assert len(trajectories)==16 and all(not r['trajectory_id'].endswith('-5') for r in trajectories)
    ident=trajectories[0]['trajectory_id']
    replay=client.get(f'/api/v1/bsf/replay/{ident}?revealed=6').json()
    assert replay['evaluation_scope']=='IN_SAMPLE_DEVELOPMENT_REPLAY'
    assert replay['forecast']['result']['predicted_next_weight_mg'] is not None
    assert all(c['error_mg'] is None for c in replay['comparisons'] if not c['time_aligned'])
    dss=client.post('/api/v1/bsf/decision-support',json={'data_mode':'HISTORICAL_RESEARCH','trajectory_id':ident,'revealed':6})
    assert dss.status_code==200 and dss.json()['triggered_rule_ids']


def test_water_golden_and_dss(client):
    seed=Path(os.getenv('FISCYCLE_WATER_REPLAY_CSV',ROOT.parent/'PRIVATE_WATER_REPLAY/water_replay_v1.csv'))
    path=seed.with_name('water_reference.json')
    if not path.exists():pytest.skip('Private Water fixture is mounted separately')
    ref=json.loads(path.read_text())
    response=client.post('/api/v1/water/analyze',json=ref['input'])
    assert response.status_code==200,response.text
    result=response.json()
    assert all(math.isclose(f['value'],ref['expected_forecasts'][p][h]['value'],abs_tol=1e-8) for p,hs in result['forecasts'].items() for h,f in hs.items())
    assert len(result['decision_support']['traces'])==6
    assert result['runtime_models']['water']['model_source']==os.getenv('FISCYCLE_MODEL_SOURCE')
    scenario=client.post('/api/v1/water/scenario',json={'history_id':result['history_id'],'input_state':'STALE'})
    assert scenario.status_code==200
    assert scenario.json()['provenance']=='SIMULATED_RULE_ONLY' and not scenario.json()['ml_recomputed']
    assert scenario.json()['after']['data_quality']['status']=='STALE'
    assert client.get('/api/v1/water/rules').json()['expert_reviewed_biological_thresholds']==[]


def test_water_replay_paired_metrics(client):
    response=client.get('/api/v1/water/replay/periods')
    if response.status_code==503:pytest.skip('Private Water replay mount unavailable')
    period=response.json()['periods'][0]
    made=client.post('/api/v1/water/replay/sessions',json={k:period[k] for k in ['start','end','pond_id']})
    assert made.status_code==201,made.text
    ident=made.json()['session_id']
    stepped=client.post(f'/api/v1/water/replay/sessions/{ident}/advance?steps=55')
    assert stepped.status_code==200,stepped.text
    state=stepped.json()
    assert len(state['metrics']['rows'])==9
    assert all(r['matched']>0 and r['persistence_same_pairs']['mae'] is not None for r in state['metrics']['rows'])
    assert client.get(f'/api/v1/water/replay/sessions/{ident}').status_code==200


def test_all_16_curated_images_real_inference_cache(client):
    listed=client.get('/api/v1/bsf/demo-gallery').json()
    assert listed['total']==16 and not listed['full_research_gallery_required']
    rows=listed['items']
    assert sum(r['track']=='A1' for r in rows)==sum(r['track']=='A2' for r in rows)==8
    outcomes=[]
    for row in rows:
        content=client.get(row['content_url'])
        assert content.status_code==200 and hashlib.sha256(content.content).hexdigest()==row['sha256']
        response=client.post(f"/api/v1/bsf/demo-gallery/{row['id']}/analyze")
        assert response.status_code==200,response.text
        result=response.json()
        assert result['image_id']==row['id'] and result['inference_status'] in {'SUCCESS','PARTIAL','REJECTED'}
        assert 'NOT_FIELD_VALIDATED' in result['status'] and not result['cache_hit']
        second=client.post(f"/api/v1/bsf/demo-gallery/{row['id']}/analyze").json()
        assert second['cache_hit'] and second['cache_key']==result['cache_key']
        assert second['inference_status']==result['inference_status']
        outcomes.append({k:result.get(k) for k in ['image_id','sample_id','inference_status','predicted_weight_mg','rejection_reason']})
    (CACHE/'CURATED_INFERENCE_TEST.json').write_text(json.dumps(outcomes,indent=2)+'\n')


@pytest.mark.parametrize('path,payload,headers,status',[
    ('/api/v1/bsf/segment',b'bad',{'Content-Type':'image/jpeg'},422),
    ('/api/v1/bsf/segment',b'',{'Content-Type':'image/jpeg'},400),
    ('/api/v1/bsf/segment',b'text',{'Content-Type':'text/plain'},400),
    ('/api/v1/bsf/forecast',{},None,422),
    ('/api/v1/water/analyze',{},None,422),
])
def test_invalid_inputs(client,path,payload,headers,status):
    response=client.post(path,content=payload,headers=headers) if headers else client.post(path,json=payload)
    assert response.status_code==status,response.text


def test_nonselected_id_and_filesystem_rejected(client):
    assert client.get('/api/v1/bsf/demo-gallery/not-a-photo').status_code==404
    assert client.post('/api/v1/bsf/demo-gallery/not-a-photo/analyze').status_code==404
    assert client.get('/api/v1/bsf/replay/45-5').status_code==404


def test_service_authentication_boundary(monkeypatch):
    from app.core.security import ServiceBoundary
    monkeypatch.setenv('FISCYCLE_AI_SERVICE_TOKEN','test-only-not-a-real-secret')
    small=FastAPI()
    @small.get('/private')
    def private():return {'ok':True}
    @small.get('/health')
    def health():return {'ok':True}
    small.add_middleware(ServiceBoundary)
    with TestClient(small) as c:
        assert c.get('/health').status_code==200
        assert c.get('/private').status_code==401
        assert c.get('/private',headers={'Authorization':'Bearer wrong'}).status_code==401
        r=c.get('/private',headers={'Authorization':'Bearer test-only-not-a-real-secret'})
        assert r.status_code==200 and r.headers['x-request-id']
        assert c.get('/private',headers={'Authorization':'Bearer hf-proxy-example','X-Fiscycle-Service-Token':'test-only-not-a-real-secret'}).status_code==200


def test_immutable_revision_and_tamper_rejection():
    for revision in ['main','v1',None]:
        with pytest.raises(ValueError):validate_hf_entry({'repo_id':'a/b','revision':revision})
    with tempfile.TemporaryDirectory(prefix='tamper_',dir=CACHE) as folder:
        file=Path(folder)/'sample.json';file.write_text('original')
        expected=hashlib.sha256(file.read_bytes()).hexdigest()
        entry={'local_dir':folder,'files':{'sample.json':expected}}
        resolve_bundle(entry,'local')
        file.write_text('changed')
        with pytest.raises(ValueError):resolve_bundle(entry,'local')


def test_failed_bundle_cannot_load_stale_runtime_copy(monkeypatch):
    from app.core.artifacts import verify_domain
    original=copy.deepcopy(REPORTS['water'])
    monkeypatch.setitem(REPORTS,'water',{**original,'artifacts_verified':False})
    with pytest.raises(ValueError):verify_domain('water')
    # A failed Water bundle does not disable independently verified BSF artifacts.
    assert verify_domain('bsf')


def test_history_keeps_calculation_revision_after_registry_changes(client,monkeypatch):
    raw=(ROOT/'tests/fixtures/a1_development_train.jpg').read_bytes()
    result=client.post('/api/v1/bsf/segment',content=raw,headers={'Content-Type':'image/jpeg'}).json()
    ident=result['history_id'];old_revision=REPORTS['bsf_a1']['resolved_revision']
    monkeypatch.setitem(REPORTS,'bsf_a1',{**REPORTS['bsf_a1'],'resolved_revision':'f'*40})
    saved=client.get(f'/api/v1/bsf/history/{ident}').json()
    assert saved['result']['calculation_model_trace']['bsf_a1']['resolved_revision']==old_revision
    assert saved['runtime_models']['bsf_a1']['resolved_revision']=='f'*40
