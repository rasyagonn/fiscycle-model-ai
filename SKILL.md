# Fiscycle model repository routing guide

This repository contains independent model domains and one shared API application. Read `AGENTS.md` first, then use only the domain guide relevant to the task:

- Water Quality: `.agents/skills/fiscycle-water-ai/SKILL.md`
- BSF Model B1: `.agents/skills/fiscycle-bsf-ai/SKILL.md`
- Shared API: `app/README.md` and `app/STRUCTURE.md`

Keep raw data, notebooks, evaluation outputs, inference modules, and model artifacts inside the owning domain folder. The shared API may load trusted runtime bundles but must not copy training data or claim new model validation. Do not create a root `models/`, `data/`, or second API tree.

For combined API work, preserve independent startup and health state per domain. A failed BSF load must not disable Water Quality, and vice versa. Water Quality remains historical replay unless a live integration is explicitly validated. BSF responses must always disclose `RESEARCH_PROTOTYPE`, `NOT_FIELD_VALIDATED`, and an explicit input provenance.
