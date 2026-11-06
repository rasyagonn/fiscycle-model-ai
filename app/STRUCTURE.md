# Struktur aplikasi sumber

```text
app/
  main.py                         satu FastAPI dan lifecycle
  run.py                          python -m app.run
  core/
    config.py                     path/prefix/batas request
    http.py                       JSON finite
    security.py                   gateway, tenant, request ID, body stream
    artifacts.py                  hash runtime
  routers/
    health.py
    water_quality.py
    bsf.py                        B1 legacy
    bsf_intelligence.py
    integration.py                demo, Water scenario/history, comparison
  schemas/
    water_quality.py
    bsf.py
  services/
    water_core.py                 port QA dan inference kausal
    water_quality.py              replay/seed/history
    water_insights.py             enam aturan dan paired metrics
    bsf.py                        adapter B1 frozen
    bsf_models.py                 A1/A2 dan exact preprocessing v3
    bsf_photo.py                  ROI, batch A2, agregasi, DSS foto
    bsf_intelligence.py           replay dan SQLite tenant-aware
    bsf_decisions.py              DSS pertumbuhan
  static/
    dashboard.html                Water existing
    bsf.html                      BSF existing + foto gabungan
    ecosystem.html                empat demo dan konteks sirkular
    integration.js
    integration.css
    gateway.js
    manifest.webmanifest
    sw.js
    fiscycle-icon.svg
  tests/
    test_api.py
    test_bsf_intelligence.py
    test_integrated.py
    browser_smoke.py
  runtime_artifacts.json          lock hash
  integration_checks.py          smoke empat alur
  build_handover.py
  handover_extension.py
  handover_verify.py
  handover_checksums.py
  verify_release.py
  requirements.txt                CPU lock
  README.md
  STRUCTURE.md
  state/                          privat; tidak masuk paket
```

Package Python juga mempunyai `__init__.py`. `release_evidence.json` merupakan hasil verifikasi. Research tetap pada folder domain di `.agents/skills/`. Builder menyalin runtime terpilih ke `FISCYCLE_DEV_HANDOVER/service/water_assets` dan `bsf_assets`. Struktur lengkap distribusi terdapat di `FISCYCLE_DEV_HANDOVER_MANIFEST.md` tingkat root.

## Tambahan galeri BSF

- routers/bsf_gallery.py: adapter galeri, akses konten melalui ID, hasil dan job.
- services/bsf_gallery.py: registry, containment, cache versi, SQLite job/result dan satu worker.
- services/bsf_gallery_roi.py: salinan inferensi dari ranked ROI v2 yang sudah ada, parameter tetap.
- static/gallery.html, gallery.js, gallery.css: tab dalam dashboard BSF yang sudah ada.
- gallery_prepare.py: inventaris seluruh test dari manifest beku, verifikasi file dan pra-registrasi.
- gallery_evaluate.py: evaluasi final yang disahkan, penyimpanan hasil, lalu pelepasan koleksi.
- gallery_bundle.py: bundle opsional seluruh 224 test original dan ekspor registry/thumbnail.
- gallery_docs.py: panduan galeri yang dihasilkan builder.
- gallery_checks.py: pemeriksaan galeri portabel pada model/hasil sebenarnya.
- tests/test_bsf_gallery.py, tests/test_gallery_portable.py: discovery, akses, job, cache, restart dan integrasi.

Hasil ilmiah baru berada di .agents/skills/fiscycle-bsf-ai/hasil/model_a_gallery_v1/. Checkpoint, source image, source annotation dan split beku tidak diedit. Antrean aplikasi menggunakan bsf_gallery.sqlite3; SQLite evaluasi final berada pada folder hasil tersebut dan tidak masuk paket. Main ZIP memuat semua metadata/thumbnail; FISCYCLE_GALLERY_DATA.zip memuat semua test original sebagai bundle data terpisah.

