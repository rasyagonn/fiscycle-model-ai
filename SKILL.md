# Fiscycle repository routing guide

Read `AGENTS.md` first. The developer runtime is **`ai-service/`** (local RC2),
with startup in `ai-service/README.md`, API integration in `docs/INTEGRATION.md`,
and actual test status in `docs/VERIFICATION.md`.

- `ai-service/`: standalone FastAPI, approved model bundles, public B1 replay and 16 demo photos.
- `app/`: preserved legacy research/dashboard implementation; not the new runtime entry point.
- `.agents/skills/fiscycle-water-ai/`: frozen Water research/data/model provenance.
- `.agents/skills/fiscycle-bsf-ai/`: frozen BSF research/data/model provenance.
- `docs/archive/v2.1.0/`: historical reports and old handover contract.
- `fiscycle-ai-service/`: ignored local HF/release tooling workspace; do not push it wholesale.

Use a domain skill when doing new scientific analysis, training or evaluation, rather
than treating a runtime packaging change as new research. Never modify frozen data,
models or A2 v3 preprocessing for handover. Do not create root `models/` or `data/`.

Preserve independent domain readiness: failed BSF loading must not disable Water and
vice versa. Water remains historical unless live integration is validated. BSF outputs
retain `RESEARCH_PROTOTYPE`, `NOT_FIELD_VALIDATED` and explicit provenance.
