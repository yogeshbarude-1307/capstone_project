"""Frozen multi-seed study: development first, then immutable evaluation."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
from dsfs.config import get_settings
from dsfs.evaluation.report import code_snapshot
from dsfs.orchestrate import run_e2e
from dsfs.runs import atomic_json
from dsfs.forecast.harness import ForecastConfig
from dataclasses import asdict

def study_ci(manifests, arm, *, n_resamples=1000):
    strata=[]
    for manifest in manifests:
        rows=json.loads((Path(manifest["snapshot_root"])/"reports/forecast/origins.json").read_text())
        def index(label):
            out={(o["entity_key"],o["origin_week_index"],o["horizon_step"]):o for o in rows[label]}
            if len(out)!=len(rows[label]):raise ValueError("Duplicate study keys")
            return out
        base, enhanced=index("A"),index(arm)
        if base.keys()!=enhanced.keys():raise ValueError("Unpaired study outcomes")
        groups={}
        for key,a in base.items():
            b=enhanced[key]
            if a["actual"] != b["actual"]:raise ValueError("Different paired actuals")
            scale=a["mase_scale"]
            if scale and scale>0:
                groups.setdefault(key[0],[]).append((abs(a["actual"]-a["predicted"])/scale,
                                                    abs(b["actual"]-b["predicted"])/scale))
        strata.append([np.asarray(v) for v in groups.values()])
    if not all(strata):return {"point":None,"ci_low":None,"ci_high":None}
    def lift(arrays):
        means=np.concatenate(arrays).mean(axis=0)
        return float((means[0]-means[1])/means[0]) if means[0]>0 else 0.
    point=lift([a for group in strata for a in group]);rng=np.random.default_rng(42)
    draws=[lift([group[i] for group in strata for i in rng.integers(0,len(group),len(group))]) for _ in range(n_resamples)]
    lo,hi=np.percentile(draws,[2.5,97.5])
    return {"metric":"MASE","point":point,"ci_low":float(lo),"ci_high":float(hi),
            "n_seeds":len(strata),"method":"paired account trajectories resampled within each seed","resamples":n_resamples}

def run_study(settings, *, writing_drift=True, n_entities=40):
    config=asdict(ForecastConfig())
    development=[]
    for seed in (1,2,3):
        print(f"Development seed {seed}",flush=True)
        development.append(run_e2e(settings,{"generator":{"seed":seed,"n_entities":n_entities},"forecast":config,"mechanics_check":seed==1}))
    freeze={"code_sha256":code_snapshot(),"forecast_config":config,"feature_version":"demand-v1",
            "development_seeds":[1,2,3],"evaluation_seeds":[101,102,103,104,105],
            "n_entities":n_entities,"n_weeks":104,"model_policy":"fixed Ridge alpha=1, training-only standardization",
            "frozen_at":datetime.now(timezone.utc).isoformat()}
    study_root=settings.reports_dir/"studies"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    atomic_json(study_root/"freeze.json",freeze)
    evaluation=[];ablations=[]
    for seed in freeze["evaluation_seeds"]:
        if code_snapshot()!=freeze["code_sha256"]:raise RuntimeError("Code changed after study freeze; evaluation aborted")
        print(f"Frozen evaluation seed {seed}",flush=True)
        cfg={"generator":{"seed":seed,"n_entities":n_entities},"forecast":config,"prepare_review":seed==101}
        if seed==101 and writing_drift:cfg["writing_drift"]={}
        evaluation.append(run_e2e(settings,cfg))
        print(f"Ten-account ablations seed {seed}",flush=True)
        ablations.append(run_e2e(settings,{"generator":{"seed":seed,"n_entities":10},"forecast":{**config,"ablation":"full"}}))
    lift={arm:study_ci(evaluation,arm) for arm in ("B","C","D")}
    oracle_positive=lift["B"]["ci_low"] is not None and lift["B"]["ci_low"]>0
    headline = {}
    for arm in ("A","B","C","D"):
        rows=[m["steps"]["forecast"][arm] for m in evaluation]
        total=sum(r["n_origins"] for r in rows)
        valid=sum(r["n_origins"]-r["mase_unavailable_count"] for r in rows)
        headline[arm]={"mae":sum(r["mae"]*r["n_origins"] for r in rows)/total,
            "bias":sum(r["bias"]*r["n_origins"] for r in rows)/total,
            "mase":sum((r["mase"] or 0)*(r["n_origins"]-r["mase_unavailable_count"]) for r in rows)/valid if valid else None,
            "n_origins":total,"mase_unavailable_count":total-valid}
    summary={"headline_metrics":headline,"freeze":freeze,"development_runs":[m["run_id"] for m in development],
        "evaluation_runs":[m["run_id"] for m in evaluation],"ablation_runs":[m["run_id"] for m in ablations],
        "lift":lift,"oracle_positive_gate":oracle_positive,"drift":evaluation[0]["steps"].get("drift"),
        "independent_review":evaluation[0]["steps"].get("independent_review"),
        "recommendation":"Evaluate extraction retention" if oracle_positive else "Revisit representation before expanding extraction technology"}
    atomic_json(study_root/"summary.json",summary)
    atomic_json(settings.reports_dir/"study-summary.json",summary)
    lines=["# Frozen customer-demand study","",f"Oracle positive gate: {oracle_positive}","",
           "| Arm | MASE lift | 95% paired trajectory CI |","|---|---:|---:|"]
    for arm,result in lift.items():
        if result["point"] is None:
            lines.append(f"| {arm} | unavailable | unavailable |")
            continue
        lines.append(f"| {arm} | {result['point']:+.2%} | [{result['ci_low']:+.2%}, {result['ci_high']:+.2%}] |")
    lines.extend(["",summary["recommendation"],"","Independent review: pending real reviewer labels.","",
        "Synthetic results do not establish signal prevalence or predictive value in real company notes."])
    (study_root/"findings.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Study evidence: {study_root}",flush=True)
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-writing-drift",action="store_true",help="Diagnostic study only; omits brief's drift demonstration")
    args=parser.parse_args()
    run_study(get_settings(),writing_drift=not args.skip_writing_drift)

if __name__=="__main__":main()
