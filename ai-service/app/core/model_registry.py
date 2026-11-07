"""Pinned, checksummed artifact resolution shared by local and HF runtimes."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
KEYS = {"water", "bsf_a1", "bsf_a2", "bsf_b1"}
REPORTS = {}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_relative(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or ":" in value or str(p) != value:
        raise ValueError("Unsafe artifact path")
    return p


def load_registry(path=None):
    path = Path(path or os.getenv("FISCYCLE_MODEL_REGISTRY", ROOT/"model_registry.json"))
    if not path.is_absolute(): path = ROOT/path
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("models", {})) != KEYS:
        raise ValueError("Registry must contain exactly four supported model bundles")
    for key, entry in data["models"].items():
        if entry.get("domain") != ("water" if key == "water" else "bsf"):
            raise ValueError("Model domain mismatch")
        if not entry.get("files"): raise ValueError("Empty artifact bundle")
        for name, value in entry["files"].items():
            safe_relative(name)
            if not re.fullmatch(r"[0-9a-f]{64}", value): raise ValueError("Invalid checksum")
    return data


def validate_hf_entry(entry):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", entry.get("repo_id") or ""):
        raise ValueError("Valid HF repository ID required")
    if not re.fullmatch(r"[0-9a-f]{40}", entry.get("revision") or ""):
        raise ValueError("HF requires a pinned full commit SHA; branches/tags are rejected")


def resolve_bundle(entry, source):
    if source == "local":
        base = Path(os.getenv("FISCYCLE_LOCAL_MODEL_PATH", ROOT))
        folder = (base/entry["local_dir"]).resolve()
        origin, revision = "LOCAL_CHECKSUM_VERIFIED", None
    elif source == "huggingface":
        validate_hf_entry(entry)
        os.environ.setdefault("HF_HOME", str(ROOT/".cache/huggingface"))
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        from huggingface_hub import snapshot_download, hf_hub_download, get_token
        kwargs = dict(repo_id=entry["repo_id"], revision=entry["revision"], token=get_token(),
                      allow_patterns=list(entry["files"])+["checksums.json"])
        strict_offline = os.getenv("FISCYCLE_HF_OFFLINE", "0").lower() in {"1", "true"}
        try:
            folder = Path(snapshot_download(**kwargs, local_files_only=True))
            origin = "HF_CACHE_OFFLINE"
        except Exception:
            if strict_offline: raise
            folder = Path(snapshot_download(**kwargs, local_files_only=False))
            origin = "HF_PINNED_DOWNLOAD"
        if folder.name != entry["revision"]: raise ValueError("Resolved revision mismatch")
        receipt = Path(hf_hub_download(repo_id=entry["repo_id"], revision=entry["revision"],
                                      filename="checksums.json", token=get_token(), local_files_only=True))
        checks = json.loads(receipt.read_text(encoding="utf-8"))
        if any(checks.get(name) != value for name,value in entry["files"].items()):
            raise ValueError("Downloaded checksum manifest differs from trusted registry")
        revision = folder.name
    else:
        raise ValueError("FISCYCLE_MODEL_SOURCE must be local or huggingface")
    for name, expected in entry["files"].items():
        if not (folder/name).is_file() or digest(folder/name) != expected:
            raise ValueError("Model checksum verification failed")
    return folder, origin, revision


def prepare_runtime():
    """Resolve artifacts before runtime modules bind paths; errors stay per bundle."""
    data = load_registry()
    source = os.getenv("FISCYCLE_MODEL_SOURCE", "local").lower()
    if source not in {"local", "huggingface"}: raise ValueError("Unsupported model source")
    fingerprint = hashlib.sha256(json.dumps({"source":source,"registry":data},sort_keys=True).encode()).hexdigest()
    base = Path(os.getenv("FISCYCLE_MODEL_CACHE", ROOT/".cache/runtime"))/fingerprint
    base.mkdir(parents=True, exist_ok=True)
    from filelock import FileLock
    for key, entry in data["models"].items():
        target = base/("water_assets" if key == "water" else "bsf_assets")
        report = {"model_name":key,"model_version":entry["version"],"preprocessing_version":entry["preprocessing_version"],
                  "model_source":source,"repo_id":entry["repo_id"],"requested_revision":entry["revision"] if source == "huggingface" else None,
                  "resolved_revision":None,"model_checksums":entry["files"],"artifacts_verified":False,"error":None}
        try:
            with FileLock(str(base/(key+".lock")), timeout=120):
                folder, origin, revision = resolve_bundle(entry, source)
                for name, expected in entry["files"].items():
                    dst = target/name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.is_file() or digest(dst) != expected:
                        pending = dst.with_name(dst.name+".tmp")
                        shutil.copyfile(folder/name, pending)
                        if digest(pending) != expected: raise ValueError("Artifact changed during copy")
                        pending.replace(dst)
                report.update(artifacts_verified=True, resolved_revision=revision, cache_behavior=origin)
        except Exception as exc:
            report["error"] = {"code":"MODEL_ARTIFACT_UNAVAILABLE", "type":type(exc).__name__}
        REPORTS[key] = report
    return base, data
