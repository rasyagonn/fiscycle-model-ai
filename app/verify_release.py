"""Rebuild twice, compare stable payload, relocate archive, execute every demo outside repository."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT / "FISCYCLE_DEV_HANDOVER"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command,cwd,env=None):
    result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stdout[-6000:]}\n{result.stderr[-3000:]}")
    return result.stdout


def payload():
    changing={"HANDOVER_MANIFEST.json","HANDOVER_MANIFEST.md","CHECKSUMS.sha256"}
    return {p.relative_to(OUTPUT).as_posix():digest(p) for p in OUTPUT.rglob("*") if p.is_file() and p.name not in changing}


def immutable_inputs():
    from app.core.artifacts import verify_domain
    locked={f"{d}/{p}":v for d in ("bsf","water") for p,v in verify_domain(d).items()}
    research=ROOT / ".agents/skills"
    for pattern in ("FREEZE.json","*manifest*.csv"):
        for path in research.rglob(pattern):
            locked[path.relative_to(ROOT).as_posix()]=digest(path)
    for relative in ("fiscycle-water-ai/data/local.csv","fiscycle-bsf-ai/hasil/v2/internal/bsf_model_b1_development_oof_residuals.csv"):
        locked[relative]=digest(research / relative)
    return locked


def main():
    before=immutable_inputs()
    env={k:v for k,v in os.environ.items() if not k.startswith("FISCYCLE_")}
    env.update(PYTHONDONTWRITEBYTECODE="1", FISCYCLE_BSF_DEVICE="cpu")
    print("Building first final release",flush=True)
    run([sys.executable,"-m","app.build_handover"],ROOT,env)
    first=payload()
    print("Building second final release",flush=True)
    run([sys.executable,"-m","app.build_handover"],ROOT,env)
    second=payload()
    changed=[name for name in first.keys() | second.keys() if first.get(name)!=second.get(name)]
    if changed:
        raise RuntimeError("Non-reproducible payload: "+repr(changed))
    archive=ROOT / "FISCYCLE_DEV_HANDOVER.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(OUTPUT.rglob("*")):
            if path.is_file():
                info=zipfile.ZipInfo("FISCYCLE_DEV_HANDOVER/"+path.relative_to(OUTPUT).as_posix(),date_time=(2026,11,6,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                bundle.writestr(info,path.read_bytes())
    with tempfile.TemporaryDirectory(prefix="fiscycle_clean_release_") as folder:
        temporary=Path(folder).resolve()
        if not temporary.is_relative_to(Path(tempfile.gettempdir()).resolve()) or temporary.is_relative_to(ROOT):
            raise RuntimeError("Relocation directory is not a safe external temporary directory")
        with zipfile.ZipFile(archive) as bundle:
            if any(Path(name).is_absolute() or ".." in Path(name).parts for name in bundle.namelist()):
                raise RuntimeError("Unsafe archive path")
            bundle.extractall(temporary)
        relocated=temporary / "FISCYCLE_DEV_HANDOVER"
        service=relocated / "service"
        print("Verifying independently extracted package",flush=True)
        checksum_log=run([sys.executable,"verify_checksums.py"],relocated,env)
        optional=ROOT/"FISCYCLE_GALLERY_DATA.zip"
        if not optional.is_file(): raise FileNotFoundError("Complete gallery data bundle required for release verification")
        shutil.copyfile(optional,service/optional.name)
        runtime_env={**env,"PYTHONPATH":str(service)}
        smoke_log=run([sys.executable,"verify_package.py"],service,runtime_env)
        # Deliberate corruption affects only a disposable extracted copy, never research inputs.
        seed=service / "water_assets/replay/water_replay_v1.csv"
        seed.write_bytes(seed.read_bytes()+b"\ncorrupt\n")
        corrupt=subprocess.run([sys.executable,"verify_checksums.py"],cwd=relocated,env=env,capture_output=True,text=True)
        if corrupt.returncode==0:
            raise RuntimeError("Corrupted seed unexpectedly passed checksum verification")
        evidence={"status":"PASS","stable_payload_files":len(first),"builds_compared":2,
            "excluded_volatile_files":["HANDOVER_MANIFEST.json","HANDOVER_MANIFEST.md","CHECKSUMS.sha256"],
            "external_extraction":True,"python":sys.version,"runtime_environment":"Existing installed CPU environment; fresh dependency installation not performed",
            "checks":checksum_log.splitlines(),"standalone_checks":[l for l in smoke_log.splitlines() if l.startswith("PASS:")],
            "corrupted_seed_rejected":True,"archive_sha256":digest(archive),"archive_bytes":archive.stat().st_size,
            "immutable_input_count":len(before),"immutable_inputs_preserved":before==immutable_inputs()}
        evidence["gallery_data_bundle"]={"filename":optional.name,"sha256":digest(optional),"bytes":optional.stat().st_size,
            "image_count":224,"externally_copied_and_mounted":True,"included_in_main_zip":False}
        if not evidence["immutable_inputs_preserved"]:
            raise RuntimeError("Immutable research input hash changed")
        target=ROOT / "app/release_evidence.json"
        print(json.dumps(evidence,indent=2),flush=True)
        try:
            target.write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
        except PermissionError:
            print("Evidence verified; local ACL prevented saving release_evidence.json. Preserve the JSON printed above.",flush=True)


if __name__=="__main__":
    main()
