"""Contract tests for a test-only source; no scored gold is used here."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biosure.schema import canonical_bytes, loads_json, parse_document, sha256
from biosure.verified_source import SourceArtifact, SourceKey, verify_source_artifact


GRAPH = parse_document({
    "record_id": "fixture-record",
    "blocks": [
        {"block_id": name, "kind": "paragraph", "text_sha256": hashlib.sha256(name.encode()).hexdigest(), "section_level": 0, "target_id": None}
        for name in ("beginning", "middle", "end")
    ],
    "citation_anchors": [],
})
KEY = SourceKey("fixture-record", "version-1", "section-A")
LOCATORS = ("section-A/p1", "section-A/p2", "section-A/p3")


def raw_for(graph=GRAPH, key=KEY):
    return canonical_bytes({"record_id": key.record_id, "version_id": key.version_id,
                            "scope_id": key.scope_id, "document": graph.to_mapping()})


RAW = raw_for()


class FixtureProvider:
    extractor_version = "fixture-extractor/1"

    def __init__(self, artifact=None, extracted_graph=None, locators=None):
        self.artifact = artifact if artifact is not None else SourceArtifact(
            key=KEY, raw_bytes=RAW, raw_sha256=hashlib.sha256(RAW).hexdigest(),
            graph=GRAPH, graph_sha256=sha256(GRAPH.to_mapping()),
            origin="operator-test-fixture", retrieved_at="2026-10-07T00:00:00Z",
            license_uri="https://example.invalid/test-only", extractor_version=self.extractor_version,
            block_locators=LOCATORS,
        )
        self.extracted_graph = extracted_graph
        self.locators = locators

    def resolve(self, key):
        return self.artifact

    def reextract(self, artifact):
        envelope = loads_json(artifact.raw_bytes.decode("utf-8"))
        if (envelope["record_id"], envelope["version_id"], envelope["scope_id"]) != (
            artifact.key.record_id, artifact.key.version_id, artifact.key.scope_id
        ):
            raise ValueError("wrong raw scope/version")
        extracted = parse_document(envelope["document"])
        locators = tuple(f"{artifact.key.scope_id}/p{i + 1}" for i in range(len(extracted.blocks)))
        return (self.extracted_graph if self.extracted_graph is not None else extracted,
                self.locators if self.locators is not None else locators)


def test_exact_independent_fixture_verifies():
    provider = FixtureProvider()
    assert verify_source_artifact(KEY, provider) == provider.artifact


def test_missing_or_untrusted_provider_abstains():
    assert verify_source_artifact(KEY, None) is None
    assert verify_source_artifact(KEY, {"artifact": FixtureProvider().artifact}) is None


def test_changed_raw_bytes_or_stale_digest_abstains():
    artifact = FixtureProvider().artifact
    assert verify_source_artifact(KEY, FixtureProvider(replace(artifact, raw_bytes=RAW + b"change"))) is None
    assert verify_source_artifact(KEY, FixtureProvider(replace(artifact, graph_sha256="0" * 64))) is None


def test_rehashed_substituted_raw_graph_and_wrong_raw_scope_abstain():
    artifact = FixtureProvider().artifact
    changed = replace(GRAPH.blocks[1], text_sha256=hashlib.sha256(b"forged").hexdigest())
    other_graph = replace(GRAPH, blocks=(GRAPH.blocks[0], changed, GRAPH.blocks[2]))
    other_raw = raw_for(other_graph)
    forged = replace(artifact, raw_bytes=other_raw, raw_sha256=hashlib.sha256(other_raw).hexdigest())
    assert verify_source_artifact(KEY, FixtureProvider(forged)) is None
    other_scope = raw_for(GRAPH, SourceKey(KEY.record_id, KEY.version_id, "section-B"))
    wrong_scope = replace(artifact, raw_bytes=other_scope, raw_sha256=hashlib.sha256(other_scope).hexdigest())
    assert verify_source_artifact(KEY, FixtureProvider(wrong_scope)) is None


def test_exact_record_version_and_scope_are_required():
    artifact = FixtureProvider().artifact
    for key in (SourceKey("other", KEY.version_id, KEY.scope_id),
                SourceKey(KEY.record_id, "other", KEY.scope_id),
                SourceKey(KEY.record_id, KEY.version_id, "other")):
        assert verify_source_artifact(KEY, FixtureProvider(replace(artifact, key=key))) is None


def test_reextractor_version_graph_and_locators_must_match():
    artifact = FixtureProvider().artifact
    assert verify_source_artifact(KEY, FixtureProvider(replace(artifact, extractor_version="stale"))) is None
    other = replace(GRAPH, blocks=GRAPH.blocks[:-1])
    assert verify_source_artifact(KEY, FixtureProvider(extracted_graph=other)) is None
    assert verify_source_artifact(KEY, FixtureProvider(locators=("section-A/p1", "section-B/p2", "section-A/p3"))) is None
    assert verify_source_artifact(KEY, FixtureProvider(replace(artifact, block_locators=("x", "x", "z")))) is None
