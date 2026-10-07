"""Learned paragraph correspondence, never semantic approval or repair authority.

The model is regularized logistic regression fitted on labeled pairs, not a
hand-coded score advertised as AI. Runtime/training use the standard library.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal, DecimalException

from .schema import sha256
from .workflow import run_workflow

FEATURE_NAMES = ['exact', 'token_dice', 'token_containment', 'trigram_dice',
                 'length_ratio', 'ordered_bigrams', 'number_overlap', 'negation_overlap']
_NUMBER = re.compile(r'(?<![\w.])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?')
_UNIT = re.compile(r'(?<!\w)(?:mg|ng|pg|kg|ug|μg|µg|g|mL|ml|uL|μL|µL|L|mm|nm|um|μm|µm|cm|mM|uM|μM|µM|nM|M|Pa|kPa|Hz|min|hours?|days?|s)(?!\w)')
_NEGATIONS = {'no', 'not', 'never', 'without', 'neither', 'nor'}


def _text(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > 4096:
        raise ValueError('nonempty paragraph of at most 4096 characters required')
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def _numbers(text: str) -> list[str]:
    def normalize(value: str) -> str:
        try:
            sign, digits, exponent = Decimal(value).as_tuple()
        except DecimalException:
            # Extreme exponents stay visible as lexical discrepancies; never crash review.
            return value.casefold()
        if not any(digits):
            return '0'
        digits = list(digits)
        while digits[-1] == 0:
            digits.pop()
            exponent += 1
        return str(Decimal((sign, tuple(digits), exponent)))
    return sorted(normalize(value) for value in _NUMBER.findall(text))


def _negations(text: str) -> list[str]:
    return sorted(word for word in re.findall(r'\w+', text.casefold()) if word in _NEGATIONS)


def _units(text: str) -> list[str]:
    equivalents = {'ug':'μg', 'µg':'μg', 'um':'μm', 'µm':'μm', 'uL':'μL', 'µL':'μL', 'uM':'μM', 'µM':'μM', 'ml':'mL'}
    return sorted(equivalents.get(value, value) for value in _UNIT.findall(text))


def critical_changes(reference: str, observed: str) -> dict:
    reference, observed = _text(reference), _text(observed)
    left = {'numbers': _numbers(reference), 'units': _units(reference), 'negations': _negations(reference)}
    right = {'numbers': _numbers(observed), 'units': _units(observed), 'negations': _negations(observed)}
    flags = [flag for key, flag in [('numbers','NUMBER_CHANGED'), ('units','UNIT_CHANGED'), ('negations','NEGATION_CHANGED')]
             if left[key] != right[key]]
    return {'flags':flags, 'reference_tokens':left, 'observed_tokens':right,
            'scope':'Lexical discrepancy alerts, not biological facts or semantic equivalence.'}


def _dice(left: Counter, right: Counter) -> float:
    total = sum(left.values()) + sum(right.values())
    return 2 * sum((left & right).values()) / total if total else 1.0


def _prepared(text: str) -> dict:
    normalized = _text(text).casefold()
    words = re.findall(r'\w+', normalized)
    return {'text':normalized, 'tokens':Counter(words),
            'trigrams':Counter(normalized[i:i+3] for i in range(max(0,len(normalized)-2))),
            'bigrams':Counter(zip(words, words[1:])), 'numbers':Counter(_numbers(normalized)),
            'negations':Counter(_negations(normalized))}


def _features(left: dict, right: dict) -> list[float]:
    common = sum((left['tokens'] & right['tokens']).values())
    minimum = min(sum(left['tokens'].values()),sum(right['tokens'].values()))
    return [float(left['text'] == right['text']), _dice(left['tokens'],right['tokens']),
            common/minimum if minimum else 0.0, _dice(left['trigrams'],right['trigrams']),
            min(len(left['text']),len(right['text'])) / max(len(left['text']),len(right['text'])),
            _dice(left['bigrams'],right['bigrams']), _dice(left['numbers'],right['numbers']),
            _dice(left['negations'],right['negations'])]


def pair_features(reference: str, observed: str) -> list[float]:
    return _features(_prepared(reference), _prepared(observed))


def _sigmoid(value: float) -> float:
    # Stable even for adversarial, but finite, model/input values.
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


def validate_model(model: dict) -> None:
    keys = {'schema_version','feature_names','weights','bias','threshold','training_rows','training_sha256','fit_parameters'}
    if not isinstance(model,dict) or set(model) != keys or model['schema_version'] != 'biosure.logistic-correspondence/1.0':
        raise ValueError('invalid model schema')
    if model['feature_names'] != FEATURE_NAMES or not isinstance(model['weights'],list) or len(model['weights']) != len(FEATURE_NAMES):
        raise ValueError('invalid model features')
    values = model['weights'] + [model['bias'],model['threshold']]
    if any(type(value) not in (int,float) or not math.isfinite(value) or abs(value) > 100 for value in values):
        raise ValueError('model parameters must be finite bounded numbers')
    if not 0 <= model['threshold'] <= 1 or type(model['training_rows']) is not int or model['training_rows'] < 2:
        raise ValueError('invalid threshold or training count')
    if not isinstance(model['training_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',model['training_sha256']):
        raise ValueError('invalid training digest')


def _probability(model: dict, features: list[float]) -> float:
    return _sigmoid(model['bias'] + sum(weight * feature for weight,feature in zip(model['weights'],features)))


def match_probability(model: dict, reference: str, observed: str) -> float:
    validate_model(model)
    return _probability(model, pair_features(reference, observed))


def train_model(rows: list[dict]) -> dict:
    if not isinstance(rows,list) or not 2 <= len(rows) <= 20000:
        raise ValueError('supply 2 to 20000 labeled training pairs')
    vectors, labels = [], []
    for row in rows:
        if not isinstance(row,dict) or set(row) != {'reference','observed','label'} or type(row['label']) is not int or row['label'] not in (0,1):
            raise ValueError('training pairs require exactly reference, observed and binary label')
        vectors.append(pair_features(row['reference'],row['observed']))
        labels.append(row['label'])
    if set(labels) != {0,1}:
        raise ValueError('both correspondence classes required')
    weights, bias = [0.0] * len(FEATURE_NAMES), 0.0
    epochs, rate, regularization = 400, 0.8, 0.002
    # Class balancing is fit from training ONLY; deterministic full-batch GD.
    counts = Counter(labels)
    sample_weights = [len(labels)/(2*counts[label]) for label in labels]
    for _ in range(epochs):
        gradient, intercept = [0.0] * len(weights), 0.0
        for features,label,sample_weight in zip(vectors,labels,sample_weights):
            error = (_sigmoid(bias + sum(w*x for w,x in zip(weights,features))) - label) * sample_weight
            intercept += error
            for i,feature in enumerate(features):
                gradient[i] += error * feature
        bias -= rate * intercept / len(labels)
        weights = [w - rate * (g/len(labels) + regularization*w) for w,g in zip(weights,gradient)]
    return {'schema_version':'biosure.logistic-correspondence/1.0', 'feature_names':FEATURE_NAMES.copy(),
            'weights':weights, 'bias':bias, 'threshold':0.5, 'training_rows':len(rows),
            'training_sha256':sha256(rows),
            'fit_parameters':{'epochs':epochs,'learning_rate':rate,'l2':regularization,'class_balanced':True}}


def review_paragraphs(payload: dict, model: dict) -> dict:
    validate_model(model)
    original = run_workflow(payload)  # Enforces existing input limits/strict keys.
    references, observations = original['reference_paragraphs'],original['observed_paragraphs']
    prepared_refs, prepared_obs = [_prepared(t) for t in references],[_prepared(t) for t in observations]
    correspondences = []
    for j,observed in enumerate(observations):
        scores = sorted([(_probability(model,_features(left,prepared_obs[j])),i)
                         for i,left in enumerate(prepared_refs)],key=lambda item:(-item[0],item[1]))
        score,index = scores[0]
        margin = score - scores[1][0] if len(scores)>1 else score
        changes = critical_changes(references[index],observed)
        correspondences.append({'observed_index':j,'reference_index':index,
            'reference':references[index],'observed':observed,'probability':score,'margin':margin,
            'above_threshold':score>=model['threshold'],'ambiguous':len(scores)>1 and margin<0.02,
            'flags':changes['flags'],'critical_tokens':changes,
            'top_candidates':[{'reference_index':i,'probability':p} for p,i in scores[:3]]})
    binding = {'schema_version':'biosure.ml-review-receipt/1.0','model_sha256':sha256(model),
               'reference_sha256':original['reference_sha256'],'observed_sha256':original['observed_sha256'],
               'correspondences_sha256':sha256(correspondences),'gate_receipt_sha256':original['receipt']['receipt_sha256']}
    return {**original,'mode':'learned_correspondence_review','correspondences':correspondences,
            'model':{'sha256':sha256(model),'training_rows':model['training_rows'],'threshold':model['threshold']},
            'ml_receipt':{**binding,'receipt_sha256':sha256(binding)},
            'ml_authority':'Ranking for manual inspection only. No probability authorizes an edit; the original deterministic gate decision is unchanged.'}
