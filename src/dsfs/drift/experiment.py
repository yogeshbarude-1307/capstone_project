"""Matched writing-change experiment with observation-time warning lead time."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import numpy as np
import pandas as pd
from dsfs.drift.alerting import evaluate_window
from dsfs.drift.monitors import monitor_feature_numeric
from dsfs.forecast.harness import ForecastConfig, paired_origins, run_arm
from dsfs.extraction.pipeline import run_extraction
from dsfs.features.service import DemandFeatureService
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.generator import generate_dataset

def _feature_windows(features, start_date):
    frame=features.copy()
    frame["week"]=(pd.to_datetime(frame.forecast_cutoff,utc=True)-pd.Timestamp(start_date,tz="UTC")).dt.days//7
    frame["pct_present"]=frame.signed_pct_change.notna().astype(float)
    return frame

def alert_time(features, start_date, injection_week):
    frame=_feature_windows(features,start_date)
    reference=frame[(frame.week>=injection_week-8)&(frame.week<injection_week)]
    streak=0;first=None;windows=[]
    for week,group in frame[frame.week>=injection_week].groupby("week"):
        probe=monitor_feature_numeric("pct_present",reference,group)
        qualifies=evaluate_window(probe,alpha=.05,min_effect_size=.3)
        streak=streak+1 if qualifies else 0
        windows.append({"week":int(week),**asdict(probe),"qualifies":qualifies})
        if streak>=2 and first is None:first=int(week)
    return first,windows

def degradation_time(control,shifted,*,injection_week,horizon_weeks=4):
    left,right=paired_origins(control,shifted)
    end=max((o.horizon_week_index+1 for o in left),default=injection_week)
    streak=0;first=None;windows=[]
    for now in range(injection_week,end+1):
        # Fully mature origins: every target week in their H-week forecast ended.
        pairs=[(a,b) for a,b in zip(left,right)
               if now-horizon_weeks-3<=a.origin_week_index<=now-horizon_weeks]
        if not pairs:continue
        a=float(np.mean([abs(o.actual-o.predicted) for o,_ in pairs]))
        b=float(np.mean([abs(o.actual-o.predicted) for _,o in pairs]))
        worsening=(b-a)/a if a>0 else (float("inf") if b>0 else 0)
        qualifies=worsening>.1
        streak=streak+1 if qualifies else 0
        windows.append({"confirmed_at_week":now,"control_mae":a,"shifted_mae":b,
                        "relative_worsening":worsening if np.isfinite(worsening) else None,"qualifies":qualifies})
        if streak>=2 and first is None:first=now
    return first,windows

def matched_report(control_features,shifted_features,control_result,shifted_result,start_date,injection_week,null_features):
    alert,feature_windows=alert_time(shifted_features,start_date,injection_week)
    degradation,performance_windows=degradation_time(control_result,shifted_result,injection_week=injection_week,
                                                     horizon_weeks=control_result.config.horizon_weeks)
    null_alerts=[alert_time(f,start_date,injection_week)[0] is not None for f in null_features]
    return {"scenario":"writing_change","monitor_layer":"features","monitor_metric":"percentage_presence",
            "detected":alert is not None,"alert_week":alert,"degradation_week":degradation,
            "lead_time_weeks":degradation-alert if alert is not None and degradation is not None else None,
            "detection_latency_weeks":alert-injection_week if alert is not None else None,
            "calibrated_false_alert_rate":sum(null_alerts)/len(null_alerts) if null_alerts else None,
            "n_no_drift_runs":len(null_alerts),"no_drift_alerts":null_alerts,
            "feature_windows":feature_windows,"performance_windows":performance_windows,
            "injection_week":injection_week,"maturity":"entire four-week forecast must have realized",
            "degradation_threshold":.1,"required_consecutive":2}

def _service(dataset,notes,run_id,config):
    extraction=run_extraction(notes,set(dataset.entities),extraction_run_id=run_id)
    return DemandFeatureService(dataset.d0_demand,extraction.accepted,{n.source_id:n for n in notes},run_id,forecast_config=config)

def run_writing_change_experiment(*,n_entities=40,n_weeks=104,seed=901,injection_week=60,n_calibration_runs=10):
    config=GeneratorConfig(seed=seed,n_entities=n_entities,n_weeks=n_weeks,events_per_entity_per_year=8,
        true_demand_delta_frac_range=(.2,.6),demand_noise_frac=.02,realized_magnitude_noise_frac=.05,
        stated_magnitude_reveal_prob={c:1.0 for c in ("ASSERTED","EXPECTED","LIKELY","POSSIBLE","UNKNOWN")})
    fc=ForecastConfig(train_weeks=52,horizon_weeks=4,min_origins=1)
    dataset=generate_dataset(config)
    altered=[]
    for note in dataset.d1_notes:
        if (note.authored_at.date()-config.start_date).days//7>=injection_week:
            text=note.raw_text.replace("increase","expand").replace("decrease","reduce").replace("roughly","approximately")
            altered.append(note.model_copy(update={"source_id":note.source_id+"-writing","source_revision":"writing-v1",
                "raw_text":text,"content_hash":"sha256:"+hashlib.sha256(text.encode()).hexdigest()}))
        else:altered.append(note)
    cutoffs=[datetime.combine(config.start_date,datetime.min.time(),tzinfo=timezone.utc)+timedelta(weeks=w) for w in range(n_weeks)]
    pairs=[(e,c) for c in cutoffs for e in dataset.entities]
    print("Matched writing-change features and forecasts",flush=True)
    control_service=_service(dataset,dataset.d1_notes,"drift-control",fc)
    shifted_service=_service(dataset,altered,"drift-writing",fc)
    control=control_service.historical(pairs)
    shifted=shifted_service.historical(pairs)
    a=run_arm(dataset.d0_demand,fc,"C",control)
    b=run_arm(dataset.d0_demand,fc,"C",shifted)
    null=[control]
    for i in range(1,n_calibration_runs):
        print(f"No-drift calibration run {i+1}/{n_calibration_runs}",flush=True)
        null_dataset=generate_dataset(config.model_copy(update={"seed":seed+i}))
        null.append(_service(null_dataset,null_dataset.d1_notes,f"null-{i}",fc).historical(pairs))
    report=matched_report(control,shifted,a,b,config.start_date,injection_week,null)
    report["generator_config"]=config.model_dump(mode="json")
    report["forecast_config"]=asdict(fc)
    report["paired_demand_identical"]=True
    return report,{"control_notes":[n.model_dump(mode="json") for n in dataset.d1_notes],
                   "shifted_notes":[n.model_dump(mode="json") for n in altered],
                   "control_origins":[asdict(o) for o in a.origins],"shifted_origins":[asdict(o) for o in b.origins],
                   "demand":dataset.d0_demand.to_dict("records")}
