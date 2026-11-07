"""Dedicated Fiscycle AI Service; main application ownership stays with dev team."""
from contextlib import asynccontextmanager
from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo
import uuid

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.openapi.utils import get_openapi
from starlette.middleware.cors import CORSMiddleware
from app.core.config import MODEL_REGISTRY, BSF_API_PREFIX
from app.core.http import api_json
from app.core.model_registry import REPORTS
from app.core.security import ServiceBoundary
from app.routers import water_quality, bsf_intelligence, integration, demo_gallery
from app.services.water_quality import WaterQualityService
from app.services.bsf import BsfService
from app.services.bsf_intelligence import BsfIntelligence
from app.services.demo_gallery import DemoGallery

VERSION = '3.0.0-rc2-local'


@asynccontextmanager
async def lifespan(app):
    if MODEL_REGISTRY is None:
        raise RuntimeError('HTTP service requires the model registry; verifier bootstrap bypass is not permitted')
    if os.getenv('FISCYCLE_RUNTIME_ENV','development')=='production' and not (os.getenv('FISCYCLE_AI_SERVICE_TOKEN') or os.getenv('FISCYCLE_GATEWAY_TOKENS')):
        raise RuntimeError('Production requires a service-to-service credential')
    app.state.load_errors = {}
    app.state.water_quality = app.state.bsf = app.state.bsf_intelligence = app.state.demo_gallery = None
    for key, initialize in [('water_quality',WaterQualityService),('bsf',BsfService),
                            ('bsf_intelligence',lambda:BsfIntelligence(b1=app.state.bsf))]:
        try: setattr(app.state,key,initialize())
        except Exception as exc: app.state.load_errors[key] = {'code':'MODEL_LOAD_FAILED','type':type(exc).__name__}
    if app.state.bsf_intelligence is not None:
        try:
            svc = app.state.bsf_intelligence
            app.state.demo_gallery = DemoGallery(svc.models_runtime,svc.history)
        except Exception as exc:
            app.state.load_errors['demo_gallery'] = {'code':'GALLERY_LOAD_FAILED','type':type(exc).__name__}
    for key in REPORTS:
        REPORTS[key]['loaded'] = (app.state.water_quality is not None if key=='water' else
            app.state.bsf is not None if key=='bsf_b1' else app.state.bsf_intelligence is not None)
    yield
    if app.state.water_quality is not None: app.state.water_quality.close()


app = FastAPI(title='Fiscycle AI Service',version=VERSION,lifespan=lifespan,
    description='Dedicated inference/DSS/replay API. Water historical replay; BSF RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Main backend owns users, farms, ponds and product history.')
app.add_middleware(CORSMiddleware,allow_origins=[v for v in os.getenv('FISCYCLE_CORS_ORIGINS','').split(',') if v],
                   allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type','X-Fiscycle-Service-Token'],expose_headers=['X-Request-ID'])


@app.middleware('http')
async def provenance_metadata(request:Request,call_next):
    response = await call_next(request)
    if 200<=response.status_code<300 and 'application/json' in response.headers.get('content-type',''):
        raw = b''.join([chunk async for chunk in response.body_iterator])
        obj = json.loads(raw)
        if isinstance(obj,dict):
            path = request.url.path
            keys = ['water'] if 'water' in path else ['bsf_b1'] if any(s in path for s in ['/forecast','/replay/','/decision-support']) else ['bsf_a1','bsf_a2']
            if path.endswith('/segment'): keys=['bsf_a1']
            if path.endswith('/estimate-weight'): keys=['bsf_a2']
            if '/demo-gallery/' in path and request.app.state.demo_gallery is not None:
                ident=path.split('/demo-gallery/',1)[1].split('/')[0]
                record=request.app.state.demo_gallery.registry.records.get(ident)
                if record and record['track']=='A2': keys=['bsf_a2']
            if path in {'/health','/api/v1/models'}: keys = list(REPORTS)
            obj.setdefault('request_id',getattr(request.state,'request_id',None))
            obj.setdefault('timestamp',datetime.now(ZoneInfo('Asia/Jakarta')).isoformat())
            if request.method == 'POST': obj.setdefault('analysis_id',uuid.uuid4().hex)
            obj.setdefault('runtime_models',{k:REPORTS[k] for k in keys if k in REPORTS})
            obj.setdefault('runtime_metadata_scope','CURRENT_SERVER_AT_RESPONSE')
            obj.setdefault('model_name',keys)
            obj.setdefault('model_version',{k:REPORTS[k]['model_version'] for k in keys if k in REPORTS})
            obj.setdefault('preprocessing_version',{k:REPORTS[k]['preprocessing_version'] for k in keys if k in REPORTS})
            obj.setdefault('model_revision',{k:REPORTS[k]['resolved_revision'] for k in keys if k in REPORTS})
            obj.setdefault('input_source',obj.get('provenance') or obj.get('data_mode') or 'SERVICE_METADATA')
            obj.setdefault('input_provenance',{'source':obj['input_source'],'caller_declared':obj.get('input_verification'),
                                             'historical_not_live': 'water' in path or '/replay/' in path})
            obj.setdefault('warnings',[obj['warning']] if obj.get('warning') else [])
        result = api_json(obj,response.status_code)
        for key,value in response.headers.items():
            if key.lower() not in {'content-length','content-type'}: result.headers[key]=value
        return result
    return response


app.add_middleware(ServiceBoundary)


@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return api_json({'detail':'Data request tidak valid','errors':[{'field':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in exc.errors()],
                     'request_id':getattr(request.state,'request_id',None)},422)


@app.exception_handler(ValueError)
async def value_error(request,exc):
    return api_json({'detail':'Input tidak sesuai kontrak inferensi','request_id':getattr(request.state,'request_id',None)},422)


@app.exception_handler(HTTPException)
async def http_error(request,exc):
    response=api_json({'detail':exc.detail,'request_id':getattr(request.state,'request_id',None)},exc.status_code)
    for key,value in (exc.headers or {}).items():response.headers[key]=value
    return response


@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    return api_json({'detail':'Inferensi gagal; periksa log internal dengan request_id','request_id':getattr(request.state,'request_id',None)},500)


@app.get('/',include_in_schema=False)
def root(): return RedirectResponse('/docs')


@app.get('/health',tags=['System'])
def health(request:Request):
    state = request.app.state
    ready = state.water_quality is not None and state.bsf is not None and state.bsf_intelligence is not None
    return {'service':'fiscycle-ai-service','version':VERSION,'ready':ready,'status':'READY' if ready else 'DEGRADED',
            'services':{'water':state.water_quality is not None,'bsf_b1':state.bsf is not None,'bsf_a1_a2':state.bsf_intelligence is not None,
                        'water_replay':state.water_quality is not None and state.water_quality.replay is not None,
                        'bsf_replay':state.bsf_intelligence is not None and bool(state.bsf_intelligence.trajectories),
                        'curated_gallery':state.demo_gallery is not None},'load_errors':state.load_errors}


@app.get('/api/v1/models',tags=['System'])
def models(): return {'registry_version':MODEL_REGISTRY['release'],'models':REPORTS}


app.include_router(water_quality.router)
# Operational observation CRUD belongs to the main backend; AI debug/history remains.
bsf_intelligence.router.routes=[r for r in bsf_intelligence.router.routes if not r.path.endswith('/observations')]
app.include_router(bsf_intelligence.router)
app.include_router(integration.router)
app.include_router(demo_gallery.router)
# Versioned Water aliases call exactly the same function/schema as legacy routes.
for route in list(app.routes):
    if getattr(route,'path','').startswith('/water-quality/'):
        app.add_api_route(route.path.replace('/water-quality','/api/v1/water',1),route.endpoint,
                         methods=list(route.methods),status_code=route.status_code,tags=['Water v1'])


def openapi_schema():
    if app.openapi_schema: return app.openapi_schema
    schema=get_openapi(title=app.title,version=VERSION,routes=app.routes,description=app.description)
    schema.setdefault('components',{}).setdefault('securitySchemes',{})['ServiceBearer']={'type':'http','scheme':'bearer'}
    schema['components']['securitySchemes']['ServiceHeader']={'type':'apiKey','in':'header','name':'X-Fiscycle-Service-Token',
        'description':'Alternative for private HF Space proxy authentication; keep this secret server-side.'}
    for path,operations in schema['paths'].items():
        for method,operation in operations.items():
            if isinstance(operation,dict) and path not in {'/health'}:
                operation['security']=[{'ServiceBearer':[]},{'ServiceHeader':[]}]
    app.openapi_schema=schema
    return schema


app.openapi=openapi_schema
