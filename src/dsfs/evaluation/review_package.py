"""Blind 35+15 reviewer package. Labels are deliberately unfinished."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random
import re
from dsfs.config import REPO_ROOT
from dsfs.evaluation.annotations import AnnotationDataset
from dsfs.extraction.extractor import DEFAULT_EXTRACTOR_VERSION

def prepare_review_package(notes, known_entities, output_dir: Path, *, seed=20261005):
    _PLACEHOLDER_EXPECTED = {"signal_type":"NO_SIGNAL","direction":"NA","impact_channel":"UNKNOWN",
        "business_certainty":"UNKNOWN","conditionality":"NONE","condition_text":None,"negated":False,
        "magnitude_value":None,"magnitude_unit":None,"effective_start":None,"effective_end":None,
        "forecast_key":None,"supersedes_source_id":None,"decision":"NO_SIGNAL",
        "abstention_reason":"REVIEWER_TODO: independently label this note."}
    if len(notes) < 35:
        raise ValueError("Review package needs at least 35 natural-prevalence notes")
    rng=random.Random(seed)
    selected=rng.sample(notes,35)
    from dsfs.synth.config import GeneratorConfig
    from dsfs.synth.generator import generate_dataset
    # New held-out challenge evidence; do not recycle development labels/notes.
    challenge_dataset=generate_dataset(GeneratorConfig(seed=seed+1,n_entities=len(known_entities),
        explicit_dates=False,entity_paraphrase_mode="none"))
    signal_notes=[n for n in challenge_dataset.d1_notes if "Plan reference" in n.raw_text]
    challenge=rng.sample(signal_notes,15)
    # Guarantee lifecycle/linguistic challenges instead of relying on prevalence.
    selected_ids={n.source_id for n in challenge}
    predicates=(lambda t:"cancelled" in t or "no longer" in t,
                lambda t:"not increasing" in t or "no increase" in t,
                lambda t:"if " in t or "pending " in t)
    for slot,predicate in enumerate(predicates):
        if any(predicate(n.raw_text.lower()) for n in challenge): continue
        candidates=[n for n in signal_notes if predicate(n.raw_text.lower()) and n.source_id not in selected_ids]
        if not candidates: raise ValueError("Challenge generator did not provide required challenge type")
        replacement=rng.choice(candidates)
        selected_ids.discard(challenge[slot].source_id);selected_ids.add(replacement.source_id)
        challenge[slot]=replacement
    natural_ids={n.source_id for n in selected}
    cases=[];context={}
    def scenario(note):
        refs=re.findall(r"plan reference ([\w-]+)",note.raw_text,re.I)
        return "natural-"+(refs[0] if len(set(refs))==1 else note.source_id)
    def blank(evidence,group,sample,tags):
        return {"evidence":evidence,"scenario_id":group,"template_group":group,"split":"test",
                "sample":sample,"tags":tags,"label_origin":"human",
                "annotator_ids":["REVIEWER_TODO_REPLACE_WITH_YOUR_ID"],"adjudication_state":"single",
                "adjudicator_id":None,"ambiguity_flag":False,"expected":copy.deepcopy(_PLACEHOLDER_EXPECTED),
                "scored_fields":[],"field_evidence":{}}
    for note in selected:
        group=scenario(note)
        cases.append(blank(note.model_dump(mode="json"),group,"natural_prevalence",[]))
        earlier=[n for n in notes if n.source_id not in natural_ids and scenario(n)==group and n.available_at<=note.authored_at]
        existing={v["source_id"] for v in context.get(group,[])}
        context.setdefault(group,[]).extend(n.model_dump(mode="json") for n in earlier if n.source_id not in existing)
    challenge_ids={n.source_id for n in challenge}
    for i,note in enumerate(challenge):
        group="challenge-"+scenario(note)
        tags=[] if "Effective from" in note.raw_text else ["vague_time"]
        if i==1:
            text=note.raw_text+" Plan reference EVT-UNRESOLVED."
            note=note.model_copy(update={"raw_text":text,"source_revision":"challenge-ref-v1",
                "content_hash":"sha256:"+hashlib.sha256(text.encode()).hexdigest()})
            tags.append("ambiguous_event_reference")
        if i%3==0:
            note=note.model_copy(update={"entity_mentions_raw":["the account discussed earlier"]})
            tags.append("ambiguous_entity")
        lower=note.raw_text.lower()
        if "if " in lower or "pending " in lower:tags.append("conditional")
        if "cancelled" in lower or "no longer" in lower:tags.append("reversal")
        if "not increasing" in lower or "no increase" in lower:tags.append("negation")
        cases.append(blank(note.model_dump(mode="json"),group,"challenge",tags))
        context[group]=[n.model_dump(mode="json") for n in challenge_dataset.d1_notes if "challenge-"+scenario(n)==group
                        and n.source_id not in challenge_ids and n.available_at<=note.authored_at]
    payload={"schema_version":"d2-0.2.0","dataset_id":"independent-review-v1",
             "description":"Blind held-out 35 natural-prevalence and 15 challenge notes. Unfinished, not scored.",
             "known_entities":sorted(set(known_entities)|set(challenge_dataset.entities)),
             "cases":cases,"scenario_context":context}
    AnnotationDataset.model_validate(payload)
    output_dir.mkdir(parents=True,exist_ok=True)
    path=output_dir/"review_dataset.json"
    path.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    (output_dir/"REVIEW_INSTRUCTIONS.md").write_text(
        "# Independent review\n\nFrozen extractor: "+DEFAULT_EXTRACTOR_VERSION+"\n\n"
        "Read source text, timestamps, entity mentions and preceding scenario_context. "
        "No predictions or generator truth are provided. Replace every REVIEWER_TODO, "
        "fill expected, scored_fields (the fields you can judge), and field_evidence spans. "
        "Set your annotator ID and keep adjudication_state=single. Do not claim double adjudication.\n\n"
        "Save completed labels to a new working copy outside the immutable run. Run `dsfs-evaluate --dataset <completed-copy.json> --split test --output-dir reports/independent-reviews/<run-id>`. "
        "Natural-prevalence and challenge cohorts are scored separately. "
        "Do not change extraction rules after reading held-out labels; a subsequent version needs a new holdout.\n",
        encoding="utf-8")
    from dsfs.evaluation.report import code_snapshot
    return {"status":"pending_independent_reviewer","path":str(path),"counts":dict(Counter(c["sample"] for c in cases)),
            "extractor_version":DEFAULT_EXTRACTOR_VERSION,"seed":seed,
            "code_sha256":code_snapshot()}
