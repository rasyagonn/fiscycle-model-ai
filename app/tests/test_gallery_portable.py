"""Run from source or an extracted service: pytest app/tests/test_gallery_portable.py."""
from fastapi.testclient import TestClient
from app.main import app
from app.gallery_checks import run_gallery_checks
from app.services.bsf_gallery import GalleryService
from app.services.bsf_intelligence import BsfHistory


def test_released_gallery_runtime(tmp_path):
    with TestClient(app) as client:
        runtime=client.app.state.bsf_intelligence.models_runtime
        gallery=GalleryService(runtime,BsfHistory(tmp_path/"history.sqlite3"),db_path=tmp_path/"gallery.sqlite3")
        original=client.app.state.bsf_gallery;client.app.state.bsf_gallery=gallery
        try:
            def check(label,condition): assert condition,label
            run_gallery_checks(client,check)
        finally:
            gallery.close();client.app.state.bsf_gallery=original
