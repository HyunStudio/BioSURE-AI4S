"""The real-source alignment audit must not turn reference copying into ML gain."""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from biosure.schema import canonical_bytes, sha256


ROOT = Path(__file__).resolve().parents[1]


def frozen():
    manifest = json.loads((ROOT / 'fixtures/prospective_ooc_manifest.json').read_text(encoding='utf-8'))
    model = json.loads((ROOT / 'fixtures/ml_model.json').read_text(encoding='utf-8'))
    return manifest, model


def copied_frozen(tmp_path):
    manifest, model = frozen()
    paths = [manifest['protocol_path'], 'results/ml_evaluation.json']
    for source in manifest['sources']:
        paths.extend([source['inputs_path'], source['gold_path']])
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return manifest, model


def test_real_source_comparison_keeps_all_sources_and_exposes_lexical_advantage():
    from biosure.learned_upstream_audit import evaluate_upstream_manifest

    manifest, model = frozen()
    result = evaluate_upstream_manifest(manifest, ROOT, model)
    overall = result['summary']['overall']
    held = result['summary']['held_out']
    assert result['schema_version'] == 'biosure.learned-upstream-audit/1.0'
    assert result['model_sha256'] == sha256(model)
    assert overall['attempted_sources'] == overall['eligible_sources'] == 8
    assert overall['attempted_units'] == overall['compared_units'] == 16
    assert held['attempted_sources'] == held['eligible_sources'] == 4
    assert held['compared_units'] == 8
    assert overall['learned']['ranking_correct_units'] == 14
    assert overall['learned']['proposal_exact_units'] == 12
    assert overall['learned']['proposal_abstained_units'] == 4
    assert overall['difflib']['ranking_correct_units'] == 16
    assert overall['token_dice']['ranking_correct_units'] == 16
    assert overall['direct_copy']['exact_units'] == 16
    assert overall['reversed_reference_failure_control']['exact_units'] == 0
    assert held['learned']['ranking_correct_units'] == 7
    assert result['summary']['development']['attempted_sources'] + held['attempted_sources'] == 8
    assert len(result['summary']['sources']) == 8


def test_decision_phase_does_not_open_gold_even_when_gold_reads_are_denied(monkeypatch):
    from biosure.learned_upstream_audit import decide_upstream_manifest

    manifest, model = frozen()
    original_bytes, original_text = Path.read_bytes, Path.read_text

    def checked_bytes(path):
        if str(path).endswith('_gold.json'):
            raise AssertionError('gold read during decisions')
        return original_bytes(path)

    def checked_text(path, *args, **kwargs):
        if str(path).endswith('_gold.json'):
            raise AssertionError('gold read during decisions')
        return original_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_bytes', checked_bytes)
    monkeypatch.setattr(Path, 'read_text', checked_text)
    decisions = decide_upstream_manifest(manifest, ROOT, model)
    assert len(decisions) == 8
    assert all(item['source_id'] for item in decisions)


def test_removed_or_reassigned_locked_source_is_rejected():
    from biosure.learned_upstream_audit import decide_upstream_manifest

    manifest, model = frozen()
    removed = copy.deepcopy(manifest)
    removed['sources'].pop()
    with pytest.raises(ValueError, match='locked source'):
        decide_upstream_manifest(removed, ROOT, model)
    reassigned = copy.deepcopy(manifest)
    reassigned['sources'][4]['split'] = 'development'
    with pytest.raises(ValueError, match='locked source'):
        decide_upstream_manifest(reassigned, ROOT, model)


def test_stale_gold_digest_is_not_silently_scored():
    from biosure.learned_upstream_audit import evaluate_upstream_manifest

    manifest, model = frozen()
    stale = copy.deepcopy(manifest)
    stale['sources'][0]['gold_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='gold digest mismatch'):
        evaluate_upstream_manifest(stale, ROOT, model)


def test_partial_locked_source_keeps_attempt_and_verifies_its_scorable_gold(tmp_path):
    from biosure.learned_upstream_audit import evaluate_upstream_manifest

    manifest, model = copied_frozen(tmp_path)
    first = manifest['sources'][0]
    inputs = json.loads((tmp_path / first['inputs_path']).read_text(encoding='utf-8'))
    inputs['cases'] = inputs['cases'][:1]
    input_bytes = canonical_bytes(inputs)
    (tmp_path / first['inputs_path']).write_bytes(input_bytes)
    first['inputs_sha256'] = hashlib.sha256(input_bytes).hexdigest()
    gold = json.loads((tmp_path / first['gold_path']).read_text(encoding='utf-8'))
    gold['cases'] = gold['cases'][:1]
    gold['input_sha256'] = sha256(inputs)
    gold_bytes = canonical_bytes(gold)
    (tmp_path / first['gold_path']).write_bytes(gold_bytes)
    first['gold_sha256'] = hashlib.sha256(gold_bytes).hexdigest()
    first['units'][1] = {'unit_id': first['source_id'] + '-abstract',
                         'status': 'unscorable', 'reason': 'page-one boundary unavailable'}

    result = evaluate_upstream_manifest(manifest, tmp_path, model)
    assert result['summary']['overall']['attempted_units'] == 16
    assert result['summary']['overall']['scorable_units'] == 15
    assert result['summary']['overall']['compared_units'] == 14
    assert result['summary']['overall']['unscorable'][0]['reason'] == 'page-one boundary unavailable'
    first['gold_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='gold digest mismatch'):
        evaluate_upstream_manifest(manifest, tmp_path, model)


def test_invalid_condition_cannot_masquerade_as_native_error(tmp_path):
    from biosure.learned_upstream_audit import evaluate_upstream_manifest

    manifest, model = copied_frozen(tmp_path)
    first = manifest['sources'][0]
    inputs = json.loads((tmp_path / first['inputs_path']).read_text(encoding='utf-8'))
    inputs['cases'][0]['condition'] = 'lab_verified'
    input_bytes = canonical_bytes(inputs)
    (tmp_path / first['inputs_path']).write_bytes(input_bytes)
    first['inputs_sha256'] = hashlib.sha256(input_bytes).hexdigest()
    gold = json.loads((tmp_path / first['gold_path']).read_text(encoding='utf-8'))
    gold['input_sha256'] = sha256(inputs)
    gold_bytes = canonical_bytes(gold)
    (tmp_path / first['gold_path']).write_bytes(gold_bytes)
    first['gold_sha256'] = hashlib.sha256(gold_bytes).hexdigest()
    with pytest.raises(ValueError, match='condition'):
        evaluate_upstream_manifest(manifest, tmp_path, model)


def test_non_ccby_locked_source_is_rejected_before_decisions():
    from biosure.learned_upstream_audit import decide_upstream_manifest

    manifest, model = frozen()
    manifest['sources'][0]['license_uri'] = 'https://creativecommons.org/licenses/by-nc/4.0/'
    with pytest.raises(ValueError, match='CC BY'):
        decide_upstream_manifest(manifest, ROOT, model)


def test_input_source_license_must_match_locked_manifest(tmp_path):
    from biosure.learned_upstream_audit import decide_upstream_manifest

    manifest, model = copied_frozen(tmp_path)
    first = manifest['sources'][0]
    inputs = json.loads((tmp_path / first['inputs_path']).read_text(encoding='utf-8'))
    inputs['source']['license_uri'] = 'https://creativecommons.org/licenses/by-nc/4.0/'
    input_bytes = canonical_bytes(inputs)
    (tmp_path / first['inputs_path']).write_bytes(input_bytes)
    first['inputs_sha256'] = hashlib.sha256(input_bytes).hexdigest()
    with pytest.raises(ValueError, match='source metadata'):
        decide_upstream_manifest(manifest, tmp_path, model)


def test_cli_writes_once_after_full_audit_and_refuses_overwrite(tmp_path):
    output = tmp_path / 'audit.json'
    command = [sys.executable, 'scripts/evaluate_learned_upstream.py',
               '--manifest', 'fixtures/prospective_ooc_manifest.json',
               '--root', '.', '--model', 'fixtures/ml_model.json', '--out', str(output)]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['summary']['overall']['attempted_sources'] == 8
    assert result['summary']['overall']['learned']['ranking_correct_units'] == 14
    existing = output.read_bytes()
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert second.returncode != 0
    assert output.read_bytes() == existing


def test_offline_verifier_replays_frozen_learned_upstream_result():
    from scripts.verify_reproduction import verify

    replay = verify(ROOT)
    real = replay['learned_upstream_audit']
    assert real == {'sources': 8, 'held_out_sources': 4, 'units': 16,
                    'learned_rank_correct': 14, 'difflib_rank_correct': 16,
                    'token_dice_rank_correct': 16, 'direct_copy_exact': 16,
                    'reversed_reference_exact': 0, 'proposal_exact': 12,
                    'proposal_abstained': 4}
