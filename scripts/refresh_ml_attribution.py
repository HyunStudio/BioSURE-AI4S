"""Repair name spacing in a frozen corpus from official JATS records.

The article identity, license and every selected paragraph must match before a
record is updated. The OAI envelope changes between requests, so raw XML
SHA-256 is deliberately not treated as a stable identity. Full XML stays in
memory. Writes a *new* snapshot path.
"""
from __future__ import annotations

import argparse
import copy
import json
import time
import urllib.request
from pathlib import Path

from biosure.schema import canonical_bytes
from scripts.build_ml_corpus import MAX_XML, extract_source


def refresh(corpus: dict, fetch=None) -> dict:
    fetch = fetch or _fetch
    updated = copy.deepcopy(corpus)
    for article in updated['articles']:
        raw = fetch(article['source_url'])
        fresh = extract_source(raw, article['pmcid'])
        if any(fresh[key] != article[key] for key in ('doi','title','paragraphs','license_uri','article_url')):
            raise ValueError('frozen article content mismatch: ' + article['pmcid'])
        article['authors'] = fresh['authors']
        time.sleep(.4)
    updated['change_notice'] += ' Author-name spacing refreshed after matching source identity, license and selected paragraphs; OAI envelope bytes can differ between retrievals.'
    return updated


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent':'BioSURE-attribution/0.3'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(MAX_XML + 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output exists; frozen snapshots are never overwritten')
    corpus = json.loads(args.source.read_text(encoding='utf-8'))
    repaired = refresh(corpus)
    with args.output.open('xb') as handle:
        handle.write(canonical_bytes(repaired))
    print(f"Verified and refreshed {len(repaired['articles'])} source attributions")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
