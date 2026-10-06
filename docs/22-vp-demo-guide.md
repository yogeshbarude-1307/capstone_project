# VP panel prototype guide

## Start

```powershell
cd D:\dev\capstone_project
.\.venv\Scripts\python.exe -m dsfs.server
```

Open `http://127.0.0.1:8000`. The dashboard defaults to the frozen
40-account run `run-20261005T083131-fdcd6526` when it is available.

## Five-minute presentation flow

1. **Overview — the decision** (60 seconds)
   - State the problem: shipment history reports demand changes after the fact; account notes can provide earlier qualitative signals.
   - Point to the evaluation banner. The prototype reports the measured result honestly: extracted signals did not beat the tabular baseline in the frozen synthetic study.
   - Use the account selector on the forecast chart to demonstrate how a planner would inspect an account. The plotted trace is explicitly illustrative; the MASE and paired-lift values are measured.
   - Point to freshness, drift warning lead, recent evidence, and the exception queue.

2. **Signal Inbox — the evidence** (60 seconds)
   - Open a critical demand-decrease signal.
   - Show the source note, extracted direction, magnitude, effective period, certainty, publication time, and validation state.
   - Explain that supplier fulfillment stays separate from demand direction.

3. **Forecast Explorer — the experiment** (60 seconds)
   - Explain the four arms: tabular baseline, oracle interpretation, extracted signals, and shuffled-account control.
   - Emphasize paired evaluation and the rule that a negative oracle result sends the team back to representation rather than prompting an unsupported value claim.

4. **Drift & Freshness — operational control** (45 seconds)
   - Show the one-hour simulated publication target and injected delayed-batch breach.
   - Show the matched writing-change scenario: 14-week warning lead and 30% false-alert rate.

5. **Lineage — trust** (45 seconds)
   - Select an account and cutoff, then trace a feature to the contributing signal and highlighted source-note span.
   - Explain that historical retrieval excludes unpublished and superseded evidence.

6. **Extraction Quality — review status** (45 seconds)
   - Show schema conformance and field metrics.
   - Show the separate Claude cross-model AI draft: 35 natural-prevalence and 15 challenge notes.
   - State clearly that it is provisional and the independent-person review remains pending.

## Close

The prototype demonstrates the complete product mechanics: unstructured notes become
versioned features, the forecast pipeline retrieves them through an API, users can
investigate exceptions and lineage, and the system reports forecast value, freshness,
extraction quality, and drift without hiding negative results.

The next research gate is improving the event representation until oracle features show
reliable incremental forecast value. The next validation gate is one independent person
reviewing the frozen 50-note package.

