"""Run actual HTTP smoke checks against a local or deployed Fiscycle AI Service."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--output',default=str(ROOT/'.cache/HTTP_SMOKE.json'))
    parser.add_argument('--water-fixture',default=str(ROOT.parent/'PRIVATE_WATER_REPLAY/water_reference.json'))
    args=parser.parse_args()
    token=os.getenv('FISCYCLE_AI_API_KEY') or os.getenv('FISCYCLE_AI_SERVICE_TOKEN')
    headers={'Authorization':'Bearer '+token} if token else {}
    space_token=os.getenv('FISCYCLE_HF_SPACE_TOKEN')
    if space_token and token:
        headers={'Authorization':'Bearer '+space_token,'X-Fiscycle-Service-Token':token}
    results=[]
    def check(label,ok):
        results.append({'check':label,'status':'PASS' if ok else 'FAIL'})
        if not ok:raise AssertionError(label)
        print('PASS',label,flush=True)
    with httpx.Client(base_url=args.base_url.rstrip('/'),headers=headers,timeout=120) as c:
        r=c.get('/health');health=r.json()
        check('actual HTTP startup /health',r.status_code==200 and health['ready'])
        check('/docs',c.get('/docs').status_code==200)
        check('all four models loaded',all(v['loaded'] and v['artifacts_verified'] for v in c.get('/api/v1/models').json()['models'].values()))
        golden=json.loads((ROOT/'tests/fixtures/golden_reference.json').read_text())
        meta=json.loads((ROOT/'tests/fixtures/fixture_metadata.json').read_text())
        raw=(ROOT/'tests/fixtures/a1_development_train.jpg').read_bytes()
        r=c.post('/api/v1/bsf/segment',files={'file':('development.jpg',raw,'image/jpeg')})
        check('A1 real image',r.status_code==200 and r.json()['visible_instance_count']==golden['a1_visible_instance_count'])
        r=c.post('/api/v1/bsf/analyze-photo',content=raw,headers={'Content-Type':'image/jpeg'})
        check('A1 to A2 photo and DSS',r.status_code==200 and r.json()['summary']['analyzed']>0 and r.json()['decision_support']['status']=='ABSTAIN_OPERATIONAL')
        raw2=(ROOT/'tests/fixtures/a2_development_train.jpg').read_bytes()
        params=dict(zip(['x0','y0','x1','y1'],meta['a2']['roi_bbox']));params['reviewed_roi']='true'
        r=c.post('/api/v1/bsf/estimate-weight',params=params,files={'file':('development.jpg',raw2,'image/jpeg')})
        check('A2 exact v3 inference',r.status_code==200 and math.isclose(r.json()['predicted_measured_weight_mg'],golden['a2_predicted_measured_weight_mg'],abs_tol=1e-4))
        r=c.post('/api/v1/bsf/forecast',json={**golden['b1_features'],'input_provenance':'SYNTHETIC_SCENARIO'})
        check('B1 real estimator',r.status_code==200 and math.isclose(r.json()['predicted_next_weight_mg'],golden['b1_predicted_next_weight_mg'],abs_tol=1e-8))
        trajectories=c.get('/api/v1/bsf/replay/trajectories').json()['trajectories']
        check('B1 development replay',len(trajectories)==16)
        ident=trajectories[0]['trajectory_id']
        r=c.get(f'/api/v1/bsf/replay/{ident}?revealed=6')
        check('B1 replay inference',r.status_code==200 and r.json()['forecast']['result']['predicted_next_weight_mg'] is not None)
        r=c.post('/api/v1/bsf/decision-support',json={'data_mode':'HISTORICAL_RESEARCH','trajectory_id':ident,'revealed':6})
        check('BSF DSS',r.status_code==200 and bool(r.json()['triggered_rule_ids']))
        water_fixture=Path(args.water_fixture)
        if water_fixture.is_file():
            ref=json.loads(water_fixture.read_text())
            r=c.post('/api/v1/water/analyze',json=ref['input'])
            check('Water nine numeric predictions',r.status_code==200 and all(math.isclose(f['value'],ref['expected_forecasts'][p][h]['value'],abs_tol=1e-8) for p,hs in r.json()['forecasts'].items() for h,f in hs.items()))
            history_id=r.json()['history_id']
            r=c.post('/api/v1/water/scenario',json={'history_id':history_id,'input_state':'STALE'})
            check('Water rule-only DSS scenario',r.status_code==200 and r.json()['provenance']=='SIMULATED_RULE_ONLY' and not r.json()['ml_recomputed'])
        else:results.append({'check':'Water numeric forecasts','status':'SKIPPED','reason':'Approved private fixture not supplied'})
        periods=c.get('/api/v1/water/replay/periods')
        if periods.status_code==200:
            period=periods.json()['periods'][0]
            made=c.post('/api/v1/water/replay/sessions',json={k:period[k] for k in ['start','end','pond_id']})
            check('Water replay session',made.status_code==201)
            r=c.post('/api/v1/water/replay/sessions/'+made.json()['session_id']+'/advance?steps=55')
            check('Water paired replay metrics',r.status_code==200 and len(r.json()['metrics']['rows'])==9 and all(e['matched']>0 for e in r.json()['metrics']['rows']))
        else:results.append({'check':'Water replay','status':'SKIPPED','reason':'Private replay not mounted'})
        gallery=c.get('/api/v1/bsf/demo-gallery').json()
        check('curated gallery 16 selected only',gallery['total']==16)
        for track in ['A1','A2']:
            row=next(x for x in gallery['items'] if x['track']==track)
            r=c.get(row['content_url'])
            check(track+' original photo bytes',r.status_code==200 and hashlib.sha256(r.content).hexdigest()==row['sha256'])
            r=c.post('/api/v1/bsf/demo-gallery/'+row['id']+'/analyze')
            check(track+' curated inference',r.status_code==200 and r.json()['inference_status'] in {'SUCCESS','PARTIAL','REJECTED'})
        check('invalid bytes rejected',c.post('/api/v1/bsf/segment',content=b'bad',headers={'Content-Type':'image/jpeg'}).status_code==422)
        check('schema violation rejected',c.post('/api/v1/water/analyze',json={}).status_code==422)
        if token:
            with httpx.Client(base_url=args.base_url,timeout=20) as anonymous:
                base_auth={'Authorization':'Bearer '+space_token} if space_token else {}
                check('missing service token rejected',anonymous.get('/api/v1/models',headers=base_auth).status_code==401)
                wrong={**base_auth,'X-Fiscycle-Service-Token':'wrong'} if space_token else {'Authorization':'Bearer wrong'}
                check('wrong service token rejected',anonymous.get('/api/v1/models',headers=wrong).status_code==401)
    report={'status':'PASS' if all(r['status']=='PASS' for r in results) else 'PARTIAL',
            'timestamp':datetime.now(timezone.utc).isoformat(),'base_url':args.base_url,'checks':results,
            'scope':'ACTUAL_HTTP_NOT_TESTCLIENT','model_source':next(iter(health['runtime_models'].values()))['model_source']}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],len(results),'HTTP checks',flush=True)


if __name__=='__main__': main()
