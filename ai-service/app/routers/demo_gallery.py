from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from app.core.config import BSF_API_PREFIX

router = APIRouter(prefix=BSF_API_PREFIX+'/demo-gallery', tags=['Curated Demo Gallery'])


def service(request):
    value = request.app.state.demo_gallery
    if value is None: raise HTTPException(503,'Galeri demo belum siap')
    return value


@router.get('')
def images(request:Request, track:str|None=Query(default=None,pattern='^(A1|A2)$')):
    gallery = service(request)
    records = [gallery.registry.public_record(r) for r in gallery.registry.records.values() if track is None or r['track']==track]
    return {'status':'DEMO_APPROVED','items':records,'total':len(records),
            'full_research_gallery_required':False,'selection':gallery.registry.manifest['approval_basis']}


@router.get('/{image_id}')
def image(image_id:str,request:Request):
    registry = service(request).registry
    return registry.public_record(registry.get(image_id))


@router.get('/{image_id}/content')
def content(image_id:str,request:Request,thumbnail:bool=False):
    registry = service(request).registry
    return FileResponse(registry.path(image_id,thumbnail),media_type='image/jpeg',headers={'X-Data-Provenance':'CURATED_PUBLIC_RESEARCH_IMAGE'})


@router.post('/{image_id}/analyze')
async def analyze(image_id:str,request:Request):
    return await run_in_threadpool(service(request).analyze,image_id)
