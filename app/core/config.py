from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PACKAGED_WATER = REPOSITORY_ROOT / "water_assets"
WATER_QUALITY_ROOT = Path(os.getenv("FISCYCLE_WATER_ROOT", str(_PACKAGED_WATER if _PACKAGED_WATER.is_dir() else REPOSITORY_ROOT / ".agents" / "skills" / "fiscycle-water-ai"))).resolve()
_PACKAGED_BSF = REPOSITORY_ROOT / "bsf_assets"
BSF_ROOT = Path(os.getenv("FISCYCLE_BSF_ROOT", str(_PACKAGED_BSF if _PACKAGED_BSF.is_dir() else REPOSITORY_ROOT / ".agents" / "skills" / "fiscycle-bsf-ai"))).resolve()
BSF_MODELS_DIR = BSF_ROOT / "models"
BSF_REPLAY_CSV = Path(os.getenv("FISCYCLE_BSF_REPLAY_CSV", str(BSF_ROOT / "replay" / "bsf_replay_development_v1.csv"))).resolve()
BSF_HISTORY_DB = Path(os.getenv("FISCYCLE_BSF_HISTORY_DB", str(APP_DIR / "state" / "bsf_history.sqlite3"))).resolve()
BSF_GALLERY_ROOT = Path(os.getenv("FISCYCLE_BSF_GALLERY_ROOT", str(BSF_ROOT / "gallery" if (BSF_ROOT / "gallery").is_dir() else BSF_ROOT / "hasil/model_a_gallery_v1"))).resolve()
BSF_GALLERY_DATA = Path(os.getenv("FISCYCLE_BSF_GALLERY_DATA", str(REPOSITORY_ROOT / "FISCYCLE_GALLERY_DATA.zip"))).resolve()
BSF_API_PREFIX = os.getenv("FISCYCLE_BSF_API_PREFIX", "/api/v1/bsf").rstrip("/")
import re
if not re.fullmatch(r"/[a-zA-Z0-9_/-]+", BSF_API_PREFIX):
    raise ValueError("FISCYCLE_BSF_API_PREFIX must start with /")
STATIC_DIR = APP_DIR / "static"
DASHBOARD_PATH = STATIC_DIR / "dashboard.html"

MAX_BODY_BYTES = int(os.getenv("FISCYCLE_MAX_BODY_BYTES", str(10 * 1024 * 1024)))


def register_domain_paths() -> None:
    """Make the two existing, hyphenated domain roots importable without moving artifacts."""
    for path in (WATER_QUALITY_ROOT, BSF_MODELS_DIR):
        resolved = str(path.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
    research_root = str(BSF_ROOT.resolve())
    if research_root not in sys.path:
        sys.path.append(research_root)

