"""Real four-flow checks reusable in source tests and relocated releases."""
import math


def run_integrated_checks(client, check):
    from app.core.config import BSF_API_PREFIX
    check("integrated ecosystem frontend",client.get("/ecosystem").status_code==200)
    raw = client.get("/api/v1/demo/photo")
    check("development-only photo exemplar",raw.status_code==200 and raw.headers.get("x-data-provenance")=="PUBLIC_RESEARCH_TRAIN_FIXTURE")
    photo = client.post(BSF_API_PREFIX+"/analyze-photo",content=raw.content,headers={"Content-Type":"image/jpeg"})
    check("Flow A real one-photo A1 A2 inference",photo.status_code==200)
    p=photo.json(); summary=p["summary"]
    check("Flow A eligible ROI numeric predictions",summary["analyzed"]>0 and summary["detected"]==summary["analyzed"]+summary["rejected"])
    weights=[i["predicted_weight_mg"] for i in p["instances"] if i["predicted_weight_mg"] is not None]
    check("Flow A visible mass count and exact geometry",math.isclose(sum(weights),summary["analyzed_visible_mass_mg"]) and
          all(i["geometry"]["scale_factor"]==224/2048 for i in p["instances"] if i["geometry"]))
    check("Flow A photo-specific DSS and domain abstention",p["decision_support"]["status"]=="ABSTAIN_OPERATIONAL" and p["domain_status"]=="EXPERIMENTAL_UNVERIFIED_IMAGING_SCALE")
    trajectory=client.get(BSF_API_PREFIX+"/replay/trajectories").json()["trajectories"][0]["trajectory_id"]
    growth=client.get(f"{BSF_API_PREFIX}/replay/{trajectory}?revealed=6").json()
    dss=client.post(BSF_API_PREFIX+"/decision-support",json={"data_mode":"HISTORICAL_RESEARCH","trajectory_id":trajectory,"revealed":6})
    check("Flow B real B1 replay and growth DSS",growth["forecast"]["result"]["predicted_next_weight_mg"] is not None and dss.status_code==200 and dss.json()["triggered_rule_ids"])
    check("Flow B unmatched timing never scored",all(c["error_mg"] is None for c in growth["comparisons"] if not c["time_aligned"]))
    periods=client.get("/water-quality/replay/periods").json()["periods"]
    check("Water eligible recorded segment available",bool(periods))
    period=periods[0]
    created=client.post("/water-quality/replay/sessions",json={k:period[k] for k in ("start","end","pond_id")})
    check("Flow C replay creation with warmup",created.status_code==201 and created.json()["warmup"]["observations"]>0)
    ident=created.json()["session_id"]
    replay=client.post(f"/water-quality/replay/sessions/{ident}/advance?steps=55").json()
    check("Flow C 9 forecasts and matched persistence evaluation",len(replay["metrics"]["rows"])==9 and all(r["matched"]>0 and r["persistence_same_pairs"]["mae"] is not None for r in replay["metrics"]["rows"]))
    check("Flow C per-parameter QA and traceable Water C",len(replay["latest_result"]["data_quality"]["parameters"])==3 and len(replay["latest_result"]["decision_support"]["traces"])==6)
    saved=client.post(f"/water-quality/replay/sessions/{ident}/snapshot").json()
    scenario=client.post("/water-quality/scenario",json={"history_id":saved["history_id"],"input_state":"STALE"}).json()
    check("Flow D rule-only scenario changes eligibility",scenario["provenance"]=="SIMULATED_RULE_ONLY" and not scenario["ml_recomputed"] and scenario["after"]["data_quality"]["status"]=="STALE" and scenario["after"]["decision_support"]["insights"][0]["rule_id"]=="C01_INPUT_QA")
    stored=client.get(f"/water-quality/history/{saved['history_id']}").json()
    check("Water scenario never changes original record",stored["result"]["data_quality"]["status"]=="VALID")
    check("request tracing",bool(client.get("/health").headers.get("x-request-id")))
    return {"photo":summary,"water_metrics":replay["metrics"],"growth_comparisons":growth["comparisons"]}
