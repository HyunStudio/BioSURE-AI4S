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
from biosure.prospective_audit import evaluate_manifest
from biosure.learned_upstream_audit import evaluate_upstream_manifest
from biosure.schema import canonical_bytes, loads_json
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
    ooc_pdf_audit = {'sources': 0, 'attempted_units': 0, 'native_error_units': 0,
                     'biosure_exact_auto': 0, 'biosure_incorrect_auto': 0,
                     'biosure_abstentions': 0, 'copy_exact_auto': 0,
                     'diff_review_records': 0, 'learned_lexical_alert_records': 0}
    for pmcid in ('PMC5562747', 'PMC7170869'):
        inputs = loads_json((root / f'fixtures/ooc_pdf_{pmcid}_inputs.json').read_text(encoding='utf-8'))
        decisions = decide_inputs(inputs, replay['model'])
        gold = loads_json((root / f'fixtures/ooc_pdf_{pmcid}_gold.json').read_text(encoding='utf-8'))
        result = score_decisions(decisions, gold)
        if result != loads_json((root / f'results/ooc_pdf_{pmcid}.json').read_text(encoding='utf-8')):
            raise ValueError(pmcid + ' OoC PDF audit frozen result mismatch')
        ooc_pdf_audit['sources'] += result['sources']
        ooc_pdf_audit['attempted_units'] += result['cases']
        ooc_pdf_audit['native_error_units'] += result['native_error_cases']
        ooc_pdf_audit['biosure_exact_auto'] += result['biosure']['exact_auto']
        ooc_pdf_audit['biosure_incorrect_auto'] += result['biosure']['incorrect_auto']
        ooc_pdf_audit['biosure_abstentions'] += result['biosure']['abstentions']
        ooc_pdf_audit['copy_exact_auto'] += result['direct_copy']['exact_auto']
        ooc_pdf_audit['diff_review_records'] += result['diff_review']['manual_review_records']
        ooc_pdf_audit['learned_lexical_alert_records'] += result['learned_review']['native_error_cases_with_lexical_alerts']
    if ooc_pdf_audit != {'sources': 2, 'attempted_units': 4, 'native_error_units': 2,
                         'biosure_exact_auto': 0, 'biosure_incorrect_auto': 0,
                         'biosure_abstentions': 4, 'copy_exact_auto': 4,
                         'diff_review_records': 2, 'learned_lexical_alert_records': 0}:
        raise ValueError('OoC PDF audit expected counts mismatch')
    three_source_pdf_audit = {
        'schema_version': 'biosure.three-source-pdf-audit/1.0', 'sources': 0,
        'attempted_units': 6, 'scorable_units': 0, 'observed_reference_discrepancy_units': 0,
        'biosure_exact_auto': 0, 'biosure_incorrect_auto': 0, 'biosure_abstentions': 0,
        'copy_exact_auto': 0, 'copy_incorrect_auto': 0, 'diff_review_records': 0,
        'learned_lexical_alert_records': 0,
        'unscorable_units': [{'case_id': 'PMC12158725-abstract',
                              'reason': 'complete abstract extends beyond article page 1'}],
        'scope': 'Three internally preselected CC BY sources; JATS/rendered-page one-agent gold, '
                 'no independent adjudication or timed user comparison.'}
    for pmcid in ('PMC12078732', 'PMC12300027', 'PMC12158725'):
        inputs = loads_json((root / f'fixtures/ooc_pdf_{pmcid}_inputs.json').read_text(encoding='utf-8'))
        decisions = decide_inputs(inputs, replay['model'])
        gold = loads_json((root / f'fixtures/ooc_pdf_{pmcid}_gold.json').read_text(encoding='utf-8'))
        result = score_decisions(decisions, gold)
        if result != loads_json((root / f'results/ooc_pdf_{pmcid}.json').read_text(encoding='utf-8')):
            raise ValueError(pmcid + ' three-source PDF audit frozen result mismatch')
        three_source_pdf_audit['sources'] += result['sources']
        three_source_pdf_audit['scorable_units'] += result['cases']
        three_source_pdf_audit['observed_reference_discrepancy_units'] += result['native_error_cases']
        three_source_pdf_audit['biosure_exact_auto'] += result['biosure']['exact_auto']
        three_source_pdf_audit['biosure_incorrect_auto'] += result['biosure']['incorrect_auto']
        three_source_pdf_audit['biosure_abstentions'] += result['biosure']['abstentions']
        three_source_pdf_audit['copy_exact_auto'] += result['direct_copy']['exact_auto']
        three_source_pdf_audit['copy_incorrect_auto'] += result['direct_copy']['incorrect_auto']
        three_source_pdf_audit['diff_review_records'] += result['diff_review']['manual_review_records']
        three_source_pdf_audit['learned_lexical_alert_records'] += result['learned_review']['native_error_cases_with_lexical_alerts']
    if three_source_pdf_audit != loads_json((root / 'results/three_source_pdf_audit.json').read_text(encoding='utf-8')):
        raise ValueError('three-source PDF audit aggregate mismatch')
    prospective_manifest = loads_json((root / 'fixtures/prospective_ooc_manifest.json').read_text(encoding='utf-8'))
    prospective_replay = evaluate_manifest(prospective_manifest, root, replay['model'])
    if canonical_bytes(prospective_replay['summary']) != (root / 'results/prospective_ooc_audit.json').read_bytes():
        raise ValueError('prospective OoC PDF audit aggregate mismatch')
    if canonical_bytes(prospective_replay['decisions']) != (root / 'results/prospective_ooc_decisions.json').read_bytes():
        raise ValueError('prospective OoC PDF audit decisions mismatch')
    prospective = prospective_replay['summary']['overall']
    prospective_ooc_audit = {
        'attempted_sources': prospective['attempted_sources'],
        'attempted_units': prospective['attempted_units'],
        'scorable_units': prospective['scorable_units'],
        'observed_reference_discrepancy_units': prospective['native_error_cases'],
        'biosure_exact_auto': prospective['biosure']['exact_auto'],
        'biosure_incorrect_auto': prospective['biosure']['incorrect_auto'],
        'biosure_abstentions': prospective['biosure']['abstentions'],
        'copy_exact_auto': prospective['direct_copy']['exact_auto'],
        'diff_review_records': prospective['diff_review']['manual_review_records'],
        'learned_lexical_alert_records': prospective['learned_review']['native_error_cases_with_lexical_alerts'],
    }
    upstream_replay = evaluate_upstream_manifest(prospective_manifest, root, replay['model'])
    if canonical_bytes(upstream_replay) != (root / 'results/learned_upstream_audit.json').read_bytes():
        raise ValueError('learned upstream source audit mismatch')
    compared = upstream_replay['summary']['overall']
    learned_upstream_audit = {
        'sources': compared['attempted_sources'],
        'held_out_sources': upstream_replay['summary']['held_out']['eligible_sources'],
        'units': compared['compared_units'],
        'learned_rank_correct': compared['learned']['ranking_correct_units'],
        'difflib_rank_correct': compared['difflib']['ranking_correct_units'],
        'token_dice_rank_correct': compared['token_dice']['ranking_correct_units'],
        'direct_copy_exact': compared['direct_copy']['exact_units'],
        'reversed_reference_exact': compared['reversed_reference_failure_control']['exact_units'],
        'proposal_exact': compared['learned']['proposal_exact_units'],
        'proposal_abstained': compared['learned']['proposal_abstained_units'],
    }
    return {"passed": True, "sets": measured, "workflow_examples": batch["summary"],
            'ml': ml, 'native_pilot': pilot, 'ooc_pdf_audit': ooc_pdf_audit,
            'three_source_pdf_audit': three_source_pdf_audit,
            'prospective_ooc_audit': prospective_ooc_audit,
            'learned_upstream_audit': learned_upstream_audit,
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
