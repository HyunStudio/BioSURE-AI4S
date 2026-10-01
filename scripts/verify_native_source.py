"""Verify frozen native-pilot observations against a locally supplied source PDF.

The PDF is not distributed. This command checks the PDF identity and text-layer
observations only; it does not adjudicate the visual/JATS gold transcription.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.native_pilot import verify_native_pdf_source
from biosure.schema import loads_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="matching full source PDF or two-page excerpt")
    parser.add_argument("inputs", type=Path, nargs="?", default=Path(__file__).resolve().parents[1]
                        / "fixtures" / "native_pilot_inputs.json")
    args = parser.parse_args()
    try:
        inputs = loads_json(args.inputs.read_text(encoding="utf-8"))
        result = verify_native_pdf_source(args.pdf.read_bytes(), inputs)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
