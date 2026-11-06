"""Tenant-aware BSF gallery HTTP adapter; clients provide opaque IDs, never file paths."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from app.core.config import BSF_API_PREFIX
from app.services.bsf_gallery import GalleryService

router=APIRouter(prefix=BSF_API_PREFIX+"/gallery",tags=["Galeri Pengujian BSF"])


def service(request:Request)->GalleryService:
    value=getattr(request.app.state,"bsf_gallery",None)
    if value is None: raise HTTPException(503,"Galeri belum tersedia; periksa inventaris dataset dan status BSF")
    return value


class RoiReview(BaseModel):
    model_config=ConfigDict(extra="forbid")
    roi_bbox:list[int]=Field(min_length=4,max_length=4)
    whole_larva_visible:bool
    no_written_markings:bool
    reviewer:str=Field(min_length=1,max_length=100)

    @model_validator(mode="after")
    def valid(self):
        if not self.whole_larva_visible or not self.no_written_markings:
            raise ValueError("ROI perlu mencakup larva utuh tanpa penanda yang dapat dibaca")
        return self


class AnalyzeInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    force:bool=False
    review:RoiReview|None=None


class JobInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    dataset_id:str=Field(min_length=1,max_length=50)
    image_ids:list[str]|None=Field(default=None,max_length=500)
    force:bool=False


@router.get("/datasets")
def datasets(request:Request): return service(request).datasets()


@router.get("/datasets/{dataset_id}/metrics")
def metrics(dataset_id:str,request:Request): return service(request).metrics(dataset_id)


@router.get("/images")
def images(request:Request,dataset_id:str|None=None,q:str=Query(default="",max_length=160),
           status:Literal["NOT_ANALYZED","SUCCESS","PARTIAL","FAILED","REJECTED"]|None=None,
           page:int=Query(default=1,ge=1),page_size:int=Query(default=20,ge=1,le=60)):
    return service(request).images(dataset_id,q,status,page,page_size)


@router.get("/images/{image_id}")
def image(image_id:str,request:Request):
    svc=service(request)
    return svc.public_record(svc.registry.get(image_id))


@router.get("/images/{image_id}/content")
def content(image_id:str,request:Request,variant:Literal["original","thumbnail","overlay","processed"]="original",cache_key:str|None=None):
    svc=service(request)
    if variant=="processed":
        from app.services.bsf_models import fixed_canvas
        from app.services.bsf_intelligence import decode_image
        import io
        result=svc.result(image_id,cache_key)
        if not result.get("roi_bbox"): raise HTTPException(409,"ROI belum tersedia")
        image=decode_image(svc.registry.raw(image_id),"image/jpeg",require_unrotated=True)
        prepared,_=fixed_canvas(image,result["roi_bbox"],2048)
        stream=io.BytesIO();prepared.save(stream,format="PNG")
        raw=stream.getvalue()
    elif variant=="overlay": raw=svc.overlay(image_id,cache_key)
    else: raw=svc.registry.content(image_id,variant=="thumbnail")
    return Response(raw,media_type="image/png" if variant in {"overlay","processed"} else "image/jpeg",headers={"Cache-Control":"private, no-store","X-Data-Provenance":"PUBLIC_RESEARCH_"+svc.registry.get(image_id)["split"]})


@router.post("/images/{image_id}/analyze")
async def analyze(image_id:str,request:Request,payload:AnalyzeInput=AnalyzeInput()):
    return await run_in_threadpool(service(request).analyze,image_id,review=payload.review.model_dump() if payload.review else None,force=payload.force)


@router.get("/images/{image_id}/results")
def results(image_id:str,request:Request,cache_key:str|None=None): return service(request).result(image_id,cache_key)


@router.post("/jobs",status_code=202)
def create_job(payload:JobInput,request:Request):
    return service(request).create_job(payload.dataset_id,image_ids=payload.image_ids,force=payload.force)


@router.get("/jobs")
def jobs(request:Request): return {"jobs":service(request).jobs()}


@router.get("/jobs/{job_id}")
def job(job_id:str,request:Request): return service(request).job(job_id)


@router.post("/jobs/{job_id}/resume",status_code=202)
def resume(job_id:str,request:Request,retry_failed:bool=False): return service(request).resume(job_id,retry_failed)
