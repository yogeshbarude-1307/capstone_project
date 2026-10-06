"""Acceptance tests exercise actual temporal and serving failure boundaries."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import numpy as np
import pandas as pd
import pytest
from dsfs.forecast.harness import ForecastConfig, run_arm, evaluate_arm, paired_origins, _ridge_fit
from dsfs.features.service import DemandFeatureService
from dsfs.features.providers import serve_local, InProcessFeatureProvider, HttpFeatureProvider
from dsfs.features.publication import published_at, publication_summary
from dsfs.extraction.pipeline import run_extraction
from dsfs.models.signal_record import ValidationStatus
from tests.extraction.conftest import make_evidence

def history(n=80):
    rng=np.random.default_rng(3)
    return pd.DataFrame([{"entity_key":e,"period_start":pd.Timestamp("2023-01-02")+pd.Timedelta(weeks=w),
        "week_index":w,"demand":100+w+rng.normal(0,2)} for e in ("CUST-0001","CUST-0002") for w in range(n)])

def service_fixture(delay=0):
    note=make_evidence("plan", "Customer confirmed they will increase orders by roughly 20%. Plan reference EVT-1. Effective from 2023-10-09 until 2023-11-06.",
                       authored_at="2023-10-01T12:00:00Z",available_at="2023-10-01T12:05:00Z")
    records=run_extraction([note],{"CUST-0001"},extraction_run_id="acceptance").accepted
    return DemandFeatureService(history(),records,{note.source_id:note},"acceptance",delays={note.source_id:delay})

def test_forecast_unchanged_when_cutoff_and_future_demand_changes():
    d0=history()
    cfg=ForecastConfig(train_weeks=45,horizon_weeks=4,min_origins=1)
    before=run_arm(d0,cfg,"A")
    changed=d0.copy()
    changed.loc[changed.week_index>=45,"demand"]+=10000
    after=run_arm(changed,cfg,"A")
    left=[o for o in before.origins if o.origin_week_index==45]
    right=[o for o in after.origins if o.origin_week_index==45]
    assert len(left)==8
    np.testing.assert_array_equal([o.predicted for o in left],[o.predicted for o in right])
    assert all(o.horizon_week_index==45+o.horizon_step-1 for o in left)

def test_training_targets_are_past_and_within_trailing_window(monkeypatch):
    import dsfs.forecast.harness as harness
    d0=history(70)
    d0["demand"]=d0.week_index.astype(float)+1
    calls=[]
    original=harness._ridge_fit
    def spy(x,y,alpha):
        calls.append(y.copy())
        return original(x,y,alpha)
    monkeypatch.setattr(harness,"_ridge_fit",spy)
    cfg=ForecastConfig(train_weeks=15,lag_weeks=[1,2],horizon_weeks=2,min_origins=1)
    result=run_arm(d0,cfg,"A")
    assert len(calls)==len(result.origins)
    for targets,o in zip(calls,result.origins):
        assert targets.max()<=o.origin_week_index  # demand[w]=w+1
        assert targets.min()>=o.origin_week_index-cfg.train_weeks+1

def test_mase_scale_only_uses_training_history_and_counts_constant_series():
    d0=history()
    d0["demand"]=np.where(d0.week_index<45,100+2*d0.week_index,10000)
    result=run_arm(d0,ForecastConfig(train_weeks=45,horizon_weeks=1,min_origins=1),"A")
    assert next(o for o in result.origins if o.origin_week_index==45).mase_scale==2
    d0["demand"]=100
    metric=evaluate_arm(run_arm(d0,ForecastConfig(train_weeks=45,horizon_weeks=1,min_origins=1),"A"))
    assert np.isnan(metric.mase)
    assert metric.mase_unavailable_count==metric.n_origins

def test_paired_arms_reject_different_keys_and_actuals():
    arm=run_arm(history(),ForecastConfig(train_weeks=45,horizon_weeks=1,min_origins=1),"A")
    other=replace(arm,origins=arm.origins[1:])
    with pytest.raises(ValueError,match="different.*keys"):
        paired_origins(arm,other)
    other=replace(arm,origins=[replace(o,actual=o.actual+1) for o in arm.origins])
    with pytest.raises(ValueError,match="actual"):
        paired_origins(arm,other)

def test_ridge_is_invariant_to_input_units_after_training_standardization():
    rng=np.random.default_rng(6); x=rng.normal(size=(30,2));y=2*x[:,0]+3*x[:,1]
    a,b=_ridge_fit(x,y,1)
    factors=np.array([1000,.001]); c,d=_ridge_fit(x*factors,y,1)
    np.testing.assert_allclose(x@a+b,(x*factors)@c+d,atol=1e-10)

def test_percentage_survives_old_note_age_and_week_boundaries():
    service=service_fixture()
    cutoff=datetime(2023,10,9,tzinfo=timezone.utc)
    row=service.row("CUST-0001",cutoff,1)
    assert row.signed_pct_change==20
    assert row.expected_qty_delta_next_horizon is None
    assert row.target_start==cutoff and row.target_end==cutoff+timedelta(weeks=1)
    # Alter availability to make the same dated ongoing claim older than 30 days.
    source=service.sources["plan"].model_copy(update={"authored_at":datetime(2023,8,1,tzinfo=timezone.utc),
                                                  "available_at":datetime(2023,8,1,tzinfo=timezone.utc)})
    old=DemandFeatureService(service.d0,service.signals,{"plan":source},service.run_id)
    assert old.row("CUST-0001",cutoff).signed_pct_change==20
    assert old.row("CUST-0001",cutoff).signal_count_30d==0
    assert old.row("CUST-0001",cutoff).active_demand_signal_count==1
    assert old.row("CUST-0001",cutoff).target_demand_direction.value=="INCREASE"


def test_aggregation_keeps_negative_percentage_and_absolute_quantity_separate():
    original=service_fixture()
    percent=original.sources["plan"].model_copy(update={"raw_text":original.sources["plan"].raw_text.replace("increase","decrease")})
    quantity=make_evidence("quantity","Customer confirmed they will increase orders by 50 units. Plan reference EVT-2. Effective from 2023-10-09 until 2023-11-06.",
        authored_at="2023-10-01T12:00:00Z",available_at="2023-10-01T12:05:00Z")
    result=run_extraction([percent,quantity],{"CUST-0001"},extraction_run_id="acceptance")
    # The retained rules baseline parses percentage templates. Supply a typed
    # quantity interpretation to exercise shared aggregation, not a new rule.
    from dsfs.models.signal_record import MagnitudeBasis
    interpreted=[r.model_copy(update={"magnitude_value":50,"magnitude_unit":"units","magnitude_basis":MagnitudeBasis.ABSOLUTE})
                 if r.source_id==quantity.source_id else r for r in result.accepted]
    row=DemandFeatureService(original.d0,interpreted,{n.source_id:n for n in (percent,quantity)},"acceptance").row(
        "CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc))
    assert row.signed_pct_change==-20 and row.expected_qty_delta_next_horizon==50

def test_repeats_do_not_multiply_and_published_cancellation_removes_claim():
    service=service_fixture()
    repeat=service.sources["plan"].model_copy(update={"source_id":"repeat","source_record_id":"repeat"})
    cancellation=make_evidence("cancel","Previous expansion plan for orders has been cancelled. Plan reference EVT-1. Effective from 2023-10-16 until 2023-11-06.",
                               authored_at="2023-10-16T00:00:00Z",available_at="2023-10-16T00:05:00Z")
    notes=[service.sources["plan"],repeat,cancellation]
    result=run_extraction(notes,{"CUST-0001"},extraction_run_id="acceptance")
    store=DemandFeatureService(service.d0,result.accepted,{n.source_id:n for n in notes},"acceptance")
    assert store.row("CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc)).signed_pct_change==20
    assert store.row("CUST-0001",datetime(2023,10,16,tzinfo=timezone.utc)).signed_pct_change==20
    assert store.row("CUST-0001",datetime(2023,10,23,tzinfo=timezone.utc)).signed_pct_change is None

def test_review_and_supplier_signals_do_not_enter_demand_percent():
    service=service_fixture()
    reviewed=service.signals[0].model_copy(update={"validation_status":ValidationStatus.REVIEW})
    store=DemandFeatureService(service.d0,[reviewed],service.sources,service.run_id)
    row=store.row("CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc))
    assert row.signed_pct_change is None and row.rejected_signal_count==1
    from dsfs.models.signal_record import ImpactChannel
    supplier=service.signals[0].model_copy(update={"impact_channel":ImpactChannel.FULFILLMENT})
    row=DemandFeatureService(service.d0,[supplier],service.sources,service.run_id).row("CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc))
    assert row.signed_pct_change is None and row.supply_signal_count==1

def test_hourly_publication_and_delay_breach():
    dt=datetime(2023,10,1,12,5,tzinfo=timezone.utc)
    assert published_at(dt)==datetime(2023,10,1,13,tzinfo=timezone.utc)
    service=service_fixture()
    assert publication_summary(service.sources)["breach_count"]==0
    assert publication_summary(service.sources,{"plan":120})["breach_count"]==1
    delayed=service_fixture(8*24*60)
    assert delayed.row("CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc)).signed_pct_change is None

def test_real_http_matches_internal_features_and_never_returns_notes():
    service=service_fixture()
    pairs=[("CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc))]
    internal=InProcessFeatureProvider(service).retrieve(pairs)
    with serve_local(service) as provider:
        served=provider.retrieve(pairs)
        assert provider.request_count==1
    pd.testing.assert_frame_equal(served.drop(columns="generated_at"),internal.drop(columns="generated_at"))
    assert "raw_text" not in served and "ground_truth" not in served

def test_http_failure_has_no_fallback():
    from urllib.error import URLError
    with pytest.raises(URLError):
        HttpFeatureProvider("http://127.0.0.1:1","acceptance",timeout=.1).retrieve(
            [("CUST-0001",datetime(2023,10,9,tzinfo=timezone.utc))])

def test_http_rejects_bad_versions_cutoffs_and_duplicate_keys():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dsfs.features.http import feature_router
    service=service_fixture();app=FastAPI()
    def resolve(run_id):
        if run_id!=service.run_id:raise KeyError("Unknown run")
        return service
    app.include_router(feature_router(resolve))
    with TestClient(app) as client:
        body={"run_id":"acceptance","entity_keys":["CUST-0001"],"forecast_cutoff":"2023-10-09T00:00:00Z"}
        assert client.post("/v1/features:batchGet",json=body).status_code==200
        assert client.post("/v1/features:batchGet",json={**body,"feature_set_version":"wrong"}).status_code==404
        assert client.post("/v1/features:batchGet",json={**body,"forecast_cutoff":"2023-10-10T00:00:00Z"}).status_code==422
        assert client.post("/v1/features:batchGet",json={**body,"run_id":"unknown"}).status_code==404
        assert client.post("/v1/features:batchGet",json={**body,"entity_keys":["CUST-0001"]*2}).status_code==422
        assert client.get("/v1/lineage/acceptance/"+service.signals[0].signal_id).json()["source"]["source_revision"]=="r1"

def test_pipeline_lock_rejects_concurrency_and_releases(tmp_path):
    from dsfs.config import Settings
    from dsfs.runs import pipeline_lock
    settings=Settings(reports_dir=tmp_path)
    with pipeline_lock(settings):
        with pytest.raises(RuntimeError,match="concurrent"):
            with pipeline_lock(settings):pass
    with pipeline_lock(settings):pass


def test_future_notes_cannot_change_earlier_augmented_forecasts():
    service=service_fixture()
    cfg=ForecastConfig(train_weeks=45,horizon_weeks=4,min_origins=1)
    pairs=[(e,pd.Timestamp(d).tz_localize("UTC").to_pydatetime()) for e in service.by_entity
           for d in sorted(service.d0.period_start.unique())]
    before=run_arm(service.d0,cfg,"C",service.historical(pairs))
    future=service.sources["plan"].model_copy(update={"source_id":"future","source_record_id":"future",
        "available_at":datetime(2024,3,1,tzinfo=timezone.utc),"authored_at":datetime(2024,3,1,tzinfo=timezone.utc)})
    signal=service.signals[0].model_copy(update={"signal_id":"future-signal","source_id":"future",
                                               "business_event_ref":"FUTURE","magnitude_value":1000})
    other=DemandFeatureService(service.d0,service.signals+[signal],{**service.sources,"future":future},service.run_id)
    after=run_arm(service.d0,cfg,"C",other.historical(pairs))
    np.testing.assert_array_equal([o.predicted for o in before.origins if o.origin_week_index==45],
                                  [o.predicted for o in after.origins if o.origin_week_index==45])


def test_latent_cancellation_preserves_prior_demand_and_stops_effect():
    import random
    from dsfs.synth.config import GeneratorConfig
    from dsfs.synth.latent import HiddenState
    from dsfs.synth.demand import realize_demand
    from dsfs.models.signal_record import BusinessCertainty
    cfg=GeneratorConfig(n_entities=1,n_weeks=8,weekly_baseline_level_range=(100,100),
        weekly_trend_frac_range=(0,0),seasonal_amplitude_frac=0,demand_noise_frac=0,
        realized_magnitude_noise_frac=0,materialization_prob_by_certainty={"ASSERTED":1})
    start=datetime(2023,1,16,tzinfo=timezone.utc);end=start+timedelta(weeks=4)
    event=HiddenState("EVT-1","CUST-0001",BusinessCertainty.ASSERTED,.4,start,end)
    original=realize_demand([event.entity_key],[event],cfg,random.Random(1))
    cancelled=realize_demand([event.entity_key],[replace(event,cancellation_at=start+timedelta(days=10))],cfg,random.Random(1))
    np.testing.assert_array_equal(original.demand[:3],cancelled.demand[:3])
    assert cancelled.demand.iloc[3]==round(100+40*3/7,2)
    assert cancelled.demand.iloc[4]==100 and original.demand.iloc[4]==140
    from dsfs.synth.latent import generate_latent_events
    _,generated=generate_latent_events([event.entity_key],cfg.model_copy(update={
        "events_per_entity_per_year":100,"reversal_probability":1,"effective_duration_weeks_range":(2,2)}),random.Random(1))
    assert generated
    assert all(e.effective_start<e.cancellation_at<e.effective_end for e in generated)


def test_simple_planted_oracle_has_usable_early_percentage_information():
    from dsfs.evaluation.mechanics import run_mechanics_scenario
    result=run_mechanics_scenario()
    assert result["oracle_usable"]
    assert result["metrics"]["C"]["mae"]<result["metrics"]["A"]["mae"]*.5


def test_degradation_uses_mature_windows_and_missing_event_has_no_lead_time():
    from dsfs.drift.experiment import degradation_time, matched_report
    base=run_arm(history(),ForecastConfig(train_weeks=45,horizon_weeks=4,min_origins=1),"C")
    base=replace(base,origins=[replace(o,predicted=o.actual+1) for o in base.origins])
    changed=replace(base,origins=[replace(o,predicted=o.actual+(3 if o.origin_week_index>=55 else 1)) for o in base.origins])
    when,windows=degradation_time(base,changed,injection_week=50)
    assert when>=59
    assert not any(w["qualifies"] for w in windows if w["confirmed_at_week"]<59)
    none,_=degradation_time(base,base,injection_week=50)
    assert none is None
    service=service_fixture();features=service.historical([(e,pd.Timestamp(d).tz_localize("UTC"))
        for e in service.by_entity for d in sorted(service.d0.period_start.unique())])
    from datetime import date
    report=matched_report(features,features,base,base,date(2023,1,2),50,[features])
    assert report["lead_time_weeks"] is None and report["degradation_week"] is None


def test_blind_package_counts_and_unfinished_review_is_rejected(tmp_path):
    from dsfs.synth.config import GeneratorConfig
    from dsfs.synth.generator import generate_dataset
    from dsfs.evaluation.review_package import prepare_review_package
    from dsfs.evaluation.annotations import AnnotationDataset
    from dsfs.evaluation.report import run_evaluation
    dataset=generate_dataset(GeneratorConfig(n_entities=10))
    metadata=prepare_review_package(dataset.d1_notes,dataset.entities,tmp_path)
    assert metadata["counts"]=={"natural_prevalence":35,"challenge":15}
    payload=json.loads((tmp_path/"review_dataset.json").read_text())
    tags={t for c in payload["cases"] if c["sample"]=="challenge" for t in c["tags"]}
    assert {"vague_time","negation","conditional","reversal","ambiguous_event_reference"}<=tags
    assert all("prediction" not in c and "ground_truth" not in c for c in payload["cases"])
    with pytest.raises(ValueError,match="unfinished"):
        run_evaluation(AnnotationDataset.model_validate(payload),split="test")


def test_dashboard_reads_one_completed_snapshot_and_rejects_unknown_run(tmp_path,monkeypatch):
    from dsfs import server
    from dsfs.config import Settings
    from dsfs.runs import run_settings, atomic_json
    from fastapi.testclient import TestClient
    settings=Settings(reports_dir=tmp_path)
    monkeypatch.setattr(server,"_settings",lambda:settings)
    for run in ("first","second"):
        isolated=run_settings(settings,run);isolated.ensure_dirs()
        record=service_fixture().signals[0].model_copy(update={"signal_id":run,"extraction_run_id":run})
        (isolated.data_processed_dir/"signal_ledger.jsonl").write_text(record.model_dump_json()+"\n")
        manifest={"run_id":run,"status":"complete","finished_at":run,"steps":{}}
        atomic_json(isolated.reports_dir/"manifest.json",manifest)
    atomic_json(settings.reports_dir/"manifest.json",manifest)
    with TestClient(server.app) as client:
        assert [r["signal_id"] for r in client.get("/api/signals?run_id=first").json()]==["first"]
        assert [r["signal_id"] for r in client.get("/api/signals").json()]==["second"]
        assert client.get("/api/signals?run_id=unknown").status_code==404
