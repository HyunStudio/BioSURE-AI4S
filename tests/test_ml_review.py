"""Real learned correspondence; no probability can authorize replacement."""
import math
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
