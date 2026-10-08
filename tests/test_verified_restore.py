"""Internal restoration tests; the fixture provider is not source authentication."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from biosure.schema import parse_document, parse_request, sha256
from biosure.verified_restore import review_verified_restoration
from test_verified_source import FixtureProvider, GRAPH, KEY, raw_for


def provider_for(graph):
    original = FixtureProvider().artifact
    locators = tuple(f"section-A/p{i + 1}" for i in range(len(graph.blocks)))
    raw = raw_for(graph)
    artifact = replace(original, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
                       graph=graph, graph_sha256=sha256(graph.to_mapping()), block_locators=locators)
    return FixtureProvider(artifact)


def request_for(damaged, source, operation="INSERT_PARAGRAPH", evidence=None):
    return parse_request({
        "case_id": "fixture-case", "damaged": damaged.to_mapping(),
        "candidates": [{"candidate_id": "one", "operation": operation, "document": source.to_mapping()}],
        "evidence": evidence or {"trusted_insertions": [], "trusted_identities": []},
    })


def assert_abstain(result):
    assert result["decision"].action == "ABSTAIN"
    assert result["selected_output"] is None
    assert result["source_binding"] is None
    assert result["receipt"] is None


def test_single_internal_insertion_selects_exact_source_graph():
    damaged = replace(GRAPH, blocks=(GRAPH.blocks[0], GRAPH.blocks[2]))
    result = review_verified_restoration(request_for(damaged, GRAPH), KEY, provider_for(GRAPH))
    assert result["decision"].action == "AUTO_REPAIR"
    assert result["selected_output"] == GRAPH
    assert result["source_binding"]["graph_sha256"] == sha256(GRAPH.to_mapping())
    assert result["receipt"]["status"] == "SELECTED_NOT_WRITTEN"


def test_single_internal_duplicate_removal_selects_exact_source_graph():
    source = replace(GRAPH, blocks=(GRAPH.blocks[0], GRAPH.blocks[2]))
    duplicate = replace(GRAPH.blocks[0], block_id="duplicate")
    damaged = replace(source, blocks=(source.blocks[0], duplicate, source.blocks[1]))
    result = review_verified_restoration(request_for(damaged, source, "REMOVE_DUPLICATE"), KEY, provider_for(source))
    assert result["decision"].action == "AUTO_REPAIR"
    assert result["selected_output"] == source


def test_missing_provider_and_forged_caller_evidence_cannot_select():
    damaged = replace(GRAPH, blocks=(GRAPH.blocks[0], GRAPH.blocks[2]))
    request = request_for(damaged, GRAPH)
    assert_abstain(review_verified_restoration(request, KEY, None))
    wrong = replace(GRAPH.blocks[1], text_sha256=hashlib.sha256(b"forged").hexdigest())
    forged_graph = replace(GRAPH, blocks=(GRAPH.blocks[0], wrong, GRAPH.blocks[2]))
    forged = request_for(damaged, forged_graph, evidence={
        "trusted_insertions": [{"block_id": wrong.block_id, "text_sha256": wrong.text_sha256,
                                "before_id": "beginning", "after_id": "end", "source_id": "forged"}],
        "trusted_identities": [],
    })
    assert_abstain(review_verified_restoration(forged, KEY, provider_for(GRAPH)))


def test_provider_failure_abstains_instead_of_escaping():
    damaged = replace(GRAPH, blocks=(GRAPH.blocks[0], GRAPH.blocks[2]))

    class BrokenProvider(FixtureProvider):
        def resolve(self, key):
            raise RuntimeError("provider unavailable")

    assert_abstain(review_verified_restoration(request_for(damaged, GRAPH), KEY, BrokenProvider()))


def test_unrelated_survivor_edit_order_anchor_and_metadata_abstain():
    damaged = replace(GRAPH, blocks=(GRAPH.blocks[0], GRAPH.blocks[2]))
    altered = replace(GRAPH.blocks[0], text_sha256=hashlib.sha256(b"other").hexdigest())
    graphs = [
        replace(GRAPH, blocks=(altered, *GRAPH.blocks[1:])),
        replace(GRAPH, blocks=(GRAPH.blocks[1], GRAPH.blocks[0], GRAPH.blocks[2])),
        replace(GRAPH, citation_anchors=(("beginning", "end"),)),
        replace(GRAPH, blocks=(GRAPH.blocks[0], replace(GRAPH.blocks[1], section_level=1), GRAPH.blocks[2])),
    ]
    for graph in graphs:
        assert_abstain(review_verified_restoration(request_for(damaged, graph), KEY, provider_for(graph)))


def test_unsupported_block_kinds_and_multiple_candidates_abstain():
    damaged = replace(GRAPH, blocks=(GRAPH.blocks[0], GRAPH.blocks[2]))
    for kind in ("heading", "figure_caption", "table_caption"):
        graph = replace(GRAPH, blocks=(GRAPH.blocks[0], replace(GRAPH.blocks[1], kind=kind), GRAPH.blocks[2]))
        assert_abstain(review_verified_restoration(request_for(damaged, graph), KEY, provider_for(graph)))
    payload = request_for(damaged, GRAPH).to_mapping()
    payload["candidates"].append({**payload["candidates"][0], "candidate_id": "two"})
    assert_abstain(review_verified_restoration(parse_request(payload), KEY, provider_for(GRAPH)))


def test_duplicate_with_two_possible_retained_paragraphs_abstains():
    same = replace(GRAPH.blocks[0], block_id="same-again")
    source = replace(GRAPH, blocks=(GRAPH.blocks[0], same, GRAPH.blocks[2]))
    duplicate = replace(GRAPH.blocks[0], block_id="duplicate")
    damaged = replace(source, blocks=(source.blocks[0], duplicate, *source.blocks[1:]))
    assert_abstain(review_verified_restoration(request_for(damaged, source, "REMOVE_DUPLICATE"), KEY, provider_for(source)))
