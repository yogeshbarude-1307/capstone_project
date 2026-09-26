# 15 — Extraction Evaluation Workflow (Milestone 4)

## Implemented scope

`src/dsfs/evaluation/` contains the D2 annotation contract, dataset validation,
metric calculations, scenario-isolated extraction runner, and local report
writer. It does not import D1 generator truth into labels or metric computation,
modify the extractor to fit D2, or append evaluation predictions to the signal
ledger. Forecast evaluation remains a separate later milestone.

`data/annotations/d2_starter.json` is a **40-note development challenge set**
with **assistant-drafted, provisional labels**. It includes all signal types,
ten no-signal cases, paraphrases, negation, conditionality, scalar magnitudes,
calendar references, unresolved/ambiguous entities, stale references, and a
two-note reversal scenario. Some familiar constructions are controls. This is
not a blind held-out test, human gold, or a natural-prevalence sample. It is
intentionally smaller than the proposed 800–1,500-note D2 target.

## Run locally

From the repo root, after the source-checkout setup in `README.md`:

```bash
python -m dsfs.evaluation.pipeline
python -m dsfs.evaluation.pipeline --dataset data/annotations/d2_reviewed.json --split test --require-gold
```

The second command is for a future reviewed dataset; that file is not supplied.
`--require-gold` rejects development splits, any provisional labels, and test
sets with fewer than 20% double-annotated/adjudicated cases. Provenance is
declared metadata, not proof of reviewer independence. The size target is
reported separately; a small reviewed set does not become statistically strong
merely by satisfying the review metadata gate.

Optional arguments: `--output-dir PATH` and `--magnitude-tolerance NUMBER`.
The latter is a nonnegative absolute tolerance in the annotated magnitude's
unit (default `1e-6`); units must still match exactly. No packages, models, or
data are downloaded by this command.

Each run writes `reports/extraction/eval-<fingerprint>/`:

| Artifact | Purpose |
|---|---|
| `dataset_snapshot.json` | Canonical frozen inputs, labels, source hashes, groups, and reviewer metadata |
| `predictions.jsonl` | Actual extraction results, with deterministic run identity and processing clock |
| `quarantine.jsonl` | Rejected output diagnostics; empty when there are no rejections |
| `report.json` | Complete metrics, counts/denominators, per-source errors, versions and configuration |
| `report.md` | Readable results, field precision/recall/accuracy, error taxonomy and limitations |

The fingerprint includes the canonical dataset, selected split, metric config,
and actual Python/schema source fingerprint. Processing time is explicitly
simulated as the latest selected source availability plus one second. Identical
reruns reproduce their artifacts; changed content cannot overwrite an existing
bundle. Runtime/dependency versions are recorded. These are local single-writer
artifacts, not a transactional experiment registry.

## Annotation contract and review procedure

The authoritative typed format is `evaluation/annotations.py`; its exported
JSON Schema is `docs/annotations/d2_dataset.schema.json` (checked for parity in
tests). It is an annotation contract, separate from the three pipeline wire
contracts in `docs/schemas/`.

Each case contains immutable `evidence`, `scenario_id`, `template_group`,
`split`, `sample`, challenge `tags`, label provenance, `expected`,
`scored_fields`, and per-field `field_evidence` character spans.

1. Review the note's meaning without looking at extractor predictions or D1
   oracle labels. Label what the source says, not future demand or a desired
   feature value. Review the ontology especially carefully for denied changes,
   cancellations, inventory, supply constraints, and ambiguous dates.
2. Correct the expected fields and support spans. Explicit null/UNKNOWN values
   mean the note does not justify an assertion. If a field cannot yet be
   adjudicated, remove it from `scored_fields`; do not invent a precise label.
   Asserted, scored fields require nonempty in-bounds support spans. Entity
   labels use the supplied canonical master list; the starter's entity IDs
   also appear in the note text. Entity alias/metadata-only grounding requires
   a future extension, not invented text spans.
3. Record actual reviewers in `annotator_ids` and change `label_origin` to
   `human` only after human annotation. Use `single` for one reviewer, `agreed`
   for two distinct reviewers who agree, or `resolved` with two reviewers and
   an `adjudicator_id` after resolving a disagreement. Never relabel an
   assistant draft as human-adjudicated without that work.
4. Keep related notes in one `scenario_id` and all shared templates/paraphrases
   in one `template_group`. No scenario/template group may cross a split or
   sampling cohort. Exact duplicate text is also rejected across splits.
   Extraction uses only source evidence and master entities within each
   scenario, so unrelated scenarios cannot create spurious reversal links.
5. Build a new, independently authored **test** set for a held-out measurement.
   The inspected starter remains **dev**, even after label corrections. Expand
   toward the proposed target or explicitly document a smaller project scope.
   Keep natural-prevalence and balanced/challenge cohorts distinct.
6. Save the reviewed dataset with a new dataset version and rerun. Review
   `report.json`'s per-source diagnostics; retain the frozen bundle for each
   result. Fix extractor errors against development data, then evaluate once
   on a genuinely held-out test snapshot.

`expected.supersedes_source_id` refers to an earlier note in the same scenario;
runtime signal IDs are resolved back to source IDs before comparison. This
reference cannot point to evidence unavailable when the reversal was authored.
Abstention labels carry an explicit reason; the report breaks decision
correctness down by those reason labels. It does not score free-text reason
paraphrases as if exact string equality were semantic agreement.

## Metric definitions

| Metric | Definition / denominator |
|---|---|
| Actionable event P/R/F1 | Only `PASS` non-`NO_SIGNAL` outputs are actionable. A `REVIEW` candidate is withheld. Per-type TP/FP/FN compare against expected actionable events. Macro-F1 averages classes with gold or predicted support; absent classes are not assigned perfect scores. |
| Type/direction classification | Candidate-field accuracy and macro-F1, independent of the actionable decision; only explicitly scored fields contribute. |
| Field accuracy | Exact matches / annotated, scored cases; nullable fields include absence matches. A missing/malformed output is an error even if the expected field is null. |
| Field precision/recall | Correct positive assertions / predicted or expected assertions respectively. Null, UNKNOWN, NA, NONE, NO_SIGNAL, and false negation are non-assertions. Numeric zero remains an assertion. Magnitude uses the configured tolerance; units match exactly. |
| Negation / conditional subsets | Classwise P/R/F1 on cases tagged `negation` or `conditional`, including negative controls. |
| Temporal exact match / IoU | Only gold cases with both interval endpoints. Exact match requires both endpoints; IoU uses half-open intervals. Missing predicted time scores zero. |
| Entity accuracy / unresolved rate | Separate denominators for known gold keys and gold-null keys; missing output does not earn correct-abstention credit. |
| Abstention P/R | Positive decision is `NO_SIGNAL` or `REVIEW`; missing/failed output is not a deliberate abstention. Exact three-way decision classification is also reported. |
| Evidence-span coverage | Annotated supported fields whose spans are contained in a valid prediction citation / annotated supported fields. This is coverage, not citation specificity. |
| Unsupported-inference rate | Predicted asserted, scored fields lacking both a matching annotated value and citation coverage / predicted asserted, scored fields. This is annotation-relative grounding, not an independent entailment model. Supersession is scored separately via contextual source links. |
| Schema valid-record rate | Independently JSON-schema-valid outputs / all output attempts, including quarantined attempts. Missing outputs are separately counted and remain semantic misses. |
| Semantic cross-field failures | Model-invalid but schema-valid returned records / schema-valid returned records. Construction quarantines without a returned record cannot be classified further and are explicitly counted as unclassified construction failures. |
| Duplicate outputs | Extra outputs for the same source; no best prediction is cherry-picked. Every duplicate actionable output is an FP and the unmatched gold event remains an FN. Cross-note event deduplication is future work. |

Every ratio includes its numerator and denominator. Zero denominators produce
JSON null / Markdown `N/A`. Error categories overlap and count affected notes,
not mutually exclusive partitions. Challenge/natural-prevalence samples and
provisional/human-single/human-adjudicated labels are separate report views;
they are never merged into one headline score.

## Initial provisional findings

On the 40-note starter, the unchanged `rules-v0.2.0` extractor yields 100%
schema-valid output, actionable-event macro-F1 **0.4158**, type accuracy **0.85**,
and direction accuracy **0.65**. The draft labels identify 10 missed actionable
events and 14 direction mismatches. These are useful development diagnostics,
not independently validated accuracy estimates. Entity and calendar results
only cover the supplied-ID/calendar-control cases; they do not establish
general entity recognition or temporal-language accuracy.

Milestone 4's evaluation machinery is implemented and tested. Independent
human annotation, adjudication and a held-out D2 report remain outstanding.
Milestones 5–6 can proceed from the verified signal contracts while that review
is performed; their dependency is Milestone 3, not a claim of strong D2 scores.
