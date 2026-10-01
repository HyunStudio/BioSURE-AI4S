"""Offline verification; never updates frozen expectations to fit the result."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.batch import run_batch
from biosure.evaluate import decide_case, score_case, summarize
from biosure.native_pilot import decide_inputs, score_decisions
from biosure.schema import loads_json
from scripts.evaluate_ml import evaluate


def verify(root: Path) -> dict:
    root = root.resolve()
    measured = {}
    expected = {"synthetic": {"cases": 8, "sources": 2, "exact": 2, "incorrect": 0, "abstentions": 6},
                "article": {"cases": 9, "sources": 3, "exact": 3, "incorrect": 0, "abstentions": 6},
                "stress": {"cases": 168, "sources": 12, "exact": 24, "incorrect": 12, "abstentions": 132}}
    for name, prefix in (("synthetic", ""), ("article", "article_"), ("stress", "stress_")):
        cases, gold = root / "fixtures" / (prefix + "challenge"), root / "fixtures" / (prefix + "gold")
        paths = sorted(cases.glob("*.json"))
        if {p.name for p in paths} != {p.name for p in gold.glob("*.json")}:
            raise ValueError(name + " challenge/gold pairing mismatch")
        decisions = [decide_case(p) for p in paths]
        result = {"mode": "candidate_dependent_public_evaluation",
                  **summarize([score_case(r, gold / p.name) for r, p in zip(decisions, paths)])}
        measured[name] = {"cases": result["cases"], "sources": result["source_graphs"],
                          "exact": result["exact_auto"], "incorrect": result["incorrect_auto"],
                          "abstentions": result["abstentions"]}
        if measured[name] != expected[name]:
            raise ValueError(name + " expected counts mismatch")
        if name == "stress" and result != loads_json((root / "results/stress_summary.json").read_text(encoding="utf-8")):
            raise ValueError("stress frozen summary mismatch")
    samples = loads_json((root / "fixtures/workflow_examples.json").read_text(encoding="utf-8"))
    batch = run_batch(samples)
    wants = [("AUTO_REPAIR", "CANDIDATE_PROPOSED"), ("AUTO_REPAIR", "CANDIDATE_PROPOSED"),
             ("ABSTAIN", "NO_CHANGE"), ("ABSTAIN", "UNSUPPORTED_DIFFERENCE"),
             ("ABSTAIN", "BOUNDARY_OMISSION"), ("ABSTAIN", "AMBIGUOUS_REFERENCE")]
    if len(samples) != len(wants):
        raise ValueError("workflow sample count mismatch")
    for sample, result, wanted in zip(samples, batch["results"], wants):
        if (result["decision"]["action"], result["adapter_status"]) != wanted:
            raise ValueError("workflow action mismatch")
        if wanted[0] == "AUTO_REPAIR" and result["selected_paragraphs"] != sample["reference_paragraphs"]:
            raise ValueError("workflow normalized output mismatch")
        if wanted[0] != "AUTO_REPAIR" and result["selected_paragraphs"] is not None:
            raise ValueError("workflow unexpected applied output")
    corpus = loads_json((root / 'fixtures/ml_corpus.json').read_text(encoding='utf-8'))
    replay = evaluate(corpus)
    if replay != loads_json((root / 'results/ml_evaluation.json').read_text(encoding='utf-8')):
        raise ValueError('ML frozen evaluation mismatch')
    if replay['model'] != loads_json((root / 'fixtures/ml_model.json').read_text(encoding='utf-8')):
        raise ValueError('ML frozen model mismatch')
    correspondence = replay['held_out']['correspondence']
    best = replay['held_out']['learned_minus_best_lexical']['baseline']
    ml = {'sources': {'train': len(replay['split']['train_sources']),
                      'dev': len(replay['split']['dev_sources']),
                      'test': len(replay['split']['test_sources'])},
          'learned_correct': correspondence['learned_logistic']['correct'],
          'best_lexical_correct': correspondence[best]['correct'],
          'scope': 'Constructed alterations on unseen CC BY 4.0 article sources; no natural-error superiority claim.'}
    pilot_inputs = loads_json((root / 'fixtures/native_pilot_inputs.json').read_text(encoding='utf-8'))
    # The first phase has no path or argument for gold. Only its sealed output
    # reaches the scorer, which opens the separately frozen adjudication.
    pilot_decisions = decide_inputs(pilot_inputs, replay['model'])
    pilot_gold = loads_json((root / 'fixtures/native_pilot_gold.json').read_text(encoding='utf-8'))
    pilot_result = score_decisions(pilot_decisions, pilot_gold)
    if pilot_result != loads_json((root / 'results/native_pilot.json').read_text(encoding='utf-8')):
        raise ValueError('native pilot frozen result mismatch')
    pilot = {'sources': pilot_result['sources'], 'cases': pilot_result['cases'],
             'native_error_cases': pilot_result['native_error_cases'],
             'biosure_exact_auto': pilot_result['biosure']['exact_auto'],
             'biosure_incorrect_auto': pilot_result['biosure']['incorrect_auto'],
             'copy_exact_auto': pilot_result['direct_copy']['exact_auto'],
             'copy_incorrect_auto': pilot_result['direct_copy']['incorrect_auto']}
    return {"passed": True, "sets": measured, "workflow_examples": batch["summary"],
            'ml': ml, 'native_pilot': pilot,
            "scope": "Implementation replay only; not an independent user study, reference authentication or biological validation."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.package_root), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
