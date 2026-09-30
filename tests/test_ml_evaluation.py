import copy
import pytest
from scripts import build_ml_corpus, evaluate_ml


def corpus():
    return {'schema_version':'biosure.ml-corpus/1.0', 'snapshot':'2026-09-30',
        'query':'test fixture, not real articles', 'selection':'fixture', 'exclusions':[],
        'change_notice':'Constructed variants, not original scientific claims.',
        'articles':[{'pmcid':f'PMC{100+i}','doi':f'10.test/{i}','title':f'Authored source {i}',
            'authors':['Test Author'],'license_uri':'https://creativecommons.org/licenses/by/4.0/',
            'article_url':f'https://pmc.ncbi.nlm.nih.gov/articles/PMC{100+i}/',
            'source_url':f'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{100+i}&metadataPrefix=pmc',
            'source_sha256':'a'*64,
            'paragraphs':[{'locator':f'body//p[{j+1}]','text':text} for j,text in enumerate([
                f'Channel source {i} used a concentration of 5 mg for controlled measurement.',
                f'Cells in source {i} did not increase after the microfluidic treatment.',
                f'The microscopy controller in source {i} collects image measurements every 24 hours.'
            ])]} for i in range(8)]}


def test_license_is_checked_from_actual_xml_before_excerpt_selection():
    raw=b'<article><front><article-meta><article-id pub-id-type="pmcid">PMC123</article-id><article-id pub-id-type="doi">10.test/a</article-id><title-group><article-title>Test</article-title></title-group><permissions><license><license_ref>https://creativecommons.org/licenses/by-nc/4.0/</license_ref></license></permissions></article-meta></front><body><p>Some text.</p></body></article>'
    with pytest.raises(ValueError,match='CC BY 4.0'):
        build_ml_corpus.extract_source(raw,'PMC123')


def test_author_name_components_are_separated_for_cc_by_attribution():
    raw = (b'<article><front><article-meta><article-id pub-id-type="pmcid">PMC123</article-id>'
           b'<article-id pub-id-type="doi">10.test/a</article-id><title-group><article-title>Test</article-title></title-group>'
           b'<contrib-group><contrib contrib-type="author"><name><surname>Liu</surname><given-names>Wenhan</given-names></name></contrib></contrib-group>'
           b'<permissions><license><license_ref>https://creativecommons.org/licenses/by/4.0/</license_ref></license></permissions>'
           b'</article-meta></front><body>' +
           b''.join(b'<p>This is a sufficiently long source paragraph about organ on chip research and measurement number '+str(i).encode()+b'.</p>' for i in range(8)) +
           b'</body></article>')
    result = build_ml_corpus.extract_source(raw,'PMC123')
    assert result['authors'] == ['Liu Wenhan']


def test_partitions_group_whole_sources_without_leakage():
    pairs=evaluate_ml.build_pairs(corpus())
    split={}
    for pair in pairs:
        split.setdefault(pair['source_id'],set()).add(pair['split'])
    assert len(split)==8
    assert all(len(values)==1 for values in split.values())
    assert {key for key,value in split.items() if value=={'test'}}=={'PMC106','PMC107'}


def test_duplicate_source_and_nonredistributable_source_fail_before_training():
    data=corpus(); data['articles'][1]=copy.deepcopy(data['articles'][0])
    with pytest.raises(ValueError): evaluate_ml.build_pairs(data)
    data=corpus(); data['articles'][0]['license_uri']='https://creativecommons.org/licenses/by-nc/4.0/'
    with pytest.raises(ValueError): evaluate_ml.build_pairs(data)


def test_test_source_edits_cannot_change_fitted_model_or_dev_threshold():
    data=corpus(); first=evaluate_ml.evaluate(data)
    altered=copy.deepcopy(data)
    altered['articles'][-1]['paragraphs'][0]['text']='Changed test paragraph with 999 μg and no cell incubation.'
    second=evaluate_ml.evaluate(altered)
    assert first['model']==second['model']
    assert first['threshold_selection']==second['threshold_selection']
    assert first['corpus_sha256']!=second['corpus_sha256']


def test_all_comparators_share_denominators_and_report_ties_and_failures():
    result=evaluate_ml.evaluate(corpus())
    methods=result['held_out']['correspondence']
    assert set(methods)=={'learned_logistic','exact','difflib','token_dice','lexical_blend'}
    assert len({value['queries'] for value in methods.values()})==1
    assert result['split']['test_sources']==['PMC106','PMC107']
    assert 'learned_minus_best_lexical' in result['held_out']
    assert 'critical_alerts' in result['held_out']
    assert result['limitations']


def test_scientific_change_controls_have_independent_mutation_labels():
    pairs=evaluate_ml.build_pairs(corpus())
    queries={pair['query_id']:pair for pair in pairs if pair['label']==1}
    number=[row for row in queries.values() if row['variant']=='number_change']
    negation=[row for row in queries.values() if row['variant']=='negation_change']
    units=[row for row in queries.values() if row['variant']=='unit_change']
    assert number and negation
    assert units
    assert all(row['expected_flags']==['NUMBER_CHANGED'] for row in number)
    assert all(row['expected_flags']==['NEGATION_CHANGED'] for row in negation)
    assert all(row['expected_flags']==['UNIT_CHANGED'] for row in units)
