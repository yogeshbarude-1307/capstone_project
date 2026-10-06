# Demand Signal Feature Service

A local Python demonstration that turns synthetic business notes into structured,
point-in-time demand features and evaluates whether they improve weekly customer
demand forecasts. Supplier fulfillment signals remain separate. The pipeline uses
rules-based extraction, Parquet, numpy Ridge regression, and a real localhost HTTP
feature service. No pipeline step calls a hosted model or downloads data.

The authoritative requirements and metric definitions are in
[the realignment acceptance contract](docs/20-realignment-acceptance.md).
Documents 00–19 preserve historical designs and evidence; conflicting historical
claims do not describe the current implementation.

## Setup (PowerShell)

Run from this checkout. Python 3.11+ is declared; the verified environment uses
Python 3.14.7 on Windows. Dependency installation needs internet access or a local
wheelhouse; execution thereafter stays offline.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-tested.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The dependency snapshot includes runtime, test and server packages. Canonical
schemas live in this checkout, so retain `docs/schemas` with the editable install.
Actual versions and source hashes are also captured in each completed manifest.

## Reproduce the demonstration

```powershell
# Small HTTP-backed regression demonstration
.\.venv\Scripts\dsfs-run.exe --config configs/e2e_smoke.json

# Complete 40-account / 104-week evidence bundle, writing drift and review package
.\.venv\Scripts\dsfs-run.exe --config configs/e2e_full.json

# Development seeds 1–3, then frozen evaluation 101–105 and 10-account ablations
.\.venv\Scripts\dsfs-study.exe

# Open http://127.0.0.1:8000 after starting the dashboard
.\.venv\Scripts\dsfs-server.exe
```

Choose one completed run in the dashboard. The Run Pipeline button creates a new
smoke run; it does not overwrite the selected evidence. Forecast, extraction,
drift and lineage views all select the same immutable run. Freshness metadata is
shown across views. Completed independent-review bundles at the documented external path are shown separately in the extraction view. The full command includes a separate, controlled writing-change
experiment with identical demand in the changed and unchanged corpora.

Artifacts live under `reports/runs/<run-id>/{raw,processed,interim,reports}`.
Completed manifests are published atomically; `reports/manifest.json` points to
the latest completed run. Concurrent pipeline runs are rejected. Failed runs keep
`failure.json` and are excluded from completed-run selection. Older artifacts are
preserved. Study settings, run IDs, paired intervals and findings live under
`reports/studies/<study-id>`.

## Interpretation

At Monday 00:00 UTC cutoff t, horizons 1–4 predict `[t,t+7d)` through
`[t+21d,t+28d)`. Only completed earlier demand periods enter training and lags.
The training target window is the trailing 52 weeks. MASE scales each account's
errors by its training-only mean absolute one-week change; zero denominators are
unavailable and counted. MAE and signed bias are also reported. Confidence
intervals resample complete paired account trajectories within each seed.

The four arms share one model policy: A tabular baseline; B generator
interpretations through shared aggregation; C text interpretations retrieved over
HTTP; D features assigned to different accounts at the same cutoff. D is unavailable
for a single account. Ablations remove disallowed columns, including their missingness
indicators. Feature matrices and completed full-arm results are reused in ablations.

Simulated hourly publication is distinct from actual extraction/execution time.
Freshness measures source availability to publication against 60 minutes; note age
is reported separately. An injected delayed batch demonstrates a breach. Only PASS
records visible at the cutoff contribute; repeated business-event references do
not multiply magnitude, and cancellations preserve historical state.

Drift monitoring compares weekly extracted percentage-presence distributions with
an eight-week reference. An alert requires p<0.05, effect size ≥0.3 and two successive
qualifying windows. Forecast degradation requires >10% excess MAE over the matched
control in two successive fully mature four-week windows. Warning lead time is
confirmation time minus alert time; missing events remain unavailable. No-drift
runs measure the complete rule's false-alert behavior.

Positive oracle lift is an experimental gate. Negative results and false alarms
remain in the reports; synthetic results do not establish predictive value in real
company notes. NER and local LLM extraction remain deferred.

## Independent review

The full run prepares `reports/review/review_dataset.json` inside its run directory:
35 natural-prevalence notes and 15 new challenge notes, grouped with preceding source
context. The package contains no predictions or generator truth. Its labels remain
unfinished until an independent person completes them. The evaluator rejects
placeholder labels and empty scored fields.

Follow the accompanying `REVIEW_INSTRUCTIONS.md`, save completed labels to a **new
working copy outside the immutable run**, then evaluate:

```powershell
.\.venv\Scripts\dsfs-evaluate.exe --dataset path\to\completed_review.json --split test --output-dir reports\independent-reviews\<run-id>
```

Single-review human results are reported separately by cohort and from provisional
starter labels. Do not use `--require-gold`: that older mode requires double
adjudication. No independent accuracy claim is made while this package is pending.

## Code map

| Path | Responsibility |
|---|---|
| `src/dsfs/synth` | Latent lifecycle, separate text rendering and demand realization |
| `src/dsfs/extraction` | Rules, entity/ref resolution, append-only ledger and quarantine |
| `src/dsfs/features` | Shared weekly aggregation, publication replay, HTTP providers/endpoints |
| `src/dsfs/forecast` | Temporal harness, oracle interpretations and shuffled control |
| `src/dsfs/evaluation` | Paired intervals, allowlisted ablations and blind review |
| `src/dsfs/drift/experiment.py` | Matched writing-change/degradation and no-drift calibration |
| `src/dsfs/runs.py`, `orchestrate.py`, `study.py` | Isolated runs, atomic completion and frozen study |
| `src/dsfs/server.py`, `static/index.html` | Dashboard and feature API |

The legacy Gradio app remains available via the optional `ui` extra; the supported
realignment demonstration uses `dsfs-server`.
