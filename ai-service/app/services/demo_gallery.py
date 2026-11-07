"""Small approved gallery, independent from the full research dataset/archive."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock

from fastapi import HTTPException
from app.core.config import DEMO_GALLERY_PATH
from app.core.model_registry import REPORTS, digest, safe_relative
from app.core.security import tenant_context
from app.services.gallery_inference import GalleryInference


class CuratedRegistry:
    def __init__(self, root=DEMO_GALLERY_PATH):
        self.root = Path(root).resolve()
        path = self.root/"competition_gallery_selection.json"
        self.manifest = json.loads(path.read_text(encoding="utf-8"))
        if self.manifest.get('status') != 'DEMO_APPROVED':
            raise ValueError("Demo gallery selection has not been authorized")
        self.records = {r['id']:r for r in self.manifest['images']}
        if len(self.records) != len(self.manifest['images']):
            raise ValueError("Duplicate gallery IDs")
        for r in self.records.values():
            if r.get('classification') != 'DEMO_APPROVED': raise ValueError("Unapproved demo photo")
            self.path(r['id'])
            self.path(r['id'], thumbnail=True)

    def get(self, ident):
        if ident not in self.records: raise HTTPException(404,"Foto tidak ada di galeri demo terpilih")
        return self.records[ident]

    def path(self, ident, thumbnail=False):
        row = self.get(ident)
        name = row['thumbnail'] if thumbnail else row['file']
        safe_relative(name)
        path = (self.root/name).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise HTTPException(503,"Aset galeri tidak tersedia")
        expected = row['thumbnail_sha256'] if thumbnail else row['sha256']
        if digest(path) != expected: raise HTTPException(503,"Checksum galeri tidak sesuai")
        return path

    def raw(self, ident, evaluation=False):
        return self.path(ident).read_bytes()

    def public_record(self, row):
        fields = ['id','sample_id','track','dataset_id','split','split_group_id','width','height','sha256',
                  'source','license','classification','selection_method','selection_seed','weight_protocol']
        return {**{k:row.get(k) for k in fields},'input_source':'CURATED_PUBLIC_RESEARCH_IMAGE',
                'scope':'RELEASED_FINAL_TEST_NOT_BLIND','content_url':f"/api/v1/bsf/demo-gallery/{row['id']}/content",
                'thumbnail_url':f"/api/v1/bsf/demo-gallery/{row['id']}/content?thumbnail=true"}


class DemoGallery(GalleryInference):
    def __init__(self, runtime, history):
        self.registry = CuratedRegistry()
        self.runtime, self.history, self.evaluation = runtime, history, False
        self.cache = {}
        self.lock = Lock()

    def analyze(self, ident):
        row = self.registry.get(ident)
        # Include caller scope and exact model revisions; never reuse across versions.
        stamp = {'image':row['sha256'],'models':REPORTS,'scope':tenant_context.get()}
        fingerprint = hashlib.sha256(json.dumps(stamp,sort_keys=True).encode()).hexdigest()
        key = ident+':'+fingerprint
        with self.lock:
            if key in self.cache:
                return {**copy.deepcopy(self.cache[key]),'cache_hit':True,'cache_key':fingerprint}
            value = self._compute(row, review=None)
            value.update(input_source='CURATED_PUBLIC_RESEARCH_IMAGE',gallery_selection_method=row['selection_method'],
                         calculated_at=datetime.now(timezone.utc).isoformat(),model_fingerprint=fingerprint)
            value['history_id'] = self.history.add('CURATED_DEMO_ANALYSIS',value['provenance'],value,
                model_version=value.get('model_version'),preprocessing_version=value.get('preprocessing_version'),image_sha256=row['sha256'])
            self.cache[key] = copy.deepcopy(value)
            return {**value,'cache_hit':False,'cache_key':fingerprint}
