from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse

from app.core.config import BSF_API_PREFIX, DASHBOARD_PATH, MAX_BODY_BYTES, WATER_QUALITY_ROOT
from app.core.http import api_json
from app.routers import bsf, bsf_intelligence, health, integration, bsf_gallery
from app.services.bsf import BsfService
from app.services.bsf_intelligence import BsfIntelligence
from app.core.security import GatewayBoundary
from starlette.middleware.cors import CORSMiddleware

if WATER_QUALITY_ROOT.is_dir():
    from app.routers import water_quality
    from app.services.water_quality import WaterQualityService
else:
    water_quality = None
    WaterQualityService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("FISCYCLE_RUNTIME_ENV", "development").lower() == "production" and not os.getenv("FISCYCLE_GATEWAY_TOKENS"):
        raise RuntimeError("Production use requires authenticated tenant isolation and privacy review")
    app.state.water_quality = None
    app.state.bsf = None
    app.state.bsf_intelligence = None
    app.state.bsf_gallery = None
    app.state.load_errors = {"water_quality": None, "bsf": None, "bsf_intelligence": None}

    if WaterQualityService is not None:
        try:
            app.state.water_quality = WaterQualityService()
        except Exception as exc:
            app.state.load_errors["water_quality"] = f"{type(exc).__name__}: inisialisasi gagal"

    try:
        app.state.bsf = BsfService()
    except Exception as exc:
        app.state.load_errors["bsf"] = f"{type(exc).__name__}: inisialisasi gagal"

    try:
        app.state.bsf_intelligence = BsfIntelligence(b1=app.state.bsf)
    except Exception as exc:
        app.state.load_errors["bsf_intelligence"] = f"{type(exc).__name__}: inisialisasi gagal"

    if app.state.bsf_intelligence is not None:
        try:
            from app.services.bsf_gallery import GalleryService
            app.state.bsf_gallery = GalleryService(app.state.bsf_intelligence.models_runtime,app.state.bsf_intelligence.history)
        except Exception as exc:
            app.state.load_errors["bsf_gallery"] = f"{type(exc).__name__}: inventaris galeri belum siap"

    yield

    if app.state.bsf_gallery is not None:
        app.state.bsf_gallery.close()

    if app.state.water_quality is not None:
        app.state.water_quality.close()


app = FastAPI(
    title="Fiscycle Model API",
    description=(
        "Satu API untuk kapabilitas model Fiscycle. Water Quality menggunakan replay historis; "
        "BSF tetap prototipe riset dan belum tervalidasi di lapangan."
    ),
    version="2.1.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=[s for s in os.getenv("FISCYCLE_CORS_ORIGINS", "").split(",") if s], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"], expose_headers=["X-Request-ID"])
app.add_middleware(GatewayBoundary)


@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > MAX_BODY_BYTES
            except ValueError:
                return api_json({"detail": "Header Content-Length tidak valid"}, 400)
            if too_large:
                return api_json({"detail": f"Request terlalu besar; batas {MAX_BODY_BYTES // 1024} KiB"}, 413)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(value) for value in error["loc"] if value != "body"),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return api_json({"detail": "Data request tidak valid", "errors": errors}, 422)


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    translations = {
        "Future observation rejected": "Pembacaan masa depan tidak diterima.",
        "Mixed pond history rejected": "Satu request tidak boleh mencampur pond_id.",
        "Only historical_replay is approved in v2": "Mode yang didukung hanya historical_replay.",
    }
    return api_json({"detail": translations.get(str(exc), "Input tidak sesuai kontrak inferensi.")}, 422)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    page = DASHBOARD_PATH if WATER_QUALITY_ROOT.is_dir() else DASHBOARD_PATH.parent / "bsf.html"
    if not page.is_file():
        raise HTTPException(503, "Dashboard belum tersedia")
    return HTMLResponse(_page_html(page))


def _page_html(page):
    content = page.read_text(encoding="utf-8")
    if page.name == "bsf.html":
        content = content.replace("__BSF_GALLERY__", (DASHBOARD_PATH.parent / "gallery.html").read_text(encoding="utf-8"))
        content = content.replace("__BSF_API_PREFIX__", BSF_API_PREFIX)
        if not WATER_QUALITY_ROOT.is_dir():
            content = content.replace('<a href="/">Kualitas Air</a>', "")
    return content


app.include_router(health.router)
if water_quality is not None:
    app.include_router(water_quality.router)
app.include_router(bsf.router)
app.include_router(bsf_intelligence.router)
app.include_router(integration.router)
app.include_router(bsf_gallery.router)


@app.get("/ecosystem", response_class=HTMLResponse, include_in_schema=False)
def ecosystem_dashboard():
    return HTMLResponse(_page_html(DASHBOARD_PATH.parent / "ecosystem.html").replace("__BSF_API_PREFIX__", BSF_API_PREFIX))


@app.get("/assets/{name}", include_in_schema=False)
def shared_assets(name: str):
    if name not in {"integration.js", "integration.css", "gateway.js", "gallery.js", "gallery.css"}:
        raise HTTPException(404,"Asset tidak ditemukan")
    return FileResponse(DASHBOARD_PATH.parent / name)


@app.get("/bsf-intelligence", response_class=HTMLResponse, include_in_schema=False)
def bsf_dashboard():
    page = DASHBOARD_PATH.parent / "bsf.html"
    if not page.is_file():
        raise HTTPException(503, "Halaman BSF belum tersedia")
    return HTMLResponse(_page_html(page))


@app.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest():
    return FileResponse(DASHBOARD_PATH.parent / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(DASHBOARD_PATH.parent / "sw.js", media_type="text/javascript")


@app.get("/fiscycle-icon.svg", include_in_schema=False)
def app_icon():
    return FileResponse(DASHBOARD_PATH.parent / "fiscycle-icon.svg", media_type="image/svg+xml")

