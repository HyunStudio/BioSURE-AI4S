"""Real learned correspondence; no probability can authorize replacement."""
import math
import json
from pathlib import Path
import pytest
from biosure import ml_review


def training_rows():
    return [
        {'reference': 'Cells were seeded at 10 mg for 24 hours.', 'observed': 'cells were seeded at 10 mg for 24 hours', 'label': 1},
        {'reference': 'The microfluidic channel was washed twice.', 'observed': 'The microfluidic channel was washed\n twice.', 'label': 1},
        {'reference': 'Viability did not increase after treatment.', 'observed': 'Viability did increase after treatment.', 'label': 1},
        {'reference': 'Cells were seeded at 10 mg for 24 hours.', 'observed': 'The bibliography lists the cited works.', 'label': 0},
        {'reference': 'The microfluidic channel was washed twice.', 'observed': 'Drug response was evaluated after incubation.', 'label': 0},
        {'reference': 'Viability did not increase after treatment.', 'observed': 'The electronic controller maintains fluid flow.', 'label': 0},
    ]


def test_actual_fit_separates_correspondence_without_learning_semantic_approval():
    model = ml_review.train_model(training_rows())
    assert any(abs(value) > 0.01 for value in model['weights'])
    assert ml_review.match_probability(model, 'Cells were seeded at 10 mg for 24 hours.', 'Cells were seeded at 10 mg for 24 hours.') > 0.8
    assert ml_review.match_probability(model, 'Cells were seeded at 10 mg for 24 hours.', 'An unrelated bibliography.') < 0.2
    assert model == ml_review.train_model(training_rows())


@pytest.mark.parametrize('reference,observed,expected', [
    ('Drug at 0.50 mg.', 'Drug at 0.5 mg.', []),
    ('Drug at 1e-3 mg.', 'Drug at 0.001 mg.', []),
    ('Drug at 0.5 mg.', 'Drug at 5 mg.', ['NUMBER_CHANGED']),
    ('Drug at 5 mg.', 'Drug at 5 ug.', ['UNIT_CHANGED']),
    ('Cells did not increase.', 'Cells did increase.', ['NEGATION_CHANGED']),
])
def test_critical_tokens_report_actual_changes_and_decimal_equivalence(reference, observed, expected):
    assert ml_review.critical_changes(reference, observed)['flags'] == expected


def test_model_cannot_apply_unsupported_difference_even_with_high_correspondence():
    model = ml_review.train_model(training_rows())
    payload = {'record_id':'ml', 'reference_paragraphs':['Header.', 'Drug at 0.5 mg.', 'Closing.'],
               'observed_paragraphs':['Header.', 'Drug at 5 mg.', 'Closing.']}
    result = ml_review.review_paragraphs(payload, model)
    assert result['decision']['action'] == 'ABSTAIN'
    assert result['selected_paragraphs'] is None
    middle = result['correspondences'][1]
    assert middle['reference_index'] == 1
    assert middle['flags'] == ['NUMBER_CHANGED']
    assert result['ml_receipt']['model_sha256']
    assert result['correspondences'][1]['observed'] == 'Drug at 5 mg.'


def test_repeated_reference_is_marked_ambiguous_not_authenticated():
    model = ml_review.train_model(training_rows())
    result = ml_review.review_paragraphs({'record_id':'repeat',
        'reference_paragraphs':['Same text.', 'Same text.'], 'observed_paragraphs':['Same text.']}, model)
    assert result['correspondences'][0]['ambiguous'] is True
    assert result['selected_paragraphs'] is None


@pytest.mark.parametrize('mutation', ['nan', 'dimension', 'negative-threshold'])
def test_invalid_numeric_artifacts_fail_closed(mutation):
    model = ml_review.train_model(training_rows())
    if mutation == 'nan': model['weights'][0] = math.nan
    elif mutation == 'dimension': model['weights'].pop()
    else: model['threshold'] = -0.01
    with pytest.raises(ValueError):
        ml_review.match_probability(model, 'A paragraph.', 'A paragraph.')


def test_fit_rejects_outcome_fields_and_single_class():
    with pytest.raises(ValueError):
        ml_review.train_model([{'reference':'a','observed':'a','label':1}])
    with pytest.raises(ValueError):
        ml_review.train_model([{**row,'gold':True} for row in training_rows()])


def test_learned_upstream_proposes_declared_text_but_does_not_approve_changed_content():
    from biosure.learned_upstream import propose_learned
    from biosure.schema import sha256

    model = ml_review.train_model(training_rows())
    payload = {'record_id': 'real-model-proposal',
               'reference_paragraphs': ['Cells were seeded at 10 mg for 24 hours.',
                                        'The microfluidic channel was washed twice.'],
               'observed_paragraphs': ['Cells were seeded at 11 mg for 24 hours.',
                                       'The microfluidic channel was washed twice.']}
    before = repr(payload)
    result = propose_learned(payload, model)
    assert repr(payload) == before
    assert result['proposal_status'] == 'PROPOSED_FOR_REVIEW'
    assert result['proposed_paragraphs'] == payload['reference_paragraphs']
    assert [match['reference_index'] for match in result['correspondences']] == [0, 1]
    assert result['proposal_check']['decision']['action'] == 'ABSTAIN'
    assert result['proposal_check']['selected_paragraphs'] is None
    assert result['upstream_receipt']['model_sha256'] == sha256(model)
    assert result['upstream_receipt']['proposal_sha256'] == sha256(payload['reference_paragraphs'])


def test_learned_upstream_abstains_on_low_confidence_and_repeated_reference():
    from biosure.learned_upstream import propose_learned

    model = ml_review.train_model(training_rows())
    low = {**model, 'threshold': 1.0}
    payload = {'record_id': 'uncertain',
               'reference_paragraphs': ['Cells were seeded at 10 mg for 24 hours.'],
               'observed_paragraphs': ['An unrelated bibliography lists citations.']}
    result = propose_learned(payload, low)
    assert result['proposal_status'] == 'ABSTAIN'
    assert result['proposal_reason'] == 'LOW_CONFIDENCE'
    assert result['proposed_paragraphs'] is None
    assert result['proposal_check'] is None

    repeated = propose_learned({'record_id': 'same',
        'reference_paragraphs': ['Same paragraph.', 'Same paragraph.'],
        'observed_paragraphs': ['Same paragraph.']}, model)
    assert repeated['proposal_status'] == 'ABSTAIN'
    assert repeated['proposal_reason'] == 'AMBIGUOUS_MATCH'


def test_learned_upstream_requires_ordered_unique_alignment():
    from biosure.learned_upstream import propose_learned

    model = ml_review.train_model(training_rows())
    reference = ['Cells were seeded at 10 mg for 24 hours.',
                 'The microfluidic channel was washed twice.']
    result = propose_learned({'record_id': 'reversed', 'reference_paragraphs': reference,
                              'observed_paragraphs': reference[::-1]}, model)
    assert result['proposal_status'] == 'ABSTAIN'
    assert result['proposal_reason'] == 'NON_MONOTONIC_ALIGNMENT'
    assert result['proposed_paragraphs'] is None


def test_learned_abstention_does_not_expose_baseline_repair_as_selected_output():
    from biosure.learned_upstream import propose_learned

    model = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/ml_model.json').read_text(encoding='utf-8'))
    payload = {'record_id': 'review',
               'reference_paragraphs': ['The channel was washed.', 'THE CHANNEL WAS WASHED.', 'Closing paragraph.'],
               'observed_paragraphs': ['The channel was washed.', 'Closing paragraph.']}
    result = propose_learned(payload, model)
    assert result['proposal_status'] == 'ABSTAIN'
    assert result['proposal_reason'] == 'AMBIGUOUS_MATCH'
    assert result['proposal_check'] is None
    assert result['original_workflow_review']['decision']['action'] == 'ABSTAIN'
    for misleading in ('decision', 'selected_paragraphs', 'selected_output', 'receipt', 'request'):
        assert misleading not in result
