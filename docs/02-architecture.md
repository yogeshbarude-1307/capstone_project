> Historical design/evidence: the [realignment acceptance contract](20-realignment-acceptance.md) supersedes conflicting scope and semantics below. The current target is weekly customer demand, Monday UTC cutoffs, four separate weekly horizons, PASS-only published signals, required HTTP consumption, a one-hour simulated freshness target, and matched forecast-degradation lead time. Earlier test counts and results require revalidation.

# 02 — Architecture

## End-to-end data flow

```
                    ┌─────────────────────────────┐
                    │  Synthetic Data Generator    │
                    │  (causal state → knowable    │
                    │   info → note text; demand   │
                    │   realized later, separately)│
                    └───────────────┬─────────────┘
                                    │
                 ┌──────────────────┼───────────────────┐
                 ▼                                        ▼
      ┌────────────────────┐                  ┌───────────────────────┐
      │  Source Evidence     │                  │  D0: Tabular demand    │
      │  Store (immutable)   │                  │  history (baseline)    │
      │  raw note + metadata │                  └───────────┬───────────┘
      └──────────┬───────────┘                              │
                 │                                            │
                 ▼                                            │
      ┌────────────────────────────────────┐                │
      │  Extraction Pipeline                 │                │
      │  rules → NER → local constrained LLM │                │
      │  → deterministic validator           │                │
      │  → abstention where unsupported      │                │
      └──────────────┬──────────────────────┘                │
                 │                                            │
                 ▼                                            │
      ┌────────────────────────────────────┐                │
      │  Signal Ledger (append-only)         │                │
      │  versioned structured events         │                │
      │  + evidence + provenance             │                │
      └──────────────┬──────────────────────┘                │
                 │                                            │
                 ▼                                            │
      ┌────────────────────────────────────┐                │
      │  Feature Transformation               │                │
      │  point-in-time eligible signals →     │                │
      │  windowed / decayed / aggregated      │                │
      │  forecast features                    │                │
      └──────────────┬──────────────────────┘                │
                 │                                            │
                 ▼                                            ▼
      ┌────────────────────────────────────┐    ┌─────────────────────┐
      │  Feature Access Layer                 │    │  Baseline Forecast    │
      │  callable Python API (batch +         │    │  (tabular only)       │
      │  historical/point-in-time retrieval)  │    └──────────┬──────────┘
      └──────────────┬──────────────────────┘               │
                 │                                            │
                 ▼                                            ▼
      ┌────────────────────────────────────────────────────────────┐
      │  Forecasting Experiment Harness (4 arms, rolling-origin CV)   │
      │  A: tabular   B: oracle-signal   C: extracted-signal          │
      │  D: shuffled-signal (negative control)                        │
      └──────────────┬───────────────────────────────────────────────┘
                 │
                 ▼
      ┌────────────────────────────────────┐
      │  Evaluation & Reporting               │
      │  extraction metrics (independent)     │
      │  forecast lift + ablations            │
      │  drift/monitoring report              │
      │  lineage trace                        │
      └────────────────────────────────────┘
```

All arrows are local, in-process, file-based hand-offs. No network calls cross any boundary in this diagram.

## Component responsibility table

| Component | Owns | Must not own |
|---|---|---|
| Synthetic data generator | Causal state, knowable-at-note-time info, note text, later-realized demand | Feature semantics, forecast logic |
| Source evidence store | Immutable raw note + `source_event_time`/`authored_at`/`available_at` + content hash | Interpretation of the note |
| Extraction pipeline | Turning note text into candidate structured events + evidence spans | Forecast feature aggregation, business-key resolution beyond simple matching |
| Deterministic validator | Schema/type/range/enum checks, business-rule cross-field checks, abstention decision | Guessing missing values |
| Signal ledger | Durable, versioned, append-only structured event history | Overwriting or silently mutating past interpretations |
| Feature transformation | Signal → point-in-time feature computation, `feature_definition_version` pinning | Re-interpreting source text |
| Feature access layer | Contracted retrieval (batch + historical), freshness/lineage metadata in the response | Hidden/implicit feature derivation |
| Forecast baseline / experiment harness | Consuming approved feature versions, running the 4-arm comparison | Text parsing |
| Evaluation & reporting | Extraction metrics, forecast metrics, drift report, lineage trace — kept independent | Conflating extraction quality with forecast value |

## Why this shape

- **Layer separation** (evidence → signal → feature) is preserved so that a wrong forecast can be diagnosed as an extraction problem, a representation problem, or a genuine "no signal exists" result — see `08-forecasting-experiment-design.md` for how the 4 arms isolate this.
- **Point-in-time correctness** is enforced structurally: the feature-transformation step is the *only* place allowed to join signals to forecast cutoffs, and it must apply the eligibility rule in `03-data-model.md` §Temporal Model before any row reaches the experiment harness.
- **Everything is local**: every box above is a local file/table/Python object; no component requires network access, matching the confirmed offline constraint.
