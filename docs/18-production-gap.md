# 18 — Production Gap Assessment

Written 2026-09-27, extending `01-poc-scope-and-non-goals.md` with what
`17-poc-findings.md` actually observed. Priority-ordered: earlier items block
later ones from being meaningful.

## Priority-ordered gaps

### 1. Real-corpus prevalence and lead-time study (Gates A, B)

**Nothing in this POC establishes that real account/service/supplier notes
contain forecast-relevant information, at what frequency, or how early
relative to the demand change they describe.** This is the single largest gap
— every other result in `17-poc-findings.md` is conditioned on "if a signal
with these properties exists." Before any further engineering investment,
someone with access to real note sources needs to answer, even informally:
do notes actually reference future demand changes, and how far ahead?

**Cannot be closed with more synthetic-POC work.** Requires real data access
and a business/domain stakeholder.

### 2. Entity master-data resolution at production scale (Gate D)

`17-poc-findings.md` §3 measured this directly: exact-string resolution
recall goes from 100% to 0% the moment a note uses a nickname, pronoun, or
hierarchy reference instead of the literal canonical key. Production would
need at minimum: an alias/nickname table per entity, fuzzy matching with a
confidence threshold, and an explicit "ambiguous — do not guess" abstention
path (the current resolver already abstains correctly when it can't match;
it just can't match very much).

**Estimated effort:** non-trivial NLP/data-engineering work, gated on having
real master data to resolve against (which doesn't fully exist without a
real note source either — see gap 1).

### 3. Human-gold annotation program (Gate C at production quality)

The 0.4158 macro-F1 headline number is self-scored — the same process wrote
the extraction rules and the "expected" labels being compared against them.
`scripts/select_review_sample.py` built the infrastructure for an independent
check (50-note sample, reusing the existing evaluation machinery so scores are
directly comparable), but the actual labeling by a second person was not
completed this session. Before any claim about extraction quality:

1. Complete the 50-note independent review that's already scaffolded
   (`docs/annotations/human_review_instructions.md`).
2. If that confirms the self-scored number is roughly right, scale to the
   docs/09-proposed ~800-note D2 minimum with double annotation and adjudication.
3. Only then is a macro-F1 number meaningful outside this POC.

### 4. Business-decision impact study (Gate H)

Nothing in this POC establishes what forecast error actually costs the
business, or whether the asymmetric cost of over- vs. under-forecasting makes
a 3-10% MAE change (the range seen in `17-poc-findings.md` §4, all currently
*negative*) worth anything at all. `docs/14-open-questions.md` item 5 (business-
approved minimum meaningful lift) is still open. Until it's answered, "does
the forecast improve" and "does that improvement matter" remain two different,
both-unresolved questions.

### 5. Resolve the B≈A finding before further extraction investment

This is new, specific to this POC run (not a generic production gap): the
oracle arm — the upper bound, bypassing extraction entirely — did not beat
the tabular baseline. Per docs/08's own decision logic, this means **iterating
on the extractor next would be premature**. The ablation matrix
(`17-poc-findings.md` §4) narrows this further: `direction`/`magnitude`
representations are statistically indistinguishable from no effect (CIs
straddle zero), while `effective_time` — and therefore `full`, since they're
identical — is where both oracle and extracted arms' loss concentrates, with
CIs excluding zero on the harmful side. Concrete, cheap-to-run next steps,
in order:

1. **Try dropping just the effective-time feature group**
   (`nearest_effective_start_days`, `delay_count_90d`, `days_since_latest_signal`)
   from the "full" feature set and re-run arms B/C — if MAE recovers to near
   the `direction`/`magnitude` row, the problem is isolated to those three
   columns specifically, not the whole representation.
2. Try feature scaling/normalization on the oracle/extracted signal columns
   before merging with tabular lag features (currently raw counts/quantities
   mixed with demand-scale lag values in one unregularized ridge fit).
3. Run a small `ridge_alpha` sweep — the current value (1.0) was never tuned
   for this feature mix.

If none of these move arm B above arm A, the honest conclusion (per docs/08)
is that this feature representation of the planted signal doesn't carry
information the model can use — which is itself a valid, useful POC
conclusion, not a failure of engineering execution.

### 6. Extraction beyond rules — NER/local-LLM feasibility (Milestone 3 hybrid)

Per `05-technology-decision-matrix.md`, the hybrid rules→NER→local-LLM
pipeline was never built; only the rules baseline. `extraction/llm_stage.py`
raises explicitly rather than silently degrading. A local feasibility check
(what model, what runtime, CPU vs. GPU) is still open
(`docs/14-open-questions.md` items 1-2). Given gap 5 above, this is lower
priority than fixing the feature representation — a better extractor cannot
fix a forecast that doesn't respond to *any* representation of the signal.

### 7. Real-time or batch serving decision

The feature access layer (`FeatureStore.get_features()`) is a callable Python
interface, not a network service. `docs/14-open-questions.md` item 6 defers
the localhost-HTTP-wrapper question. No production serving architecture
decision has been made or is blocked on anything in this POC.

## Non-goals: still excluded, or newly justified in-scope?

Checking every non-goal from `01-poc-scope-and-non-goals.md` against what
was actually built:

| Non-goal | Status |
|---|---|
| Kubernetes/container orchestration | Still excluded — no scaling need demonstrated |
| Message bus/event streaming | Still excluded — batch-only pipeline throughout |
| Online/low-latency feature store | Still excluded — `FeatureStore` remains batch/callable only |
| Automatic model/extractor retraining | Still excluded |
| Multi-region/HA infrastructure | Still excluded |
| Real company notes | Still excluded — this is gap 1 above, the top production blocker |
| Hosted/API LLMs | Still excluded — `extraction/llm_stage.py` raises rather than falling back to one |
| Cloud storage/registries/SaaS observability | Still excluded |
| Enterprise feature store product (Feast, etc.) | Still excluded — the PIT-join pattern was reused directly, not the product |
| Formal security/IAM | Still excluded — no network-facing service exists |
| Human-review workflow tooling | Still excluded as a *product feature* — the review sample scaffold (`scripts/select_review_sample.py`) is a POC evaluation script, not the ticket queue/reviewer UI the non-goal explicitly names |
| Production-grade cost/capacity modeling | Still excluded — no hosted-API usage exists to model |

**No non-goal was silently violated.** The M9-M11 additions (ablation matrix,
lineage, drift, orchestrator) are all listed in the *confirmed scope* (items
7-11 of `01-poc-scope-and-non-goals.md`), not new scope creep.

## What this POC actually settles vs. leaves open

**Settles:** the engineering mechanics work — synthetic generation with
enforced causal separation, PIT-correct feature construction (zero violations,
directly re-checked), lineage tracing (100% resolved at sample scale), a
4-arm rolling-origin experiment harness with a working ablation matrix, and
drift detection with proper calibration and persistence discipline. These are
non-trivial correctness properties and they hold.

**Leaves open:** literally the core business hypothesis. Gate A/B (does real
data have this signal, how early) are untouched. Gate C (extraction accuracy)
is self-scored only. Gate F/G's own headline result (B≈A) is not a positive
finding at current configuration. Gate H (does it matter) has no answer.
