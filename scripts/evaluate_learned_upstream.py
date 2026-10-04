"""Replay the frozen source-held-out learned upstream audit without overwriting output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.learned_upstream_audit import (FOLLOWUP_LOCKED_SOURCES,
                                            evaluate_upstream_manifest)
from biosure.schema import canonical_bytes, loads_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--profile", choices=("original", "followup"), default="original",
                        help="Select an exact committed source-order lock; no arbitrary source set is accepted")
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("output already exists")
        manifest = loads_json(args.manifest.read_text(encoding="utf-8"))
        model = loads_json(args.model.read_text(encoding="utf-8"))
        if args.profile == "followup":
            result = evaluate_upstream_manifest(manifest, args.root, model,
                                                locked_sources=FOLLOWUP_LOCKED_SOURCES)
        else:
            result = evaluate_upstream_manifest(manifest, args.root, model)
        with args.out.open("xb") as output:
            output.write(canonical_bytes(result))
        print("Audited", result["summary"]["overall"]["attempted_sources"], "locked sources", flush=True)
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
