"""Small planted demand scenario, verified before the broader noisy study."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import random
import numpy as np
import pandas as pd
from dsfs.models.source_evidence import SourceEvidence, SourceType
from dsfs.models.signal_record import SignalType, Direction, BusinessCertainty, Conditionality
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.latent import HiddenState
from dsfs.synth.demand import realize_demand
from dsfs.synth.notes import NoteGroundTruth
from dsfs.forecast.harness import ForecastConfig, run_arm, evaluate_arm, paired_origins
from dsfs.forecast.oracle_service import oracle_service
from dsfs.features.service import DemandFeatureService
from dsfs.extraction.pipeline import run_extraction

def run_mechanics_scenario():
    n=140; rng=np.random.default_rng(8)
    pct=np.where(rng.random(n)<.3,rng.uniform(20,60,n),0)
    config=GeneratorConfig(n_entities=1,n_weeks=n,weekly_baseline_level_range=(100,100),
        weekly_trend_frac_range=(0,0),seasonal_amplitude_frac=0,demand_noise_frac=0,
        realized_magnitude_noise_frac=0,materialization_prob_by_certainty={"ASSERTED":1})
    dates=[datetime(2023,1,2,tzinfo=timezone.utc)+timedelta(weeks=w) for w in range(n)]
    sources={};truth=[];hidden=[]
    for w,p in enumerate(pct):
        if not p:continue
        start=dates[w];end=start+timedelta(weeks=1);sid=f"plant-{w}";ref=f"EVT-{w}"
        text=f"Customer confirmed they will increase orders by roughly {p:.4f}%. Plan reference {ref}. Effective from {start.date()} until {end.date()}."
        sources[sid]=SourceEvidence(source_id=sid,source_type=SourceType.ACCOUNT_NOTE,source_record_id=sid,
            source_revision="r1",authored_at=start-timedelta(weeks=5),available_at=start-timedelta(weeks=5),
            raw_text=text,content_hash="sha256:"+hashlib.sha256(text.encode()).hexdigest(),entity_mentions_raw=["CUST-0001"])
        hidden.append(HiddenState(ref,"CUST-0001",BusinessCertainty.ASSERTED,float(p)/100,start,end))
        truth.append(NoteGroundTruth(source_id=sid,entity_key="CUST-0001",event_id=ref,
            signal_type=SignalType.DEMAND_EXPECTATION,direction=Direction.INCREASE,
            business_certainty=BusinessCertainty.ASSERTED,conditionality=Conditionality.NONE,condition_text=None,
            stated_magnitude_value=float(p),stated_magnitude_unit="%",effective_start=start,effective_end=end,
            negated=False,is_irrelevant=False,is_reversal=False,supersedes_event_id=None,template_id="mechanics"))
    d0=realize_demand(["CUST-0001"],hidden,config,random.Random(1));fc=ForecastConfig(min_origins=1)
    pairs=[("CUST-0001",d) for d in dates]
    oracle=oracle_service(d0,truth,sources,"mechanics",forecast_config=fc).historical(pairs)
    records=run_extraction(list(sources.values()),{"CUST-0001"},extraction_run_id="mechanics").accepted
    extracted=DemandFeatureService(d0,records,sources,"mechanics",forecast_config=fc).historical(pairs)
    arms={label:run_arm(d0,fc,label,features) for label,features in (("A",None),("B",oracle),("C",extracted))}
    for arm in arms.values():paired_origins(arms["A"],arm)
    baseline=evaluate_arm(arms["A"]).mae
    metrics={label:asdict(evaluate_arm(arm,baseline)) for label,arm in arms.items()}
    return {"scenario":"explicit early independent random demand changes, no noise, fully materialized",
            "metrics":metrics,"oracle_usable":metrics["B"]["mae"]<baseline*.5,
            "separate_from_frozen_headline":True}

if __name__=="__main__":
    from dsfs.runs import atomic_json
    from dsfs.config import get_settings
    result=run_mechanics_scenario()
    atomic_json(get_settings().reports_dir/"mechanics-validation.json",result)
    print(result)
