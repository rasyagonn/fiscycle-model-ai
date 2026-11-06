"""Prepare and freeze BSF A1/A2 datasets; never fit a model or modify raw data.

Run: python .agents/skills/fiscycle-bsf-ai/prepare_model_a.py
Verify: same command with --verify (also the default when FREEZE.json exists).
All paths in outputs are relative to this script's domain directory.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import platform
import re
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
AUDIT = ROOT / "hasil/model_a_audit"
OUT = ROOT / "hasil/model_a_preparation_v1"
SEED = 20261105
SPLITS = ("train", "validation", "test")
PROPORTIONS = np.array([.70, .15, .15])
SUSPECT_BASES = {
    "001_jpg", "2023-08-31-12-39-17_jpg", "2023-08-31-12-42-31_jpg",
    "2023-08-31-12-43-29_jpg", "2023-10-13-11-17-05_jpg",
    "2023-10-24-16-29-52_jpg", "image_1686225670032_png_jpg",
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False,
                                     allow_nan=False) + "\n", encoding="utf-8")


def csv(name, frame):
    frame.to_csv(OUT / name, index=False, lineterminator="\n")


class Graph:
    def __init__(self, ids):
        self.parent = {str(x): str(x) for x in ids}
        self.edges = []

    def find(self, x):
        x = str(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, left, right, reason):
        left, right = str(left), str(right)
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)
        self.edges.append((left, right, reason))

    def tokens(self, rows):
        seen = {}
        for identity, tokens in rows:
            for token in tokens:
                if token in seen:
                    self.join(identity, seen[token], token)
                else:
                    seen[token] = identity

    def groups(self, prefix):
        components = {}
        for x in sorted(self.parent):
            components.setdefault(self.find(x), []).append(x)
        return {x: prefix + hashlib.sha256("|".join(xs).encode()).hexdigest()[:16]
                for xs in components.values() for x in xs}


def dated_source(base):
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})-", base)
    if match:
        return "-".join(match.groups())
    match = re.match(r"image_(\d{13})", base)
    if match:
        return datetime.fromtimestamp(int(match[1]) / 1000, timezone.utc).date().isoformat()
    return ""


def verify_inputs():
    """Refresh byte evidence. Cached full-decode/pHash audit applies only if bytes match."""
    source = []
    provenance = json.loads((AUDIT / "provenance.json").read_text())
    for p in sorted(DATA.rglob("*")):
        if not p.is_file():
            continue
        sha, md5 = hashlib.sha256(), hashlib.md5()
        before = p.stat()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                sha.update(chunk)
                md5.update(chunk)
        after = p.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        if p.name in ("Single Larvae data.zip", "Larvae--size-data.xlsx"):
            assert md5.hexdigest() == provenance["expected_files"][p.name]["md5"]
        source.append(dict(path=p.relative_to(ROOT).as_posix(), bytes=after.st_size,
                           mtime_ns=after.st_mtime_ns, sha256=sha.hexdigest()))
    multi = pd.read_csv(AUDIT / "multi_images.csv", keep_default_na=False)
    single = pd.read_csv(AUDIT / "single_images.csv", keep_default_na=False)
    assert len(multi) == 321 and len(single) == 1608
    assert (multi.error == "").all() and (single.error == "").all()
    assert single.sha256.is_unique and single.pixel_sha256.is_unique
    for r in multi.itertuples():
        p = ROOT / r.path.replace("\\", "/")
        assert digest(p) == r.sha256
        with Image.open(p) as im:
            assert im.size == (r.width, r.height) and im.mode == r.mode
    with zipfile.ZipFile(DATA / "Single Larvae data.zip") as z:
        assert set(n for n in z.namelist() if not n.endswith("/")) == set(single.path)
        for r in single.itertuples():
            # One JPEG at a time, approximately 4 MB; no 7 GB in-memory extraction.
            payload = z.read(r.path)
            assert hashlib.sha256(payload).hexdigest() == r.sha256
            with Image.open(io.BytesIO(payload)) as im:
                assert im.size == (r.width, r.height) and im.mode == r.mode
                assert str(im.getexif().get(306, "")) == r.exif_datetime
    # Near-duplicate evidence must refer to the unchanged image inventory.
    near = pd.read_csv(AUDIT / "near_duplicate_candidates.csv")
    for kind, images in (("multi", multi), ("single", single)):
        hashes = dict(zip(images.path, images.phash))
        expected = set()
        for (a, ha), (b, hb) in itertools.combinations(hashes.items(), 2):
            distance = (int(ha, 16) ^ int(hb, 16)).bit_count()
            if distance <= 4:
                expected.add((min(a, b), max(a, b), distance))
        actual = {(min(r.left, r.right), max(r.left, r.right), r.phash_hamming)
                  for r in near[near.dataset == kind].itertuples()}
        assert expected == actual
    return multi, single, near, pd.DataFrame(source)


def prepare_a1(images, near):
    rows = []
    for r in images.itertuples():
        path = r.path.replace("\\", "/")
        label = Path(path.replace("/Images/", "/Labels/")).with_suffix(".txt")
        counts = [0, 0]
        valid = True
        for line in (ROOT / label).read_text().splitlines():
            fields = line.split()
            cls = int(fields[0])
            coords = np.array([float(x) for x in fields[1:]])
            assert cls in (0, 1)
            valid &= len(coords) >= 6 and len(coords) % 2 == 0
            valid &= bool(np.isfinite(coords).all() and ((coords >= 0) & (coords <= 1)).all())
            points = coords.reshape(-1, 2)
            area = abs(np.dot(points[:, 0], np.roll(points[:, 1], 1)) -
                       np.dot(points[:, 1], np.roll(points[:, 0], 1))) / 2
            valid &= area > 0
            counts[cls] += 1
        assert sum(counts) == r.label_count
        base = Path(path).name.split(".rf.")[0]
        flags = ["FLAG_AMBIGUOUS_CLASS", "FLAG_REVIEW_REQUIRED"]
        if base in SUSPECT_BASES:
            flags.append("FLAG_POSSIBLE_MISSED_ANNOTATIONS")
        if 0 < sum(counts) <= 5:
            flags.append("FLAG_LOW_LABEL_COUNT_REVIEW_NOT_PROVEN_ERROR")
        if not sum(counts):
            assert base == "2023-10-25-17-06-18_jpg"
            flags.insert(0, "EXCLUDE_EMPTY_LABEL_WITH_VISIBLE_LARVAE")
        rows.append(dict(image_path=path, label_path=label.as_posix(), image_sha256=r.sha256,
                         label_sha256=digest(ROOT / label), source_group_id=base,
                         date_proxy=dated_source(base), width=r.width, height=r.height,
                         class_0_count=counts[0], class_1_count=counts[1],
                         total_instances=sum(counts), polygon_structurally_valid=valid,
                         annotation_candidate=valid and sum(counts) > 0,
                         eligibility_status="|".join(flags),
                         training_ready=False, metric_eligible=False,
                         notes="Anonymous class_0/class_1; completeness unverified; public camera timezone UNKNOWN"))
    a = pd.DataFrame(rows).sort_values("image_path").reset_index(drop=True)
    graph = Graph(a.image_path)
    graph.tokens((r.image_path, ["source:" + r.source_group_id] +
                  (["day:" + r.date_proxy] if r.date_proxy else [])) for r in a.itertuples())
    for r in near[near.dataset == "multi"].itertuples():
        graph.join(r.left.replace("\\", "/"), r.right.replace("\\", "/"),
                   "pHash<=4_conservative_scene_union")
    for column in ("sha256", "pixel_sha256"):
        graph.tokens((r.path.replace("\\", "/"), [column + ":" + getattr(r, column)])
                     for r in images.itertuples())
    a["split_group_id"] = a.image_path.map(graph.groups("a1_"))
    dated_groups = set(a.loc[a.date_proxy != "", "split_group_id"])
    a["primary_split_eligible"] = a.annotation_candidate & a.split_group_id.isin(dated_groups)
    a.loc[a.annotation_candidate & ~a.primary_split_eligible, "eligibility_status"] += "|QUARANTINE_UNKNOWN_SCENE"
    a["density"] = pd.cut(a.total_instances, [-1, 0, 5, 29, np.inf],
                            labels=["empty", "low_1_5", "medium_6_29", "high_30_plus"]).astype(str)
    return a, graph


def a2_graph(a, both_dates=False, ancestry=False, origin_cohort=False):
    graph = Graph(a.L_ID)
    graph.tokens((r.L_ID, ["date:" + r.EXIF_date] +
                  (["date:" + r.Excel_Date] if both_dates else []) +
                  (["batch:" + r.Batch_ID] if r.Batch_ID != "BATCH_UNKNOWN" else []) +
                  (["origin:Foulum_hatched_2023-07-20"] if origin_cohort and r.Batch_ID in ("B007", "B008", "B009") else []) +
                  (["ancestry:B007_B008_B010"] if ancestry and r.Batch_ID in ("B007", "B008", "B010") else []))
                 for r in a.itertuples())
    return graph


def prepare_a2(images, near):
    metadata = pd.read_excel(DATA / "Larvae--size-data.xlsx", sheet_name="Larva Data")
    metadata.insert(0, "excel_row", np.arange(2, len(metadata) + 2))
    metadata["Date"] = pd.to_datetime(metadata.Date).dt.strftime("%Y-%m-%d")
    old = pd.read_csv(AUDIT / "metadata_audit.csv")
    pd.testing.assert_frame_equal(metadata, old, check_dtype=False)
    assert metadata.L_ID.is_unique and len(metadata) == 1613
    img = images.rename(columns={"filename_id": "L_ID", "path": "archive_member", "sha256": "image_sha256"})
    assert img.L_ID.is_unique
    a = img.merge(metadata, on="L_ID", validate="one_to_one", how="left", indicator=True)
    assert (a._merge == "both").all()
    a = a.drop(columns=["_merge"]).sort_values("L_ID").reset_index(drop=True)
    a = a.rename(columns={"Date": "Excel_Date"})
    a["archive_path"] = "data/Single Larvae data.zip"
    a["Batch_ID_raw"] = a.Batch_ID
    a["Batch_ID"] = a.Batch_ID.fillna("BATCH_UNKNOWN")
    a["EXIF_date"] = pd.to_datetime(a.exif_datetime, format="%Y:%m:%d %H:%M:%S").dt.strftime("%Y-%m-%d")
    a["date_match"] = a.Excel_Date == a.EXIF_date
    a["Weight_mg"] = a.Weight * 1000
    a["weight_unit"], a["length_unit"], a["width_unit"] = "g", "mm", "UNKNOWN"
    a["camera_timezone"] = "UNKNOWN"
    a["width_valid"] = np.isfinite(a.Width) & a.Width.gt(0)
    a["width_status"] = np.select([a.Width.isna(), a.Width.eq(0), a.width_valid],
                                    ["WIDTH_MISSING", "WIDTH_ZERO", "WIDTH_POSITIVE"], "WIDTH_INVALID")
    a["image_weight_eligible"] = np.isfinite(a.Weight) & a.Weight.gt(0) & a.error.eq("")
    a["length_baseline_eligible"] = a.image_weight_eligible & np.isfinite(a.Length) & a.Length.gt(0)
    a["length_width_baseline_eligible"] = a.length_baseline_eligible & a.width_valid
    simple = a2_graph(a)
    primary = a2_graph(a, both_dates=True, ancestry=True, origin_cohort=True)
    a["batch_group_id"] = a.Batch_ID
    a["session_group_id"] = a.EXIF_date
    a["connected_group_id"] = a.L_ID.astype(str).map(simple.groups("c_"))
    a["split_group_id"] = a.L_ID.astype(str).map(primary.groups("a2_"))
    by_id = a.set_index("L_ID")
    suspicious = set()
    reviews = []
    all_phash = a2_graph(a, both_dates=True, ancestry=True, origin_cohort=True)
    for r in near[near.dataset == "single"].itertuples():
        left, right = int(Path(r.left).stem), int(Path(r.right).stem)
        cross = by_id.loc[left, "split_group_id"] != by_id.loc[right, "split_group_id"]
        if cross:
            suspicious.update([left, right])
        all_phash.join(left, right, "pHash_candidate_not_identity_proof")
        reviews.append(dict(left_id=left, right_id=right, phash_hamming=r.phash_hamming,
                            crosses_primary_group=bool(cross), confirmed_duplicate=False,
                            review_status="UNREVIEWED", action="QUARANTINE_BOTH" if cross else "KEEP_SAME_GROUP"))
    a["cross_group_similarity_pending"] = a.L_ID.isin(suspicious)
    a["primary_split_eligible"] = (a.image_weight_eligible & a.Batch_ID.ne("BATCH_UNKNOWN") &
                                     a.date_match & ~a.cross_group_similarity_pending)
    a["eligibility_status"] = ["|".join(["ELIGIBLE_WEIGHT_IMAGE", "IMAGE_METADATA_OK", r.width_status] +
        (["BATCH_MISSING"] if r.Batch_ID == "BATCH_UNKNOWN" else []) +
        (["DATE_MISMATCH"] if not r.date_match else []) +
        (["CROSS_GROUP_SIMILARITY_REVIEW"] if r.cross_group_similarity_pending else []))
        for r in a.itertuples()]
    a["notes"] = "Measured individual weight; wet/dry UNKNOWN. Sex/ID/filename/batch/date are not predictors."
    missing = metadata[~metadata.L_ID.isin(a.L_ID)].copy()
    missing["Batch_ID_raw"] = missing.Batch_ID
    missing["Batch_ID"] = missing.Batch_ID.fillna("BATCH_UNKNOWN")
    missing["eligibility_status"] = "NO_IMAGE"
    return a, primary, pd.DataFrame(reviews), missing, len(set(all_phash.groups("x_").values()))


def choose_split(a, group, kind):
    """Fixed pretraining objective; all assignments are WHOLE GROUPS, never rows."""
    eligible = a[a.primary_split_eligible].copy()
    groups = sorted(eligible[group].unique())
    counts = eligible.groupby(group).size().reindex(groups).to_numpy(float)
    if kind == "a2":
        bins = pd.cut(eligible.Weight_mg, [-np.inf, 150, 200, 250, 300, np.inf], right=False)
    else:
        bins = eligible.density
    hist = pd.crosstab(eligible[group], bins).reindex(groups, fill_value=0).to_numpy(float)
    global_hist = hist.sum(axis=0) / counts.sum()
    if len(groups) <= 10:
        assignments = np.array(list(itertools.product(range(3), repeat=len(groups))), dtype=np.int8)
    else:
        assignments = np.random.default_rng(SEED).choice(3, size=(20000, len(groups)), p=PROPORTIONS)
    scores = np.zeros(len(assignments))
    for split in range(3):
        mask = (assignments == split).astype(float)
        n = mask @ counts
        scores += 12 * (n / counts.sum() - PROPORTIONS[split]) ** 2
        scores += np.mean((mask @ hist / np.maximum(n[:, None], 1) - global_hist) ** 2, axis=1)
        scores[n / counts.sum() < .08] = np.inf
    if kind == "a1":
        sources = eligible.groupby(group).source_group_id.nunique().reindex(groups).to_numpy(float)
        classes = eligible.groupby(group)[["class_0_count", "class_1_count"]].sum().reindex(groups).to_numpy(float)
        for split in range(3):
            mask = (assignments == split).astype(float)
            scores += .5 * (mask @ sources / sources.sum() - PROPORTIONS[split]) ** 2
            c = mask @ classes
            scores += .5 * np.mean((c / np.maximum(c.sum(axis=1)[:, None], 1) - classes.sum(axis=0) / classes.sum()) ** 2, axis=1)
    best = int(np.argmin(scores))
    assert np.isfinite(scores[best])
    return dict(zip(groups, [SPLITS[x] for x in assignments[best]])), float(scores[best])


def assign(a, mapping, group="split_group_id"):
    a = a.copy()
    a["reserved_group_split"] = a[group].map(mapping).fillna("unassigned")
    a["split"] = a.reserved_group_split.where(a.primary_split_eligible, "quarantine")
    if "annotation_candidate" in a:
        a.loc[~a.annotation_candidate, "split"] = "excluded"
    a["is_final_test"] = a.split.eq("test")
    return a


def distribution(values):
    v = pd.Series(values).dropna().astype(float)
    if not len(v):
        return {"count": 0}
    return dict(count=len(v), min=float(v.min()), max=float(v.max()), mean=float(v.mean()),
                median=float(v.median()), std=float(v.std()) if len(v) > 1 else None,
                percentiles={str(p): float(v.quantile(p / 100)) for p in [1, 5, 25, 75, 95, 99]})


def summary(a, kind, group="split_group_id"):
    result = {}
    for name, s in a.groupby("split", sort=True):
        item = dict(images=len(s), groups=int(s[group].nunique()))
        if kind == "a1":
            item.update(source_groups=int(s.source_group_id.nunique()), polygons=int(s.total_instances.sum()),
                        class_0=int(s.class_0_count.sum()), class_1=int(s.class_1_count.sum()),
                        density={str(k): int(v) for k, v in s.density.value_counts().items()},
                        instance_count=distribution(s.total_instances))
        else:
            item.update(batches=sorted(s.loc[s.Batch_ID != "BATCH_UNKNOWN", "Batch_ID"].unique()),
                        batch_count=int(s.loc[s.Batch_ID != "BATCH_UNKNOWN", "Batch_ID"].nunique()),
                        exif_date_count=int(s.EXIF_date.nunique()), excel_date_count=int(s.Excel_Date.nunique()),
                        weight_mg=distribution(s.Weight_mg), length_mm=distribution(s.Length),
                        valid_width=int(s.width_valid.sum()), missing_batch=int(s.Batch_ID.eq("BATCH_UNKNOWN").sum()),
                        date_mismatch=int((~s.date_match).sum()))
        result[name] = item
    return result


def crossing(a, column):
    active = a[a.split.isin(SPLITS)]
    return int(active.groupby(column).split.nunique().gt(1).sum())


def leakage_checks(a1, a2, near):
    assert len(a1) == 321 and len(a2) == 1608
    assert a1.image_path.is_unique and a2.L_ID.is_unique
    assert a1.total_instances.sum() == 6612
    assert a1.class_0_count.sum() == 4713 and a1.class_1_count.sum() == 1899
    assert a1.polygon_structurally_valid.all()
    assert (a1.split == "excluded").sum() == 2
    assert (a1.split == "quarantine").sum() == 8
    assert a1.primary_split_eligible.sum() == 311
    assert a2.split_group_id.nunique() == 6
    assert a2.primary_split_eligible.sum() == 1292
    expected_active = a2.image_weight_eligible & a2.Batch_ID.ne("BATCH_UNKNOWN") & a2.date_match & ~a2.cross_group_similarity_pending
    assert a2.primary_split_eligible.equals(expected_active)
    assert a2.image_weight_eligible.sum() == 1608
    assert a2.length_width_baseline_eligible.sum() == 1435
    assert a2.Batch_ID.eq("BATCH_UNKNOWN").sum() == 217
    assert (~a2.date_match).sum() == 55
    assert not a1.metric_eligible.any() and not a1.training_ready.any()
    for a, cols in ((a1, ["source_group_id", "split_group_id"]),
                    (a2, ["split_group_id", "Batch_ID", "Excel_Date", "EXIF_date"])):
        assert set(a.loc[a.primary_split_eligible, "split"]) == set(SPLITS)
        assert a.is_final_test.equals(a.split.eq("test"))
        assert a.groupby("split_group_id").reserved_group_split.nunique().max() == 1
        for col in cols:
            assert crossing(a, col) == 0, col
    active = a2[a2.split.isin(SPLITS)]
    ancestry = active[active.Batch_ID.isin(["B007", "B008", "B009", "B010"])]
    assert ancestry.split.nunique() == 1
    for kind, a, key in (("multi", a1, "image_path"), ("single", a2, "archive_member")):
        splits = a.set_index(key).split.to_dict()
        for r in near[near.dataset == kind].itertuples():
            left, right = r.left.replace("\\", "/"), r.right.replace("\\", "/")
            if splits[left] in SPLITS and splits[right] in SPLITS:
                assert splits[left] == splits[right]
    return {"row_coverage": "PASS", "source_group_overlap": 0, "known_batch_overlap": 0,
            "known_date_overlap": 0, "known_ancestry_or_origin_cohort_overlap": 0,
            "screened_phash_candidate_cross_split_pairs": 0,
            "unknown_relationships": "NOT_PROVEN_ABSENT", "no_model_fitted": True}


def table(rows):
    keys = list(rows[0])
    return "| " + " | ".join(keys) + " |\n| " + " | ".join(["---"] * len(keys)) + " |\n" + "\n".join(
        "| " + " | ".join(str(row[k]) for k in keys) + " |" for row in rows)


def build_report(a1, a2, summaries, candidates, checks):
    s1, s2 = summaries["a1"], summaries["a2"]
    t1 = table([dict(split=s, images=v["images"], source_groups=v["source_groups"], groups=v["groups"],
                     polygons=v["polygons"], class_0=v["class_0"], class_1=v["class_1"], density=v["density"])
                for s, v in s1.items()])
    t2 = table([dict(split=s, images=v["images"], groups=v["groups"], batches=v["batch_count"],
                     exif_dates=v["exif_date_count"], excel_dates=v["excel_date_count"],
                     valid_width=v["valid_width"], missing_batch=v["missing_batch"], date_mismatch=v["date_mismatch"])
                for s, v in s2.items()])
    dist = table([dict(split=s, **{k: round(v["weight_mg"][k], 3) for k in ["min", "max", "mean", "median", "std"]},
                       **{"P"+p: round(value, 3) for p, value in v["weight_mg"]["percentiles"].items()})
                  for s, v in s2.items()])
    candidate_table = table([dict(strategy=k, all_groups=v["all_groups"], active_groups=v["active_groups"],
                                active_sizes=v["active_sizes"], counts=v["split_counts"],
                                batch_overlap=v["batch_overlap"], session_overlap=v["session_overlap"],
                                primary_group_overlap=v["primary_group_overlap"])
                            for k, v in candidates.items()])
    hashes = "\n".join(f"- `{name}` SHA-256: `{digest(OUT / name)}`" for name in ("a1_manifest.csv", "a2_manifest.csv"))
    return f"""# Fiscycle Smart BSF Model A — Dataset Preparation v1

Status: **RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED**. Tanggal 5 November 2026 (WIB).
Dataset preparation saja: tidak ada training, augmentasi, prediksi, akurasi, atau deployment.
Direktori ini menyimpan output turunan; raw dan bundle Model B1 tidak diubah.

## Sumber dan verifikasi

Sumber: Quentin Geissmann, *Black Soldier Fly detection, phenotyping and sex prediction dataset*,
[Zenodo v1 / DOI 10.5281/zenodo.13359376](https://zenodo.org/records/13359376), 27 Agustus 2024,
CC BY 4.0 menurut provenance audit. Atribusi ini harus dibawa saat redistribusi.
`../model_a_audit/` berisi audit awal, provenance, overlay, mapping dan kandidat pHash.
Script membaca ulang workbook, semua label, header semua JPEG, SHA-256 semua JPEG termasuk
1.608 member ZIP, serta memverifikasi ulang MD5 ZIP dan workbook terhadap provenance.
Cache full-decode dan pHash audit hanya digunakan setelah byte gambar cocok; pasangan pHash
dihitung ulang dari hash audit, bukan embedding learned. Semua 646 sumber raw dicatat di
`source_integrity.csv`; snapshot B1/audit di `protected_integrity.json`.
Tidak ada ZIP baru diunduh, data diunggah, atau arsip diekstrak penuh. Folder multi-larva
tetap tidak memiliki ZIP asli untuk pembandingan checksum publik.

## A1 Preparation Summary

321 gambar, 321 label, 6.612 polygon, 185 source basename. **319 kandidat annotation valid
secara struktur**, bukan 319 gambar yang kelengkapan anotasinya telah disahkan. Dua positive
image dengan label kosong dikeluarkan; delapan gambar dari source tanpa tanggal yang terhubung
dikarantina (001_jpg=5, 002_jpg=3). **311 gambar memiliki split utama**, tetapi semua menunggu review annotation.
Daftar lengkap flag/exclusion ada di `a1_review_queue.csv`; tidak ada label otomatis diperbaiki.
Flag label rendah <=5 adalah antrean inspeksi, bukan bukti jumlah larva salah.
Flag suspected missed diteruskan dari source yang sudah disorot audit, bukan review baru seluruh gambar.

{t1}

`source_group_id` = basename sebelum `.rf.`. `split_group_id` lebih konservatif: connected
components source + tanggal proxy + semua kandidat pHash<=4 + exact byte/pixel hash.
Tanggal nama file memakai prefix tanggal atau epoch-millisecond UTC-date **sebagai proxy**;
bukan timezone kamera yang terverifikasi. Semua frame dalam satu tanggal tetap bersama,
karena identitas tray/sesi lintas-frame tidak cukup lengkap. `a1_group_edges.csv` mengaudit
alasan penggabungan. Merge pHash konservatif mengurangi jumlah unit independen; ia tidak
membuktikan identitas biologis. Source bertanggal tidak diketahui yang terhubung pHash ke
source bertanggal mengikuti kelompok itu. Source tanpa hubungan tersebut dikarantina.

Kepadatan tinggi (>=30 label) hanya muncul pada **dua kelompok tanggal**. Tidak mungkin
menyebarnya ke tiga split tanpa memecah kelompok. Tabel menunjukkan kekosongan density
tersebut secara eksplisit; jangan mengeklaim seluruh rentang density teruji di setiap split.
Latar/tray yang sama lintas-hari dan hubungan yang lolos screen tetap risiko residual.

**Default yang diusulkan: class-agnostic `visible_bsf_larva`**. Pada loader turunan nanti,
map ID 0 dan 1 ke satu ID 0, pertahankan polygon serta label raw. Ini baru rencana, belum
dilaksanakan. Opsi dua kelas anonim `class_0`/`class_1` memungkinkan eksperimen konsistensi
annotation tetapi tidak punya arti biologis terverifikasi, dan setiap kelas perlu review.
Jangan memberi nama larva/prepupa/sex dari ID tersebut.

Semua test disegel sebagai reserved evaluation. `a1_test_review.csv` mencakup seluruh
gambar test. `is_source_representative` memilih satu nama file leksikografis per basename
untuk menghindari menghitung varian yang sama berulang saat evaluasi; scene berbeda dalam
satu hari masih berkorelasi. `metric_eligible=False` dan `training_ready=False` untuk semua.
Review test khusus kualitas label diperbolehkan sebelum pelatihan, tetapi tidak boleh
memakai hasil model pada test untuk memilih hyperparameter/crop/augmentation.
Perbaiki hanya working copy ber-versi, mewarisi reserved membership, kemudian sahkan annotation.
Known-incomplete labels tidak boleh menghasilkan precision/recall/mAP standar sebelum relabel.

## A2 Preparation Summary

1.608 pasangan gambar–Weight yang valid tetap dicatat; 5 metadata tanpa gambar terpisah
di `a2_metadata_without_image.csv`. ID: 215, 368, 1001, 1282, 1602. Join memakai integer
basename == L_ID, bukan nomor urut Excel. `excel_row`, kolom raw, dua tanggal dan Sex
dipertahankan. `Batch_ID_raw` tetap kosong jika asli kosong; `Batch_ID` analitis memakai
`BATCH_UNKNOWN` tanpa menebak batch. Total workbook missing batch **219**, mapped **217**.
55 date mismatch tetap utuh dan tidak dianggap kesalahan biologis yang sudah terbukti.

Eligibility terpisah: image+Weight **1.608**, Length+Weight **1.608**, Length+Width positif
+Weight **1.435**. Pada mapped rows, Width missing=121, zero=52. Width unit UNKNOWN;
baseline dua ukuran hanya eksperimen numerik, bukan kalibrasi fisik terverifikasi.
Weight (g) x 1.000 = mg; istilah wet/dry tidak dinyatakan. Length berunit mm.
Sex, ID, filename, batch, tanggal, dan kolom frekuensi samping bukan input predictor.

{t2}

### Kandidat grouping dan pemilihan

{candidate_table}

Semua kandidat dibandingkan pada **1.292 baris aktif yang sama**; `all_groups` memakai
seluruh 1.608 baris. Batch UNKNOWN pada kandidat A bukan batch biologis dan hanya ada di
quarantine. JSON menyimpan ukuran semua grup, bobot/Length per split, assignment dan skor.
A (batch) menguji batch baru tetapi sesi dan ancestry dapat menyeberang; B (EXIF day)
menguji tanggal baru tetapi batch dapat menyeberang. C (batch OR EXIF day) lebih kuat,
tetapi belum mengikat kedua tanggal konflik, ancestry B010 dari B007/B008, dan asal kohor.

**Primary ditentukan dari aturan independensi sebelum optimasi distribusi**: connected
batch OR kedua tanggal OR ancestry B007/B008/B010 OR asal kohor, total **6 kelompok**.
`Batch_Info` menyatakan B007/B008/B009 berasal dari Foulum, menetas 20 Juli 2023.
Ini bukan bukti ketiganya saudara biologis, tetapi cukup untuk mengikat ketiganya secara
konservatif sebagai kemungkinan satu kohor asal; B010 ikut melalui hubungan ancestry.
Tanpa batas asal kohor ini, aturan batch+kedua tanggal+ancestry menghasilkan 7 kelompok.
Kedua tanggal
dipakai sebagai batas konservatif, tidak memilih salah satunya sebagai biological truth.
Batch B011/B013 tidak punya deskripsi di Batch_Info; makna generalisasi tetap terbatas.

Menggabungkan seluruh 153 pasangan pHash individu sebagai identitas menghasilkan hanya
**1 komponen**: tidak mungkin split tiga arah. Latar putih/kartu dapat mendominasi pHash,
jadi kandidat bukan duplicate terkonfirmasi. Kebijakan konservatif: **29 pasangan
lintas primary group / 49 ID endpoint** dikarantina untuk review, bukan dinyatakan berbeda.
Ditambah batch kosong dan konflik tanggal, union quarantine **316 baris**, active **1.292**.
Valid image-weight pair tidak dihapus. Primary group dibangun sebelum quarantine, jadi
relasi melalui baris quarantine tetap mencegah leakage antar baris aktif.
Review lengkap di `a2_similarity_review.csv`; reserved membership quarantine tetap tersimpan.
Jangan masukkan kembali baris quarantine tanpa review dan versi baru yang mewarisi reservasi test.

### Distribusi Weight (mg)

{dist}

Statistik Length, seluruh percentile, serta rentang test di luar train tersimpan di
`preparation_summary.json`; visual di `a2_split_distributions.png`. Ketidakseimbangan
biologis antar batch tetap nyata. Test utama hanya satu primary group, B011; jumlah
178 gambar test bukan 178 batch independen. Confidence interval antar-batch dan klaim
generalisasi luas belum didukung. Jangan memindahkan individu ekstrem antar grup hanya
untuk meratakan histogram. Mean/std di sini deskriptif, bukan preprocessing fitted.

## Aturan optimasi yang direproduksi

Target proporsi 70/15/15; hard constraint setiap split >=8% baris aktif. Enumerasi semua
3^G assignment bila G<=10; kandidat lebih besar memakai 20.000 assignment group-level
dengan numpy seed **{SEED}**. Semua grup tetap utuh; urutan group stabil dan tie memilih
assignment pertama. Objective = jumlah antar split [12*(proporsi-rasio target)^2 + mean
square perbedaan fraksi histogram split vs global]. A2 bins mg tetap [-inf,150,200,250,300,inf)
tanpa fitted quantile. A1 histogram density low1–5/medium6–29/high>=30, ditambah 0,5 kali
error proporsi source dan 0,5 kali error fraksi polygon kelas. Score hanya kualitas desain
distribusi, **bukan performa model**. Statistik target dipakai sekali untuk desain yang
diminta, tidak untuk belajar parameter model. Setelah freeze, test tidak boleh dipakai tuning.
Semua scaler, imputasi, feature selection, dan normalisasi learned nanti fit train saja.

## Baseline-ready tables dan praktik training berikutnya

`a2_baseline_length.csv`, `a2_baseline_length_width.csv`, `a2_image_table.csv` berisi
subset sesuai task eligibility dan menyertakan quarantine secara eksplisit. **Wajib filter
split=train/validation/test** untuk eksperimen utama; jangan melatih seluruh tabel.
Bandingkan tiga pendekatan juga pada intersection ID test yang sama, karena Width valid
mengubah populasi evaluasi. Ini tabel, belum ada regresi atau CNN dilatih.

A1: mulai 640x640, transform polygon sinkron dengan gambar; augmentasi train saja dan
setelah annotation review. Evaluasi per unique source representative, laporkan korelasi
scene, density yang tidak tercakup, dan jumlah kelompok independen yang kecil.
A2: streaming/minibatch dari ZIP atau cache turunan terbatas; jangan memuat 7 GB ke RAM.
Simpan full-resolution raw. Uji crop yang benar-benar melokalisasi larva pada train/val,
bukan naive central crop. Hindari transform yang mengubah morfologi fisik atau memotong
larva. Evaluasi shortcut kartu ID, tanda sex, ruler, dan background; crop/masking perlu
review working copy. Kalibrasi pixel-ke-mm belum sah; resize tidak memperbaikinya.
MVP belum memiliki kamera BSF operasional atau dataset gambar BSF lokal.

## Leakage risk dan frozen manifest

Pemeriksaan otomatis: `{json.dumps(checks, ensure_ascii=False)}`.
Zero overlap hanya berlaku pada relasi yang tercatat/screened. Tidak menjamin semua
kemiripan visual, individu, tray lintas-hari, atau hubungan biologis tak tercatat ditemukan.
Belum ada cross-dataset A1/A2 crop matching; jangan melakukan joint training atau menganggap
crop dari A1 setara citra terkontrol A2. Tidak ada label biomass multi-image tervalidasi.

{hashes}

`FREEZE.json` mencatat hash semua output, script, seed, environment dan jumlah split;
output diberi atribut read-only, script menolak rebuild bila freeze sudah ada. Ini
pengaman perubahan tak sengaja dan integritas hash, **bukan WORM atau tanda tangan digital**.
Training berikutnya wajib membaca manifest ini, mengecek hash, dan tidak membuat ulang split.
Reservasi test final; revisi label tidak berarti izin mengacak ulang holdout. Jalankan:
`python .agents/skills/fiscycle-bsf-ai/prepare_model_a.py --verify` dari root repository.

### Model A1
CONDITIONALLY READY

Reason: manifest dan reservasi split sudah siap, tetapi training menunggu review/copy
annotation; standard detection metrics NO-GO sampai completeness test disahkan.

### Model A2
CONDITIONALLY READY

Reason: GO untuk tahap eksperimen baseline pada 1.292 baris grouped yang disegel setelah
otorisasi training; 316 quarantine tidak ikut fit/evaluasi utama. Image model membutuhkan
review crop/shortcut train/val. Width units, calibration, provenance wet/dry dan field
generalization tetap belum terselesaikan. Tidak ada klaim akurasi.

### Combined A1 → A2
NOT READY

Reason: kedua model belum dilatih/diuji, domain crop berbeda, dan belum ada validasi
asosiasi deteksi–berat maupun total biomass pada gambar multi-larva.

### Exact next action

1. Review annotation A1 pada working copy, dahulukan test queue dan suspected missed; pertahankan split dan raw.
2. Review konflik/similarity A2, konfirmasi unit Width dan proses pencitraan; rancang crop memakai train/validation saja.
3. Setelah training diotorisasi, verifikasi freeze dan mulai baseline A2 Length vs Length+Width pada split tetap; test sekali setelah model selection.
"""


def protected_files():
    paths = list(AUDIT.glob("*")) + list((ROOT / "models").rglob("*"))
    paths += [p for p in (ROOT / "hasil").rglob("*") if "model_a" not in p.as_posix()]
    paths += list(ROOT.glob("*b1*"))
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths)) if p.is_file()}


def verify(full_sources=True):
    freeze = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
    assert digest(Path(__file__)) == freeze["script_sha256"], "Preparation script changed"
    for name, sha in freeze["outputs"].items():
        assert digest(OUT / name) == sha, f"Frozen output changed: {name}"
    protected = json.loads((OUT / "protected_integrity.json").read_text())
    for name, sha in protected.items():
        assert digest(ROOT / name) == sha, f"B1/audit changed: {name}"
    if full_sources:
        for r in pd.read_csv(OUT / "source_integrity.csv").itertuples():
            assert digest(ROOT / r.path) == r.sha256, f"Raw changed: {r.path}"
    a1, a2 = (pd.read_csv(OUT / f"a{i}_manifest.csv") for i in (1, 2))
    checks = leakage_checks(a1, a2, pd.read_csv(AUDIT / "near_duplicate_candidates.csv"))
    for name, eligibility in (("a2_baseline_length.csv", "length_baseline_eligible"),
                              ("a2_baseline_length_width.csv", "length_width_baseline_eligible"),
                              ("a2_image_table.csv", "image_weight_eligible")):
        b = pd.read_csv(OUT / name)
        expected = a2[a2[eligibility]].set_index("L_ID")
        assert set(b.L_ID) == set(expected.index)
        for column in ("split", "split_group_id", "Weight"):
            pd.testing.assert_series_equal(b.set_index("L_ID")[column], expected[column])
        if "Width" in b:
            assert b.Width.gt(0).all() and b.Width.notna().all()
    print(json.dumps({"verification": "PASS", "checks": checks}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify or (OUT / "FREEZE.json").exists():
        verify()
        return
    if OUT.exists() and any(OUT.iterdir()):
        assert (OUT / "BUILDING.json").exists(), "Refuse to overwrite unrelated output"
    OUT.mkdir(parents=True, exist_ok=True)
    write_json("BUILDING.json", {"status": "UNFROZEN_BUILD", "version": 1})
    protected = protected_files()
    print("Verifying raw sources, audit image hashes and JPEG headers...", flush=True)
    multi, single, near, sources = verify_inputs()
    print("Inputs verified; constructing group graphs and fixed split assignments...", flush=True)
    a1, graph1 = prepare_a1(multi, near)
    a2, graph2, reviews, missing, all_phash_components = prepare_a2(single, near)
    map1, score1 = choose_split(a1, "split_group_id", "a1")
    a1 = assign(a1, map1)
    a1["is_source_representative"] = ~a1.duplicated("source_group_id")
    candidates, assignments = {}, []
    for name, col in (("A_batch", "batch_group_id"), ("B_session", "session_group_id"),
                      ("C_batch_OR_session", "connected_group_id"),
                      ("PRIMARY_both_dates_ancestry_origin", "split_group_id")):
        mapping, score = choose_split(a2, col, "a2")
        candidate = assign(a2, mapping, col)
        candidates[name] = dict(all_groups=int(a2[col].nunique()),
            all_sizes={str(k): int(v) for k, v in a2.groupby(col).size().items()},
            active_groups=len(mapping), active_sizes=sorted(a2[a2.primary_split_eligible].groupby(col).size().tolist()),
            objective_score=score, split_counts={s: int(candidate.split.eq(s).sum()) for s in SPLITS},
            batch_overlap=crossing(candidate, "Batch_ID"), session_overlap=crossing(candidate, "EXIF_date"),
            primary_group_overlap=crossing(candidate, "split_group_id"), summary=summary(candidate, "a2", col))
        assignments.extend(dict(strategy=name, group_id=k, split=v) for k, v in mapping.items())
        if col == "split_group_id":
            a2 = candidate
    checks = leakage_checks(a1, a2, near)
    summaries = dict(a1=summary(a1, "a1"), a2=summary(a2, "a2"), checks=checks,
                     a1_objective_score=score1, all_a2_phash_merged_component_count=all_phash_components)
    training_weights = a2.loc[a2.split == "train", "Weight_mg"]
    test_weights = a2.loc[a2.split == "test", "Weight_mg"]
    summaries["a2_test_outside_train_weight_range"] = int(((test_weights < training_weights.min()) |
                                                         (test_weights > training_weights.max())).sum())
    csv("a1_manifest.csv", a1)
    csv("a2_manifest.csv", a2)
    csv("a1_review_queue.csv", a1)
    csv("a1_test_review.csv", a1[a1.is_final_test])
    csv("a2_similarity_review.csv", reviews)
    csv("a2_metadata_without_image.csv", missing)
    csv("a1_group_edges.csv", pd.DataFrame(graph1.edges, columns=["left", "right", "reason"]))
    csv("a2_group_edges.csv", pd.DataFrame(graph2.edges, columns=["left", "right", "reason"]))
    csv("a2_candidate_assignments.csv", pd.DataFrame(assignments))
    base = ["L_ID", "split", "reserved_group_split", "split_group_id", "Weight", "Weight_mg"]
    csv("a2_baseline_length.csv", a2.loc[a2.length_baseline_eligible, base + ["Length"]])
    csv("a2_baseline_length_width.csv", a2.loc[a2.length_width_baseline_eligible, base + ["Length", "Width", "width_unit"]])
    csv("a2_image_table.csv", a2.loc[a2.image_weight_eligible, base + ["archive_path", "archive_member"]])
    csv("source_integrity.csv", sources)
    write_json("protected_integrity.json", protected)
    write_json("grouping_candidates.json", candidates)
    write_json("preparation_summary.json", summaries)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for split in SPLITS:
        subset = a2[a2.split == split]
        axes[0].hist(subset.Weight_mg, bins=np.arange(50, 371, 20), density=True,
                     histtype="step", linewidth=2, label=f"{split} (n={len(subset)})")
        axes[1].hist(subset.Length, bins=np.arange(10, 28, 1), density=True,
                     histtype="step", linewidth=2, label=split)
    for ax, title in zip(axes, ["Measured Weight (mg)", "Measured Length (mm)"]):
        ax.set(xlabel=title, ylabel="Density")
        ax.legend()
    fig.suptitle("A2 frozen grouped splits: descriptive distributions, no model fitted")
    fig.tight_layout()
    fig.savefig(OUT / "a2_split_distributions.png", dpi=160)
    plt.close(fig)
    (OUT / "PREPARATION_REPORT.md").write_text(build_report(a1, a2, summaries, candidates, checks), encoding="utf-8")
    for r in sources.itertuples():
        current = (ROOT / r.path).stat()
        assert (current.st_size, current.st_mtime_ns) == (r.bytes, r.mtime_ns), r.path
    assert protected_files() == protected, "B1 or original audit was modified"
    write_json("BUILDING.json", {"status": "COMPLETE", "version": 1})
    freeze = dict(version=1, created_utc=datetime.now(timezone.utc).isoformat(), seed=SEED,
                  script_sha256=digest(Path(__file__)),
                  environment={"python": platform.python_version(), "pandas": pd.__version__,
                               "numpy": np.__version__, "pillow": Image.__version__, "matplotlib": matplotlib.__version__},
                  outputs={p.name: digest(p) for p in sorted(OUT.iterdir()) if p.is_file()},
                  split_counts={"a1": a1.split.value_counts().to_dict(), "a2": a2.split.value_counts().to_dict()},
                  contract="Read frozen manifests; no reshuffle; fit preprocessing train only; one-time test after selection.")
    with (OUT / "FREEZE.json").open("x", encoding="utf-8") as f:
        json.dump(freeze, f, indent=2, allow_nan=False)
        f.write("\n")
    verify(full_sources=False)
    for p in OUT.iterdir():
        if p.is_file():
            p.chmod(stat.S_IREAD)
    print(json.dumps({"output": str(OUT), "split_counts": freeze["split_counts"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
