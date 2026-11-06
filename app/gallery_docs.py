"""Gallery distribution guidance generated from the same source as the runtime."""
def write_gallery_docs(stage,bundle,write):
    docs=stage/"docs"
    write(docs/"GALLERY_INTEGRATION_GUIDE.md", """# Galeri Pengujian AI BSF

Existing Smart BSF screen: `/bsf-intelligence#gallery`. The gallery is a new tab in the same Fiscycle shell, not another application. All 46 frozen A1 test photographs and all 178 frozen A2 individual test images are registered; two existing development-train fixtures remain separate. Search by filename/ID, pagination, full-resolution preview, previous/next, real AI action, rejection/failure states, per-instance distribution and DSS are included. All user-facing controls are Bahasa Indonesia.

Default routes under configurable FISCYCLE_BSF_API_PREFIX:
- GET /gallery/datasets
- GET /gallery/images?dataset_id=a1-test|a2-test&q=...&status=...&page=1&page_size=20
- GET /gallery/images/{opaque_id}
- GET /gallery/images/{id}/content?variant=original|thumbnail|overlay|processed
- POST /gallery/images/{id}/analyze with JSON {"force":false}; valid cached frozen-model results are reused and labelled cache_hit
- GET /gallery/images/{id}/results; optional cache_key selects a particular owned/public research result
- GET /gallery/datasets/{dataset_id}/metrics
- POST /gallery/jobs {"dataset_id":"a1-test","force":false}; optional image_ids for controlled integration tests, omitted to process the whole collection
- GET /gallery/jobs and /gallery/jobs/{id}
- POST /gallery/jobs/{id}/resume?retry_failed=true

Never submit filesystem paths. Image IDs are server-issued hashes; source and bundle content is accessed through containment checks. Parent gateway authentication and tenant isolation cover jobs, results and private history. Public frozen-research baseline predictions are deliberately reusable across tenants; user observations and user-specific review records are not shared.

For optional manual A2 ROI review, POST /analyze with `review` containing roi_bbox [x0,y0,x1,y1], whole_larva_visible=true, no_written_markings=true, reviewer=name. Coordinates are original source pixels. Do not fabricate a human review. Such later analyses are distinct from the immutable initial final-evaluation record. Automatic A2 proposal is the pre-existing ranked ROI v2 algorithm with unchanged parameters; its selected native ROI enters the exact v3 2048->224 transform. Automatic-ROI errors are descriptive; they do not certify reviewed-ROI performance. A1->A2 is experimental cross-model inference, not paired end-to-end ground-truth validation.
""")
    write(docs/"GALLERY_DEPLOYMENT.md",f"""# Complete optional gallery data

The main application archive includes the complete 226-image registry (224 test + 2 development), all 226 thumbnails, original measured references where available, attribution, pre-registered protocol, final-evaluation receipt, baseline predictions, and the two existing full-resolution development fixtures.

All **224** authorized full-resolution test images and **46** original A1 annotation files are in the separate optional `{bundle['filename']}` ({bundle['bytes']} bytes, SHA-256 `{bundle['sha256']}`). No test image is omitted from this complete data bundle. These 224 originals are excluded from the MAIN ZIP solely to keep the app archive small. The source dataset is CC BY 4.0: credit Quentin Geissmann, Zenodo v1 DOI 10.5281/zenodo.13359376; attribution is also inside the bundle. Source labels and images remain unchanged.

After extracting FISCYCLE_DEV_HANDOVER.zip, copy FISCYCLE_GALLERY_DATA.zip into FISCYCLE_DEV_HANDOVER/service/ and leave the DATA ZIP compressed. Alternatively configure FISCYCLE_BSF_GALLERY_DATA as the server-controlled absolute path to that approved ZIP. The loader verifies the bundle checksum and each image hash; it never accepts a client path. Do not expose dataset directories as unrestricted static files.

Without the optional bundle, all gallery metadata/thumbnails and recorded baseline outcomes remain browsable, but full-resolution test content and fresh test inference are unavailable; the API reports runtime_available=0 for both test collections and returns 503 for missing originals. This is metadata-only gallery availability, not a fully mounted portable gallery. With the bundle, runtime_available is 46 and 178 respectively. All original test files are read from the approved bundle, with no research-folder dependency.

Run a single uvicorn worker for this local SQLite job implementation. One inference worker processes one image at a time; batch A1->A2 retains the existing maximum64 ROI policy. Jobs do not start merely by opening the gallery. Progress, completed/failed/rejected/pending items and results persist in bsf_gallery.sqlite3 alongside the existing history DB. Configure FISCYCLE_BSF_GALLERY_DB to move it. On a dead worker, active items become pending and the job becomes INTERRUPTED; resume explicitly through the API/UI. Retry failed items without erasing their attempt counts. A changed configuration fingerprint requires a new job. Cache keys include original image hash, checkpoint hashes, exact preprocessing, ROI adapter/configuration, pipeline source hash, device/library versions and optional source ROI review. A failed computation is retryable; unchanged successful results are reused.

The final evaluation was expressly authorized by the user before release. Both displayed final-test sets are no longer blind. Do not retrain, tune thresholds, choose checkpoints or adjust ROI filtering based on gallery results. A1 annotations are incomplete: segmentation accuracy remains unavailable. A2 has only one primary test group; automatic-ROI metrics are not a certified reviewed-ROI benchmark or field validation. Any later software correction must retain the original evaluation receipt and document cache invalidation/affected results.

Smoke: python verify_package.py from service/ (full gallery checks require mounted data ZIP). Optional pytest suite: python -m pytest app/tests/test_gallery_portable.py -q. Fresh dependency installation and Docker must be tested separately; no clean-install success is implied.
""")
    demo=docs/"COMPETITION_DEMO_GUIDE.md"
    write(demo,demo.read_text(encoding="utf-8")+"\n\nGallery: open /bsf-intelligence#gallery. Select Dataset Pengujian A1 to browse all46; select any photo and Jalankan AI to view source, segmentation, experimental per-instance weights, analyzed/rejected coverage, distribution and DSS. Use the separate Dataset Pengujian A2 collection for all178 individual images and measured-vs-predicted descriptive errors. Development fixtures are labelled Bukan Test. Analisis Semua Foto creates a persistent background job for the entire selected collection, not just the current page. Hasil cache is explicit; check Hitung ulang only when a fresh inference attempt is needed. Failed/rejected images remain listed and can be retried. Both original test sets have been evaluated and released and must not be called blind.\n")
    readme=stage/"README.md"
    write(readme,readme.read_text(encoding="utf-8")+"\n\nFull BSF gallery: additionally place FISCYCLE_GALLERY_DATA.zip inside service/ (keep compressed), or configure FISCYCLE_BSF_GALLERY_DATA. It contains ALL46 A1 +178 A2 original test files. The main ZIP contains their complete metadata and thumbnails; full-size test inference needs the data bundle. See docs/GALLERY_DEPLOYMENT.md. Open /bsf-intelligence#gallery.\n")
    env=stage/"service/.env.example"
    write(env,env.read_text(encoding="utf-8")+"# Optional complete 224-test-image gallery bundle\n# FISCYCLE_BSF_GALLERY_DATA=./FISCYCLE_GALLERY_DATA.zip\n# FISCYCLE_BSF_GALLERY_DB=./app/state/bsf_gallery.sqlite3\n")
