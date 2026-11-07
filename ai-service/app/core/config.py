"""Service config: model roots, replay mounts and private runtime state."""
import os
from pathlib import Path
import sys

# Runtime must never install optional packages while handling user requests.
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
os.environ.setdefault("YOLO_OFFLINE", "true")

APP_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = APP_DIR.parent
if os.getenv("FISCYCLE_SKIP_REGISTRY_BOOTSTRAP") == "1":
    MODEL_REGISTRY = None
    MODEL_CACHE = REPOSITORY_ROOT/".cache/runtime"
else:
    from app.core.model_registry import prepare_runtime
    MODEL_CACHE, MODEL_REGISTRY = prepare_runtime()
WATER_QUALITY_ROOT = (Path(os.getenv("FISCYCLE_WATER_ROOT", MODEL_CACHE/"water_assets")) if MODEL_REGISTRY is None else MODEL_CACHE/"water_assets").resolve()
BSF_ROOT = (Path(os.getenv("FISCYCLE_BSF_ROOT", MODEL_CACHE/"bsf_assets")) if MODEL_REGISTRY is None else MODEL_CACHE/"bsf_assets").resolve()
BSF_MODELS_DIR = BSF_ROOT / "models"
REPLAY_PATH = Path(os.getenv("FISCYCLE_REPLAY_PATH", REPOSITORY_ROOT/"replay")).resolve()
_PRIVATE_SEED = REPOSITORY_ROOT.parent/"PRIVATE_WATER_REPLAY/water_replay_v1.csv"
_DEFAULT_WATER_SEED = _PRIVATE_SEED if _PRIVATE_SEED.is_file() else REPLAY_PATH/"water/water_replay_v1.csv"
WATER_REPLAY_CSV = Path(os.getenv("FISCYCLE_WATER_REPLAY_CSV", _DEFAULT_WATER_SEED)).resolve()
BSF_REPLAY_CSV = Path(os.getenv("FISCYCLE_BSF_REPLAY_CSV", REPLAY_PATH/"bsf/bsf_replay_development_v1.csv")).resolve()
BSF_HISTORY_DB = Path(os.getenv("FISCYCLE_DATABASE_PATH", REPOSITORY_ROOT/".cache/state/bsf_history.sqlite3")).resolve()
DEMO_GALLERY_PATH = Path(os.getenv("FISCYCLE_DEMO_GALLERY_PATH", REPOSITORY_ROOT/"assets/demo_gallery")).resolve()
BSF_API_PREFIX = os.getenv("FISCYCLE_BSF_API_PREFIX", "/api/v1/bsf").rstrip("/")
MAX_BODY_BYTES = int(os.getenv("FISCYCLE_MAX_BODY_BYTES", str(10*1024*1024)))


def register_domain_paths():
    for path in [BSF_MODELS_DIR, WATER_QUALITY_ROOT]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

