# Realignment findings and acceptance status

The technical realignment and frozen study are complete. The positive oracle gate failed: the full oracle and extracted representations **worsened** error under the frozen model policy. Independent human extraction accuracy remains **unavailable** until a person labels the prepared 50-note package.

## Verified environment and evidence

- Windows, Python 3.14.7; editable virtual-environment installation with runtime, test and server dependencies. Exact versions are in `requirements-tested.txt` and each run manifest.
- Revalidated original checkout: **316 passed, 1 failed**. Timestamp format validation lacked its optional RFC3339 dependency. Installation now includes `jsonschema[format]`.
- Final suite: **337 passed**, one Starlette test-client deprecation warning. `pip check` found no dependency conflicts.
- Live headless Edge verification rendered four forecast cards, 13 extraction field rows, freshness and lineage without console errors.
- **13 completed study runs**, with **501 artifact hash entries checked and zero mismatches**. The frozen source hash remained unchanged across evaluation.
- Study evidence: `reports/studies/20261005T083131548825/`; frozen source archive: `source-snapshot.zip`.
- Frozen code SHA-256: `2f74377d2782ac354ccbe40f3fcd0f1effb6e4e50466874a9beee8f595c20462`.

## Forecast results

Development seeds 1-3 preceded the freeze. Evaluation seeds 101-105 used 40 accounts x 104 weeks, four horizons, trailing 52-week target windows, Ridge alpha 1, and training-only numeric standardization. Each arm has 39,200 paired account/cutoff/horizon outcomes. MASE uses the rolling training-only one-week naive denominator; no denominator was unavailable in this study.

| Arm | MASE | MAE | Bias (prediction - actual) | MASE lift vs A | 95% paired CI |
|---|---:|---:|---:|---:|---:|
| A | 1.3495 | 25.73 | -1.20 | baseline | n/a |
| B | 1.3934 | 26.68 | -0.45 | -3.25% | [-5.20%, -1.50%] |
| C | 1.3924 | 26.66 | -0.46 | -3.18% | [-5.20%, -1.32%] |
| D | 1.5231 | 29.07 | -1.43 | -12.87% | [-13.81%, -11.88%] |

A is tabular-only; B uses generator interpretations through shared aggregation; C retrieves extracted features through real localhost HTTP; D assigns features to different accounts at the same cutoff. Confidence intervals use 1,000 resamples of complete paired account trajectories within each seed. Horizon and exposure breakdowns are in each manifest under `steps.forecast_segments`.

Both B and C have lift intervals entirely below zero. The shuffled control is also worse; it provides no indication of positive lift from broken account alignment. These results support revisiting the representation/model policy before adding NER or a local LLM.

### Representation diagnostic

All seven implemented ablations ran on ten accounts for each evaluation seed. Across those five runs, approximate mean MAE was 26.89 for baseline A, 25.83 for the oracle magnitude ablation (presence + direction + magnitude), and 27.52 for the full oracle representation. Additional timing/modality/source features therefore deserve scrutiny in the next development cycle. This is a diagnostic comparison, not a replacement for the negative 40-account headline result or a claim that a newly selected model passed a fresh holdout. The per-seed matrices include paired trajectory intervals.

### Noiseless mechanics check

In the independent planted, fully materialized scenario, baseline MAE was 19.70; oracle and extracted MAE were both 1.34. This verifies usable early information through corrected overlap/percentage semantics. It does not establish value for the broader noisy generator.

## Serving, freshness, extraction and lineage

- All study forecasts consumed extracted features through HTTP with no file fallback: 17 requests per 40-account run and 5 per ten-account run. Provider tests cover real sockets, contract equality, invalid requests and unavailable services.
- Normal simulated hourly publication had **zero one-hour breaches** in all 13 runs. Each delayed-batch demonstration recorded **one breach**. Publication latency and note recency remain separate from actual execution time.
- Extraction schema conformance was **100%** in all study runs, with no construction/schema quarantine. REVIEW records persist and are excluded from predictive features. Schema validity does not establish semantic accuracy.
- Every sampled lineage trace resolved: **10/10 per run**. The manifest pins the complete snapshot, including rejection artifacts when present.
- Earlier development artifacts remain available. A prototype run exposed four invalid cancellation intervals; the latent lifecycle was corrected before the frozen study, and its rejected records were preserved.

## Matched writing-change drift

The controlled experiment used seed 901 with 40 accounts x 104 weeks. It deliberately increased signal strength and reduced noise relative to the headline generator; its complete configuration is in `writing_change.json`. Changed and unchanged corpora share identical business events and demand. Only post-injection writing and physical source revisions differ.

- Writing change: week 60; persistent alert: week 68.
- Degradation confirmation: week 82, after fully mature four-week outcomes.
- **Warning lead time: 14 weeks**; detection latency: 8 weeks.
- **False alerts: 3/10 no-drift runs (30%)**, using seeds 901-910 and the complete fixed alert rule.
- The rule used an eight-week pre-change reference, p < 0.05, effect >=0.3, and two consecutive qualifying probes. Degradation required >10% excess MAE versus matched control in two consecutive mature four-week windows.
- This demonstrates a warning in the declared scenario, while the false-alert rate shows that the current rule needs further operational calibration. Missing alerts/degradation produce unavailable lead time rather than zero or an invented success.
- Full feature/performance windows, both note corpora, paired forecast outcomes and identical demand are preserved in the drift evidence bundle.

## Independent review: remaining acceptance item

The rules-v0.3.0 extractor was frozen before selecting **35 natural-prevalence and 15 challenge notes**. Related cases share lifecycle context. The reviewer package contains source text, timestamps, entity mentions and preceding notes; it contains no generator truth or extractor predictions. Challenge coverage includes vague dates, negation, conditionality, cancellations and ambiguous references.

A separate **cross-model AI draft** from Claude has now been validated and evaluated. It contains all 50 cases with `assistant_draft / draft` provenance, no TODO placeholders, unchanged blind source material, and 341 valid evidence spans. The dashboard reports its natural-prevalence and challenge metrics as provisional diagnostics. This does not complete the independent-person requirement, which remains open.

Provide only these blind materials to the independent reviewer:
- `reports/runs/run-20261005T083131-fdcd6526/reports/review/review_dataset.json`
- The adjacent `REVIEW_INSTRUCTIONS.md`
- Grouped reading copy: `reports/independent-reviews/run-20261005T083131-fdcd6526/READING_COPY.md`

Keep the immutable run unchanged. Save completed labels to a new working copy, replace every TODO, supply evidence spans and nonempty scored fields, and identify the single reviewer. Then run:

```powershell
.\.venv\Scripts\dsfs-evaluate.exe --dataset path\to\completed_review.json --split test --output-dir reports\independent-reviews\run-20261005T083131-fdcd6526
```

The evaluator rejects unfinished labels and reports the natural-prevalence and challenge cohorts separately. The dashboard recognizes a matching, single-review human bundle separately from provisional starter scores. Do not use the older double-adjudication `--require-gold` mode for this cohort. Human accuracy has not been claimed or fabricated.

## Reproduce the dashboard demonstration

Run `./.venv/Scripts/dsfs-server.exe`, open `http://127.0.0.1:8000`, and select **`run-20261005T083131-fdcd6526`** in the run selector. This completed 40-account frozen run includes HTTP evidence, freshness, matched drift, lineage and the blind review package. The latest completed run after `dsfs-study` is a ten-account ablation, so select the specified run for the full demonstration.

The forecast view shows its paired intervals and breakdowns; the extraction view distinguishes the Claude cross-model draft from pending human review; the drift view shows the 14-week lead and 30% false-alert rate. The lineage view supplies a valid Monday cutoff and resolves contributing source spans.

For a newly generated complete demonstration, use `./.venv/Scripts/dsfs-run.exe --config configs/e2e_full.json`. For the complete development/frozen study use `./.venv/Scripts/dsfs-study.exe`. Historical counts and results in documents 00-19 are prior evidence, not this study.

> This synthetic POC evaluates whether early qualitative signals improve forecasts. Positive forecast value is established only when the reported comparison supports it. It does **not** demonstrate that real company account/service/supplier notes contain comparable predictive information, at what prevalence, or with what real lead time. Real-data validation is a required, separate, subsequent gate before any production claim is made.
