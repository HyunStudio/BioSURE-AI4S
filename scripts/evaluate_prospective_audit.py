"""Run a locked multi-source audit with gold-separated decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.prospective_audit import evaluate_manifest
from biosure.schema import canonical_bytes, loads_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.out_dir.exists():
            raise ValueError("output directory already exists")
        manifest = loads_json(args.manifest.read_text(encoding="utf-8"))
        model = loads_json(args.model.read_text(encoding="utf-8"))
        result = evaluate_manifest(manifest, args.manifest.parent, model)
        args.out_dir.mkdir(parents=False, exist_ok=False)
        (args.out_dir / "decisions.json").write_bytes(canonical_bytes(result["decisions"]))
        (args.out_dir / "summary.json").write_bytes(canonical_bytes(result["summary"]))
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
