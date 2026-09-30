"""Fit once on frozen PMC sources, tune on dev, and score unseen articles."""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import math
import random
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from biosure.ml_review import FEATURE_NAMES, _UNIT, critical_changes, match_probability, pair_features, train_model
from biosure.schema import canonical_bytes, sha256

LICENSE='https://creativecommons.org/licenses/by/4.0/'
METHODS=('learned_logistic','exact','difflib','token_dice','lexical_blend')
NUMBER=re.compile(r'(?<![\w.])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?')
WORD=re.compile(r'\b[A-Za-z]{10,}\b')
UNIT_REPLACEMENTS={'mg':'g','ng':'µg','pg':'ng','kg':'g','ug':'mg','μg':'mg','µg':'mg',
                   'g':'kg','mL':'µL','ml':'µL','uL':'mL','μL':'mL','µL':'mL','L':'mL',
                   'mm':'µm','nm':'µm','um':'mm','μm':'mm','µm':'mm','cm':'mm',
                   'mM':'µM','uM':'mM','μM':'mM','µM':'mM','nM':'µM','M':'mM',
                   'Pa':'kPa','kPa':'Pa','Hz':'kHz','min':'s','hour':'min',
                   'hours':'min','day':'hours','days':'hours','s':'min'}


def _mutate(text: str) -> list[tuple[str,str,list[str]]]:
    items=[('identity',text,[]), ('whitespace','  '.join(text.split()),[]),
           ('punctuation',text[:-1] if text.endswith('.') else text+'.',[])]
    match=WORD.search(text)
    if match:
        word=match.group()
        items.append(('line_hyphenation',text[:match.start()]+word[:5]+'-\n'+word[5:]+text[match.end():],[]))
    match=NUMBER.search(text)
    if match:
        old=match.group()
        # A deliberately different value with the same surrounding article text.
        replacement=str(Decimal(old)+1)
        items.append(('number_change',text[:match.start()]+replacement+text[match.end():],['NUMBER_CHANGED']))
    unit=_UNIT.search(text)
    if unit:
        replacement=UNIT_REPLACEMENTS[unit.group()]
        items.append(('unit_change',text[:unit.start()]+replacement+text[unit.end():],['UNIT_CHANGED']))
    negation=re.search(r'\bnot\b',text,flags=re.I)
    if negation:
        changed=text[:negation.start()]+text[negation.end():]
    else:
        changed='Not '+text
    items.append(('negation_change',changed,['NEGATION_CHANGED']))
    return items


def _validated_articles(corpus: dict) -> list[dict]:
    if not isinstance(corpus,dict) or corpus.get('schema_version')!='biosure.ml-corpus/1.0':
        raise ValueError('invalid corpus schema')
    articles=corpus.get('articles')
    if not isinstance(articles,list) or len(articles)<8 or len(articles)>36:
        raise ValueError('need 8-36 distinct articles')
    ids=[]
    for item in articles:
        if not isinstance(item,dict) or not re.fullmatch(r'PMC\d+',str(item.get('pmcid',''))):
            raise ValueError('invalid article identity')
        if item.get('license_uri')!=LICENSE:
            raise ValueError('non-CC-BY source')
        if not isinstance(item.get('paragraphs'),list) or not 2<=len(item['paragraphs'])<=8:
            raise ValueError('need 2-8 paragraphs per article')
        paragraphs=[p.get('text') for p in item['paragraphs'] if isinstance(p,dict)]
        if len(paragraphs)!=len(item['paragraphs']) or any(not isinstance(s,str) or not s.strip() or len(s)>4096 for s in paragraphs):
            raise ValueError('invalid article paragraph')
        if len(set(paragraphs))!=len(paragraphs):
            raise ValueError('repeated reference paragraph')
        ids.append(item['pmcid'])
    if len(set(ids))!=len(ids):
        raise ValueError('duplicate article source')
    return articles


def _split(articles: list[dict]) -> dict[str,str]:
    train=len(articles)//2
    dev=(len(articles)-train)//2
    return {item['pmcid']:('train' if i<train else 'dev' if i<train+dev else 'test')
            for i,item in enumerate(articles)}


def build_pairs(corpus: dict) -> list[dict]:
    articles=_validated_articles(corpus)
    partitions=_split(articles)
    pairs=[]
    for article in articles:
        source=article['pmcid']
        paragraphs=[item['text'] for item in article['paragraphs']]
        for target,text in enumerate(paragraphs):
            for variant,observed,flags in _mutate(text):
                query=f'{source}:p{target+1}:{variant}'
                for candidate,reference in enumerate(paragraphs):
                    pairs.append({'source_id':source,'split':partitions[source],
                        'query_id':query,'variant':variant,'reference_index':candidate,
                        'reference':reference,'observed':observed,'label':int(candidate==target),
                        'expected_flags':flags})
    return pairs


def _score(method: str, model: dict, reference: str, observed: str) -> float:
    if method=='learned_logistic':
        return match_probability(model,reference,observed)
    if method=='exact':
        return float(' '.join(reference.split())==' '.join(observed.split()))
    if method=='difflib':
        return difflib.SequenceMatcher(None,reference.casefold(),observed.casefold()).ratio()
    features=pair_features(reference,observed)
    if method=='token_dice':
        return features[1]
    if method=='lexical_blend':
        return .45*features[1]+.45*features[3]+.10*features[4]
    raise ValueError('unknown comparator')


def _counts(labels: list[int], predictions: list[int]) -> dict:
    tp=sum(y==1 and x==1 for y,x in zip(labels,predictions))
    fp=sum(y==0 and x==1 for y,x in zip(labels,predictions))
    fn=sum(y==1 and x==0 for y,x in zip(labels,predictions))
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    return {'pairs':len(labels),'tp':tp,'fp':fp,'fn':fn,'precision':precision,
            'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0.0}


def evaluate(corpus: dict) -> dict:
    pairs=build_pairs(corpus)
    articles=_validated_articles(corpus)
    partitions=_split(articles)
    training=[{key:row[key] for key in ('reference','observed','label')} for row in pairs if row['split']=='train']
    model=train_model(training)
    dev=[row for row in pairs if row['split']=='dev']
    dev_scores=[_score('learned_logistic',model,row['reference'],row['observed']) for row in dev]
    threshold_choices=[]
    for threshold in (.35,.50,.65,.80):
        counts=_counts([row['label'] for row in dev],[int(score>=threshold) for score in dev_scores])
        threshold_choices.append({'threshold':threshold,**counts})
    choice=max(threshold_choices,key=lambda item:(item['f1'],item['precision'],item['threshold']))
    model['threshold']=choice['threshold']
    held=[row for row in pairs if row['split']=='test']
    groups=defaultdict(list)
    for row in held: groups[row['query_id']].append(row)
    scoring={}; per_query={}
    for method in METHODS:
        correct=incorrect=abstained=0
        per_source=defaultdict(lambda:[0,0])
        failures=[]
        for query,rows in groups.items():
            candidates=[(_score(method,model,row['reference'],row['observed']),row['reference_index'],row['label']) for row in rows]
            candidates.sort(key=lambda item:(-item[0],item[1]))
            winner=candidates[0]
            applied=winner[0]>0 if method=='exact' else winner[0]>=model['threshold'] if method=='learned_logistic' else True
            per_source[rows[0]['source_id']][1]+=1
            if not applied:
                abstained+=1
            elif winner[2]:
                correct+=1; per_source[rows[0]['source_id']][0]+=1
            else:
                incorrect+=1
                failures.append({'source_id':rows[0]['source_id'],'query_id':query,
                                 'variant':rows[0]['variant'],'chosen_reference_index':winner[1],
                                 'expected_reference_index':next(row['reference_index'] for row in rows if row['label']==1),
                                 'winning_score':winner[0]})
        total=len(groups)
        scoring[method]={'queries':total,'correct':correct,'incorrect':incorrect,'abstained':abstained,
            'top1_accuracy':correct/total if total else 0.0,
            'accepted_precision':correct/(correct+incorrect) if correct+incorrect else 0.0,
            'article_macro_accuracy':sum(a/b for a,b in per_source.values())/len(per_source),
            'failures':failures}
        per_query[method]={source:value[0]/value[1] for source,value in per_source.items()}
    test_sources=[item['pmcid'] for item in articles if partitions[item['pmcid']]=='test']
    best_lexical=max((name for name in METHODS if name!='learned_logistic'),
                     key=lambda name:(scoring[name]['top1_accuracy'],name))
    deltas={source:per_query['learned_logistic'][source]-per_query[best_lexical][source] for source in test_sources}
    generator=random.Random(20260930)
    bootstrap=sorted(sum(deltas[generator.choice(test_sources)] for _ in test_sources)/len(test_sources)
                     for _ in range(1000))
    flags=['NUMBER_CHANGED','UNIT_CHANGED','NEGATION_CHANGED']
    alert_results={}
    for flag in flags:
        expected=[]; predicted=[]
        for rows in groups.values():
            gold=next(row for row in rows if row['label']==1)
            expected.append(int(flag in gold['expected_flags']))
            predicted.append(int(flag in critical_changes(gold['reference'],gold['observed'])['flags']))
        alert_results[flag]=_counts(expected,predicted)
    return {'schema_version':'biosure.ml-evaluation/1.0','corpus_sha256':sha256(corpus),
            'split':{'train_sources':[item['pmcid'] for item in articles if partitions[item['pmcid']]=='train'],
                     'dev_sources':[item['pmcid'] for item in articles if partitions[item['pmcid']]=='dev'],
                     'test_sources':test_sources},
            'training_pairs':len(training), 'model':model,
            'threshold_selection':{'rule':'Maximize dev pair F1; ties higher precision then threshold',
                                   'choices':threshold_choices,'selected':choice['threshold']},
            'held_out':{'correspondence':scoring,'critical_alerts':alert_results,
                'learned_minus_best_lexical':{'baseline':best_lexical,
                    'accuracy_delta':scoring['learned_logistic']['top1_accuracy']-scoring[best_lexical]['top1_accuracy'],
                    'article_bootstrap_95_interval':[bootstrap[25],bootstrap[974]]}},
            'limitations':'Labels and variants are constructed from attributed articles; source holdout does not make them natural errors. No independent scientific or human-time evaluation. Full correct source copy remains a stronger restoration baseline than this ranking task.'}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus',type=Path)
    parser.add_argument('model_output',type=Path)
    parser.add_argument('result_output',type=Path)
    args=parser.parse_args()
    if args.model_output.exists() or args.result_output.exists():
        parser.error('output already exists; frozen artifacts are not overwritten')
    corpus=json.loads(args.corpus.read_text(encoding='utf-8'))
    result=evaluate(corpus)
    with args.model_output.open('xb') as output: output.write(canonical_bytes(result['model']))
    with args.result_output.open('xb') as output: output.write(canonical_bytes(result))
    mini={'sources':{key:len(value) for key,value in result['split'].items()},
          'training_pairs':result['training_pairs'],'threshold':result['model']['threshold'],
          'test':{key:{k:item[k] for k in ('queries','correct','incorrect','abstained')} for key,item in result['held_out']['correspondence'].items()},
          'delta':result['held_out']['learned_minus_best_lexical']}
    print(json.dumps(mini,indent=2),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
