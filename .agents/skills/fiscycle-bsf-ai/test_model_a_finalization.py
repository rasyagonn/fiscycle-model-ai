"""Integrity and acceptance-gate tests. Synthetic decisions never enter production outputs."""
import copy
import json
import unittest
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from PIL import Image
import finalize_model_a as f
import a2_preprocessing_v2 as roi


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.entry={"id":"SYNTHETIC_ONLY","proposal_hash":"proposal","policy_hash":"policy","source_sha256":"source",
                    "split":"train","track":"A1","hard_hold":False,"checks_required":f.CHECKS["A1"],
                    "source_polygons":[{"source_line":1,"source_class":1,"target_class":0,"points":[[.1,.1],[.4,.1],[.4,.4],[.1,.4]]}]}
        self.decision={**{k:self.entry[k] for k in ["id","proposal_hash","policy_hash","source_sha256","split"]},
                       "reviewer_kind":"human","reviewer":"SYNTHETIC TEST FIXTURE - NOT AN APPROVAL",
                       "reviewed_at":"2026-11-05T12:00:00+07:00","decision":"approve",
                       "checks":{k:True for k in f.CHECKS["A1"]},"polygons":copy.deepcopy(self.entry["source_polygons"])}

    def test_synthetic_valid_decision_in_memory_only(self):
        f.validate_decision(self.decision,self.entry)

    def test_binding_tampering_rejected(self):
        for key in ["id","proposal_hash","policy_hash","source_sha256","split"]:
            d=copy.deepcopy(self.decision);d[key]="changed"
            with self.assertRaises(ValueError): f.validate_decision(d,self.entry)

    def test_missing_human_confirmation_and_hard_hold(self):
        for key,value in [("reviewer",""),("reviewer_kind","agent"),("reviewed_at","2026-11-05T12:00:00"),("checks",{})]:
            d=copy.deepcopy(self.decision);d[key]=value
            with self.assertRaises(ValueError): f.validate_decision(d,self.entry)
        self.entry["hard_hold"]=True
        with self.assertRaises(ValueError): f.validate_decision(self.decision,self.entry)

    def test_bad_geometry_rejected(self):
        for points in [[[.1,.1],[.101,.1],[.101,.101]],[[.1,.1],[.4,.4],[.1,.4],[.4,.1]],[[.1,.1],[1.1,.1],[.4,.4]],[[.1,.1],[.1,.1],[.4,.4],[.1,.4]]]:
            p=copy.deepcopy(self.entry["source_polygons"]);p[0]["points"]=points
            with self.assertRaises(ValueError): f.validate_polygons(p,enforce_visibility=True)
        with self.assertRaises(ValueError): f.validate_polygons(self.entry["source_polygons"]*2)

    def test_changed_crop_rejected(self):
        e={**self.entry,"track":"A2","crop_sha256":"crop","crop_bbox":[10,20,100,200]}
        d={**self.decision,"crop_sha256":"crop","crop_bbox":[10,20,100,201]}
        with self.assertRaises(ValueError): f.validate_decision(d,e)

    def test_no_object_abstains_and_test_disallowed(self):
        result=roi.propose_roi(Image.new("RGB",(640,480),"white"))
        self.assertFalse(result["roi_found"])
        self.assertFalse(result["training_approved"])
        for split in ["test","quarantine","excluded"]:
            with self.assertRaises(ValueError): roi.require_development_split(split)

    def test_actual_mapping_preserves_all_instances_and_geometry(self):
        manifest=pd.read_csv(f.OUT/"a1_working_manifest.csv")
        count=0
        for r in manifest.itertuples():
            source=f.parse_labels(f.ROOT/r.label_path);mapped=f.parse_labels(f.OUT/r.mapped_label_path)
            self.assertEqual(len(source),len(mapped));count+=len(source)
            for a,b in zip(source,mapped):
                self.assertEqual(a["points"],b["points"]);self.assertEqual(b["source_class"],0)
        self.assertEqual(count,6612)

    def test_membership_and_no_accidental_approval(self):
        a=pd.read_csv(f.OUT/"a1_working_manifest.csv");old=pd.read_csv(f.FROZEN/"a1_manifest.csv")
        pd.testing.assert_frame_equal(a[["image_path","split","reserved_group_split"]],old[["image_path","split","reserved_group_split"]])
        b=pd.read_csv(f.OUT/"a2_working_manifest.csv");old=pd.read_csv(f.FROZEN/"a2_manifest.csv")
        expected=old[old.split.isin(["train","validation"])].set_index("L_ID")
        self.assertEqual(set(b.L_ID),set(expected.index));self.assertEqual(len(b),1114)
        self.assertFalse(b.human_approved.any());self.assertFalse(a.training_eligible.any())
        for r in b.itertuples(): self.assertEqual(r.split,expected.loc[r.L_ID,"split"])

    def test_review_has_no_weight_predictors_and_known_failures_held(self):
        items=f.read_json(f.OUT/"a2_working_review_items.json")
        for e in items:
            self.assertFalse(set(e)&{"Weight","Length","Width","Sex","Batch_ID","measured_weight_g"})
            if e["L_ID"] in [18,107,253,773,1460]: self.assertTrue(e["hard_hold"])

    def test_import_freezes_only_synthetic_accepted_fixture_in_temporary_workspace(self):
        with tempfile.TemporaryDirectory(prefix="fiscycle-synthetic-import-") as directory:
            root=Path(directory);out=root/"working";frozen=root/"frozen"
            out.mkdir();frozen.mkdir();(root/"data").mkdir()
            Image.new("RGB",(640,640),"white").save(root/"source.png")
            (root/"source.txt").write_text("1 .1 .1 .4 .1 .4 .4 .1 .4\n")
            e={**self.entry,"image_id":"SYNTHETIC_ONLY","source_path":"source.png","source_label_path":"source.txt",
               "source_sha256":f.sha(root/"source.png"),"source_label_sha256":f.sha(root/"source.txt"),
               "reserved_group_split":"train","split_group_id":"SYNTHETIC_GROUP","issues":"SYNTHETIC FIXTURE ONLY"}
            f.write_json(out/"review_items.json",[e])
            for name in ["annotation_policy.json","a2_roi_config.json","PACKAGE_RECEIPT.json"]: f.write_json(out/name,{"fixture":True})
            f.write_json(frozen/"FREEZE.json",{"fixture":True})
            pd.DataFrame([dict(L_ID=1,Weight=.1,split="train",Batch_ID="SYNTHETIC")]).to_csv(frozen/"a2_manifest.csv",index=False)
            with zipfile.ZipFile(root/"data/Single Larvae data.zip","w"): pass
            d={**self.decision,"source_sha256":e["source_sha256"]}
            decision_path=root/"synthetic_decision.json"
            f.write_json(decision_path,{"package_hash":f.sha(out/"review_items.json"),"decisions":[d]})
            with patch.object(f,"ROOT",root),patch.object(f,"OUT",out),patch.object(f,"FROZEN",frozen),patch.object(f,"verify_package",return_value={}):
                f.import_reviews(decision_path)
                snapshots=list((out/"review_snapshots").iterdir());self.assertEqual(len(snapshots),1)
                snapshot=snapshots[0];receipt=f.read_json(snapshot/"FREEZE.json")
                self.assertEqual(receipt["accepted"],1)
                for name,h in receipt["files"].items(): self.assertEqual(f.sha(snapshot/name),h)
                accepted=pd.read_csv(snapshot/"approved_working_manifest.csv")
                self.assertEqual(accepted.iloc[0].id,"SYNTHETIC_ONLY")
                self.assertTrue(accepted.iloc[0].training_eligible)
                self.assertFalse(accepted.iloc[0].metric_eligible)
                self.assertEqual((root/"source.txt").read_text(),"1 .1 .1 .4 .1 .4 .4 .1 .4\n")
                with self.assertRaises(FileExistsError): f.import_reviews(decision_path)


if __name__=="__main__": unittest.main(verbosity=2)
