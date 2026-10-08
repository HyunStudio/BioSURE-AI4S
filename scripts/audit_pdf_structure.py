"""Structural audit of review-only PDF import against JATS body paragraphs.

For each separately obtained PDF/JATS pair, the import text is compared with
body paragraphs (figures/tables excluded). Matching ignores case, spacing,
punctuation and digits, so it measures paragraph integrity, order and spliced
captions/page furniture, not glyph fidelity. The JATS file is the same
article's own reference, not independent adjudication. No source file is
packaged; obtain them from the PMC Cloud URLs in the protocol report.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.pdf_extract import extract_pdf

MIN_PARAGRAPH = 200
PROBE = 40
_CAPTION = re.compile(r"\b(?:Fig\.?|FIG|Figure|FIGURE|Table|TABLE)\s?\d+", re.I)


def norm(text: str) -> str:
    # Digits are dropped because PDFs print citation numbers that JATS marks up separately.
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKC", text).lower())


def _strip(xml: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", xml))


def jats_paragraphs(xml: str) -> list[str]:
    body = re.search(r"<body>(.*)</body>", xml, re.S)
    if body is None:
        raise ValueError("JATS file has no <body>")
    body_text = re.sub(r"<(fig|table-wrap)[ >].*?</\1>", " ", body.group(1), flags=re.S)
    paragraphs = [_strip(p) for p in re.findall(r"<p(?:\s[^>]*)?>(.*?)</p>", body_text, re.S)]
    return [p for p in paragraphs if len(norm(p)) >= MIN_PARAGRAPH]


def _inserts(target: str, text: str, raw_index: list[int], raw: str):
    """Greedy alignment; yields raw text spliced between matched runs (None if unresolved)."""
    pos, i = text.find(target[:PROBE]), 0
    while pos >= 0 and i < len(target):
        k = 0
        while i + k < len(target) and pos + k < len(text) and text[pos + k] == target[i + k]:
            k += 1
        i += k
        if i >= len(target):
            return
        resume = text.find(target[i:i + PROBE], pos + k)
        if resume < 0:
            yield None
            return
        yield raw[raw_index[pos + k - 1] + 1:raw_index[resume]]
        pos = resume


def audit_pair(pdf: bytes, xml: str) -> dict:
    paragraphs = jats_paragraphs(xml)
    result = extract_pdf(pdf)
    raw = " ".join(chunk["text"] for chunk in result["paragraphs"])
    raw_index, letters = [], []
    for index, char in enumerate(raw):
        for letter in norm(char):
            raw_index.append(index)
            letters.append(letter)
    text = "".join(letters)
    hints = [h for h in result["review_hints"] if h["kind"] == "PROBABLE_CAPTION_OR_PAGE_FURNITURE"]
    hint_keys = [norm(h["excerpt"])[:30] for h in hints if len(norm(h["excerpt"])) >= 4]
    row = {"pages": result["pages"], "paragraphs": len(paragraphs), "intact": 0, "split": 0,
           "unverified": 0, "lost": 0, "order_inversions": 0, "inserts": 0, "caption_inserts": 0,
           "furniture_or_other_inserts": 0, "inserts_located_by_hint": 0,
           "furniture_hints_shown": len(hints)}
    positions = []
    for paragraph in paragraphs:
        target = norm(paragraph)
        found = text.find(target)
        if found >= 0:
            row["intact"] += 1
            positions.append(found)
            continue
        head, tail = text.find(target[:PROBE]), text.find(target[-PROBE:])
        if head < 0 or tail <= head:
            row["lost"] += 1
            continue
        positions.append(head)
        inserts = list(_inserts(target, text, raw_index, raw))
        if None in inserts:
            # Not every letter could be traced in order: the gap may be a
            # deletion, reordering or linearised formula, not a splice.
            row["unverified"] += 1
            continue
        row["split"] += 1
        for insert in inserts:
            row["inserts"] += 1
            row["caption_inserts" if _CAPTION.search(insert) else "furniture_or_other_inserts"] += 1
            key = norm(insert)
            row["inserts_located_by_hint"] += any(k in key for k in hint_keys)
    row["order_inversions"] = sum(1 for a, b in zip(positions, positions[1:]) if b < a)
    return row


def audit_directory(root: Path) -> dict:
    rows = {}
    for pdf in sorted((root / "pdf").glob("*.pdf")):
        rows[pdf.stem] = audit_pair(pdf.read_bytes(), (root / "xml" / f"{pdf.stem}.xml").read_text(encoding="utf-8"))
    if not rows:
        raise ValueError("no PDF files under pdf/")
    keys = [k for k in next(iter(rows.values())) if isinstance(next(iter(rows.values()))[k], int)]
    return {"sources": len(rows), "total": {k: sum(r[k] for r in rows.values()) for k in keys}, "by_source": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="directory with pdf/<ID>.pdf and xml/<ID>.xml")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(audit_directory(args.root), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"PDF structure audit error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
