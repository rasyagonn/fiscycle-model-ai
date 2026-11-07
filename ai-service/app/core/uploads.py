"""One image interface for raw image bytes and multipart/form-data."""
from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from app.core.config import MAX_BODY_BYTES


async def image_upload(request: Request):
    kind = request.headers.get('content-type','').split(';')[0].lower()
    if kind == 'multipart/form-data':
        async with request.form(max_files=1,max_fields=0,max_part_size=MAX_BODY_BYTES) as form:
            file = form.get('file')
            if not isinstance(file,UploadFile) or len(form) != 1:
                raise HTTPException(400,"Multipart memerlukan satu file pada field 'file'")
            raw = await file.read(MAX_BODY_BYTES+1)
            kind = file.content_type or ''
    else: raw = await request.body()
    if not raw: raise HTTPException(400,"File gambar kosong")
    if len(raw)>8*1024*1024: raise HTTPException(413,"File gambar melebihi 8 MiB")
    if kind not in {'image/jpeg','image/png','image/webp'}:
        raise HTTPException(400,"Tipe gambar harus JPEG, PNG atau WebP")
    return raw, kind
