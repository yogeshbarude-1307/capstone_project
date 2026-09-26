"""Synthetic data generator (Milestone 2, docs/06-synthetic-data-design.md).

Causal generation order — this is the anti-leakage backbone of the whole
project and must never be reordered or shortcut:

    1. entities.py  -> which synthetic entities exist
    2. latent.py    -> a hidden latent business state (HiddenState) AND the
                        knowable subset of it a human could plausibly write
                        about at note time (Knowable) — generated together,
                        but only Knowable ever leaves this step for notes.
    3. notes.py     -> renders note text from Knowable ONLY. Never imports
                        demand.py and never sees HiddenState.
    4. demand.py    -> realizes the demand series from HiddenState ONLY,
                        independently and afterward. Never imports notes.py
                        and never sees rendered note text or signals.
    5. generator.py -> orchestrates 1-4 in this order and writes D0 (tabular
                        demand history) and D1 (notes + ground truth,
                        strictly separate objects) to local storage.

See docs/06-synthetic-data-design.md and the leakage tests in
tests/synth/test_leakage.py for how this ordering is enforced and checked.
"""
