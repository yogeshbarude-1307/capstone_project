# Realignment acceptance contract

This document supersedes earlier statements that feature HTTP serving,
freshness targets, or forecast degradation monitoring are optional.

The target is weekly **customer demand per account**, not constrained shipments.
Supplier fulfillment evidence is kept separate from demand-direction features.
All data and processing remain local; dependency installation is setup work.

| Requirement | Definition | Acceptance evidence |
|---|---|---|
| Forecast comparison | Same account/cutoff/horizon keys and model policy in A/B/C/D; training-only one-week MASE scaling; MAE and bias secondary | Future perturbation, paired-key, scaling, ablation tests; frozen seed reports |
| Feature serving | Forecast retrieves combined tabular/signal features through localhost HTTP without fallback | Real HTTP end-to-end test and transport manifest |
| Freshness | Hourly simulated publication; source availability to publication <= 60 minutes | Latency percentiles and breach counts, including injected delay |
| Drift warning | Persistent feature alert precedes confirmation of forecast degradation | Matched writing-change/no-drift experiment; nullable lead time and false alarms |
| Extraction conformance | Every accepted signal and served feature validates; failures quarantined | Contract tests and reports with explicit denominators |
| Lineage | Feature -> signal -> source revision and source span | Resolution tests and sampled traces |
| Independent extraction evaluation | 35 natural-prevalence and 15 challenge notes; blind human single-review labels | Reviewer package and completed human evaluation, separate from drafts |

## Temporal and experimental defaults

- Monday 00:00 UTC cutoff t. Horizon h targets [t+7(h-1), t+7h) days.
- Demand from periods ending after t is unavailable. Trailing training targets
  span 52 weeks; lag history can precede that window but never the cutoff.
- Signals must be PASS, active as of their simulated publication at t, and
  intersect the individual target week. REVIEW/FAIL remain diagnostic only.
- MASE denominator is mean absolute one-week change in the account's training
  history. Zero scales are unavailable, counted explicitly, never replaced.
- Development seeds 1,2,3; frozen evaluation seeds 101,102,103,104,105.
  Headline scale: 40 accounts x 104 weeks, four horizons. Ablations: 10 accounts.
- Numeric standardization and missingness are fit on training inputs only.
- Feature drift: weekly probes, eight-week reference, p<0.05, effect>=0.3,
  two consecutive qualifying probes. Degradation: mature four-week MAE exceeds
  matched control by 10% for two consecutive probes. Lead time is confirmation
  time minus alert time; missing events produce null, not an invented score.

## Publication and versioning

Simulated publication times and actual processing timestamps are distinct.
The current forecast contract is demand-v1 / schema 1.0.0. Old schema 0.1.0
artifacts remain readable for inspection; they are never relabeled or overwritten.
New runs use isolated directories and atomically publish completed manifests.
Schema validity does not establish semantic accuracy or positive forecast lift.
Negative oracle/forecast outcomes are legitimate results and are reported.

Independent labels must be supplied by the reviewer; software must never
manufacture reviewer identities, labels, or adjudication status.

## Implementation and verification map

| Capability | Implementation | Regression / run artifact |
|---|---|---|
| Boundary, trailing targets, training scaling, paired keys | `forecast/harness.py` | `tests/test_realignment.py`, `reports/forecast/origins.json` |
| Event cancellation, deduplication and target overlap | `synth/latent.py`, `synth/demand.py`, `features/service.py`, `extraction/ledger.py` | lifecycle tests; `mechanics.json` |
| Combined HTTP feature contract and explicit failures | `features/http.py`, `features/providers.py` | actual socket retrieval tests; `steps.serving` |
| Publication and age as distinct measurements | `features/publication.py`, `models/demand_feature.py` | delay tests; `steps.freshness`, per-row note age |
| Immutable run selection and atomic completion | `runs.py`, `server.py` | lock and end-to-end tests; run manifest and hashes |
| Allowlisted ablations and paired trajectories | `evaluation/ablation.py`, `evaluation/paired.py`, `study.py` | ablation tests; frozen study summary and ten-account matrices |
| Persistent drift and mature degradation | `drift/experiment.py` | maturity/no-event tests; `reports/drift/writing_change.json`, matched inputs |
| Blind, single-review human evaluation | `evaluation/review_package.py`, `evaluation/report.py` | placeholder rejection and package counts; `reports/review` |

The oracle gate requires the frozen study's 95% paired MASE lift interval to lie
above zero. It is separate from the noiseless mechanics gate. Active target-week
demand counts/direction include dated ongoing events of any age; 30-day note counts
retain their recent-note meaning. Supplier counts do not enter demand aggregates.
Exposure breakdowns use active target-week demand signals, not merely recent notes.
The drift reference is the fixed eight weeks preceding the declared writing change;
probes contain account/horizon rows at one weekly cutoff. The no-drift calibration
uses this same full rule. False alerts are reported even when frequent.

Schema versions: demand feature 1.0.0 (`demand-v1`), signal 0.2.0 (business-event ref),
annotation d2-0.2.0 (preceding source context). Legacy signal and annotation versions
remain readable. `generated_at`/`extracted_at` are actual execution clocks except
explicitly labelled reproducible evaluation replay; publication clocks are simulated.

`days_since_latest_signal` and the legacy `freshness_flag` describe note recency
from source availability. They do not measure publication latency; that uses
`publication_latency_minutes`, `freshness_target_minutes`, and `freshness_breach`.
The retained extractor currently recognizes the generator's `roughly N%` magnitude
phrase. Aggregation supports typed quantities separately, while broader quantity
language remains a documented extraction limitation for independent review.

`feature_available_at` records the latest contributing signal-component publication.
The combined tabular/signal snapshot is assembled for `forecast_cutoff`, with only
completed tabular periods. Component publication metadata must not be read as the
actual wall-clock execution time of the HTTP request or the full evidence run.
