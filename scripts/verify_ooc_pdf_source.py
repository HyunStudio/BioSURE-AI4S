"""Verify one frozen OoC publisher PDF against its public audit inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.ooc_pdf_audit import verify_frozen_pdf
from biosure.schema import loads_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    try:
        inputs = loads_json(args.inputs.read_text(encoding="utf-8"))
        result = verify_frozen_pdf(args.pdf.read_bytes(), inputs)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
