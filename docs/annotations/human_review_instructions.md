# Human review instructions (docs/16 Layer 2a)

Purpose: get one macro-F1 number for the extraction pipeline that is **not**
self-scored by the same process that wrote the extractor. This closes part of
Gate C (extraction validity) from the Phase One research report.

## Who should do this

Someone who did **not** write the extraction rules ([src/dsfs/extraction/rules.py](../../src/dsfs/extraction/rules.py)).
If no second person is available, skip this and say so explicitly in the M12
findings report — do not let the provisional/self-scored number stand in for it silently.

## Steps

1. Generate a dataset if you haven't already:
   ```
   dsfs-generate
   ```
2. Select a sample:
   ```
   python scripts/select_review_sample.py --n 50
   ```
   This writes `data/annotations/human_review_sample.json` — 50 notes chosen
   deterministically from D1, each with a placeholder `expected` block.
3. Open the file. For **each** case:
   - Read only `evidence.raw_text`. Do **not** look at the generator's ground
     truth (`data/raw/d1_note_ground_truth.jsonl`) or the extractor's output —
     that would make the review circular, not independent.
   - Replace the placeholder `expected` block with your own judgment: what
     signal (if any) does this note assert, in what direction, with what
     certainty/conditionality, magnitude, and effective dates?
   - Set `decision` to `"PASS"` if you found an actionable signal, `"NO_SIGNAL"`
     if the note has no forecast-relevant content, or `"REVIEW"` if it's
     genuinely ambiguous even to you.
   - If `decision != "PASS"`, keep a real `abstention_reason` (e.g.
     `"no_signal"` or a short free-text reason) — replace the `REVIEWER_TODO`
     placeholder text.
   - If you assert a field's value (i.e. it's not `null`/`UNKNOWN`/`NA`/`NONE`),
     add a `field_evidence` entry for it: the exact character span in
     `raw_text` that supports your reading. See any case in
     [d2_starter.json](../../data/annotations/d2_starter.json) for the shape.
   - Replace `annotator_ids` with your own identifier.
   - Leave `adjudication_state` as `"single"` (one independent reviewer — not
     a double-blind adjudication).
4. Score it with the existing evaluation CLI — no new tooling needed:
   ```
   dsfs-evaluate --dataset data/annotations/human_review_sample.json --split dev
   ```
   Because `label_origin="human"` and `adjudication_state="single"` (not
   `"draft"`), the report's `report.md` will show this cohort as
   `natural_prevalence / human_single`, distinct from the `challenge /
   provisional` cohort that `d2_starter.json` produces. That distinction is
   what makes this an independent check rather than a repeat of the
   self-scored number.

## What this does and does not establish

- **Does establish:** an independent estimate of extraction macro-F1 /
  field accuracy on real generator output, not written or reviewed by the
  extractor's author.
- **Does not establish:** anything about real company notes (Gate A/B remain
  out of scope — see [docs/16-revised-execution-plan.md](../16-revised-execution-plan.md)).
- Sample size is 50, well below the docs/09 proposed 800-note minimum —
  report this as a mechanics/direction check, not a precise estimate.
