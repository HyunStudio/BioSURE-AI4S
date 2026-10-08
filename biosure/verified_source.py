"""Internal consistency boundary for an operator-controlled source provider.

This module does not authenticate a provider or make caller-supplied evidence trusted.
No production provider is bundled or connected to the public API.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .schema import Document, parse_document, sha256


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class SourceKey:
    record_id: str
    version_id: str
    scope_id: str


@dataclass(frozen=True)
class SourceArtifact:
    key: SourceKey
    raw_bytes: bytes
    raw_sha256: str
    graph: Document
    graph_sha256: str
    origin: str
    retrieved_at: str
    license_uri: str
    extractor_version: str
    block_locators: tuple[str, ...]


@runtime_checkable
class TrustedSourceProvider(Protocol):
    extractor_version: str

    def resolve(self, key: SourceKey) -> SourceArtifact | None: ...

    def reextract(self, artifact: SourceArtifact) -> tuple[Document, tuple[str, ...]]: ...


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _locators(value: object, count: int) -> bool:
    return (isinstance(value, tuple) and len(value) == count and count > 0
            and all(_nonempty(locator) for locator in value)
            and len(set(value)) == count)


def verify_source_artifact(key: SourceKey, provider: TrustedSourceProvider | None) -> SourceArtifact | None:
    """Check reproducibility of a separately configured provider's artifact.

    Passing these checks establishes byte/graph consistency, not real-world
    provenance. A malicious or mistaken provider may still be self-consistent.
    """
    if (not isinstance(key, SourceKey)
            or not all(_nonempty(value) for value in (key.record_id, key.version_id, key.scope_id))
            or provider is None or not isinstance(provider, TrustedSourceProvider)):
        return None
    try:
        artifact = provider.resolve(key)
        if not isinstance(artifact, SourceArtifact) or artifact.key != key:
            return None
        if (not _nonempty(provider.extractor_version)
                or artifact.extractor_version != provider.extractor_version
                or not all(_nonempty(value) for value in (
                    artifact.origin, artifact.retrieved_at, artifact.license_uri))
                or not isinstance(artifact.raw_bytes, bytes)
                or not _digest(artifact.raw_sha256) or not _digest(artifact.graph_sha256)
                or hashlib.sha256(artifact.raw_bytes).hexdigest() != artifact.raw_sha256
                or not isinstance(artifact.graph, Document)
                or artifact.graph.record_id != key.record_id):
            return None
        graph = parse_document(artifact.graph.to_mapping())
        if graph != artifact.graph or sha256(graph.to_mapping()) != artifact.graph_sha256:
            return None
        if not _locators(artifact.block_locators, len(graph.blocks)):
            return None
        extracted, locators = provider.reextract(artifact)
        if (not isinstance(extracted, Document) or extracted != graph
                or sha256(parse_document(extracted.to_mapping()).to_mapping()) != artifact.graph_sha256
                or locators != artifact.block_locators):
            return None
        return artifact
    except (OSError, ValueError, TypeError, AttributeError):
        return None
