"""Replay the constructed stress suite through the internal verified-source path.

An operator-controlled provider serves the authored, undamaged stress source
graphs from the generator, never from the scored gold files. Caller evidence is
discarded. This checks fail-closed selection mechanics on constructed cases; it
does not authenticate a real source, and source and gold share an origin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.gate import decide
from biosure.schema import canonical_bytes, loads_json, parse_document, parse_request, sha256
from biosure.verified_restore import review_verified_restoration
from biosure.verified_source import SourceArtifact, SourceKey
from scripts.build_stress_challenge import SOURCE_COUNT, source_document


VERSION_ID = "stress-constructed-v1"
SCOPE_ID = "full-document"
SCOPE = ("Constructed mechanics check: an operator-controlled fixture provider serves the "
         "generator's undamaged stress source graphs and all caller evidence is discarded. "
         "Source and gold share an origin by construction. Not source authentication, a "
         "natural-document result, the prospective verified-source arm, or a public route.")


def _raw(document: dict, version_id: str = VERSION_ID) -> bytes:
    return canonical_bytes({"record_id": document["record_id"], "version_id": version_id,
                            "scope_id": SCOPE_ID, "document": document})


class ConstructedEnvelopeProvider:
    """Test-grade provider: raw bytes are a JSON envelope re-parsed on every extraction."""

    extractor_version = "biosure-constructed-envelope/1"

    def __init__(self, documents: list[dict], version_id: str = VERSION_ID):
        self._raw = {document["record_id"]: _raw(document, version_id) for document in documents}

    def resolve(self, key: SourceKey) -> SourceArtifact | None:
        raw = self._raw.get(key.record_id)
        if raw is None:
            return None
        envelope = loads_json(raw.decode("utf-8"))
        if (envelope["version_id"], envelope["scope_id"]) != (key.version_id, key.scope_id):
            return None
        graph = parse_document(envelope["document"])
        return SourceArtifact(
            key=key, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
            graph=graph, graph_sha256=sha256(graph.to_mapping()),
            origin="scripts/build_stress_challenge.py:source_document",
            retrieved_at="2026-09-30T00:00:00Z",
            license_uri="https://opensource.org/license/mit",
            extractor_version=self.extractor_version,
            block_locators=tuple(f"{key.scope_id}/{block.block_id}" for block in graph.blocks),
        )

    def reextract(self, artifact: SourceArtifact):
        envelope = loads_json(artifact.raw_bytes.decode("utf-8"))
        if (envelope["record_id"], envelope["version_id"], envelope["scope_id"]) != (
            artifact.key.record_id, artifact.key.version_id, artifact.key.scope_id
        ):
            raise ValueError("raw envelope does not match the requested key")
        graph = parse_document(envelope["document"])
        return graph, tuple(f"{artifact.key.scope_id}/{block.block_id}" for block in graph.blocks)


def _condition(case_id: str) -> str:
    return case_id.split("--", 1)[1]


def _arm(requests: list, provider) -> list[dict]:
    """Decide every case without access to gold."""
    decided = []
    for request in requests:
        key = SourceKey(request.damaged.record_id, VERSION_ID, SCOPE_ID)
        result = review_verified_restoration(request, key, provider)
        selected = result["selected_output"]
        decided.append({
            "case_id": request.case_id,
            "action": result["decision"].action,
            "reason_codes": list(result["decision"].reason_codes),
            "selected_output_sha256": sha256(selected.to_mapping()) if selected is not None else None,
        })
    return decided


def _score(decided: list[dict], golds: dict[str, str]) -> dict:
    by_condition: dict[str, dict] = {}
    totals = {"cases": 0, "automatic": 0, "exact_auto": 0, "incorrect_auto": 0, "abstentions": 0}
    reasons: dict[str, int] = {}
    for item in decided:
        auto = item["action"] == "AUTO_REPAIR"
        exact = auto and item["selected_output_sha256"] == golds[item["case_id"]]
        row = by_condition.setdefault(_condition(item["case_id"]),
                                      {"cases": 0, "automatic": 0, "exact_auto": 0, "incorrect_auto": 0})
        for bucket in (row, totals):
            bucket["cases"] += 1
            bucket["automatic"] += auto
            bucket["exact_auto"] += exact
            bucket["incorrect_auto"] += auto and not exact
        totals["abstentions"] += not auto
        if not auto:
            for code in item["reason_codes"]:
                reasons[code] = reasons.get(code, 0) + 1
    return {**totals, "by_condition": dict(sorted(by_condition.items())),
            "abstention_reasons": dict(sorted(reasons.items()))}


def evaluate(root: Path) -> dict:
    root = root.resolve()
    paths = sorted((root / "fixtures/stress_challenge").glob("*.json"))
    if len(paths) != 168:
        raise ValueError("stress challenge must contain 168 cases")
    requests = [parse_request(loads_json(path.read_text(encoding="utf-8"))) for path in paths]
    sources = [source_document(index) for index in range(1, SOURCE_COUNT + 1)]
    arms = {
        "verified_source": _arm(requests, ConstructedEnvelopeProvider(sources)),
        "control_no_provider": _arm(requests, None),
        "control_stale_version": _arm(requests, ConstructedEnvelopeProvider(sources, "stale-version")),
    }
    public_gate = [{"case_id": request.case_id, "action": (decision := decide(request)).action,
                    "reason_codes": list(decision.reason_codes),
                    "selected_output_sha256": next(
                        (sha256(c.document.to_mapping()) for c in request.candidates
                         if c.candidate_id == decision.candidate_id), None)}
                   for request in requests]
    # Gold is opened only after every arm has decided.
    golds = {}
    for path in paths:
        gold = parse_document(loads_json((root / "fixtures/stress_gold" / path.name).read_text(encoding="utf-8")))
        golds[path.stem] = sha256(gold.to_mapping())
    return {
        "schema_version": "biosure.verified-constructed-stress/1.0",
        "scope": SCOPE,
        "challenge_sha256": sha256([request.case_id for request in requests]),
        "source_graphs": len(sources),
        "provider_extractor_version": ConstructedEnvelopeProvider.extractor_version,
        "arms": {name: _score(decided, golds) for name, decided in
                 {**arms, "public_caller_evidence_gate": public_gate}.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["run", "verify"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, help="new result file (run only; never overwritten)")
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.root)
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.command == "run":
            if args.out is None:
                raise ValueError("--out is required for run")
            with open(args.out, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        else:
            frozen = loads_json((args.root / "results/verified_constructed_stress.json").read_text(encoding="utf-8"))
            if frozen != result:
                raise ValueError("frozen verified-source constructed result mismatch")
        verified = result["arms"]["verified_source"]
        print(json.dumps({k: verified[k] for k in ("cases", "exact_auto", "incorrect_auto", "abstentions")},
                         sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"verified constructed evaluation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
