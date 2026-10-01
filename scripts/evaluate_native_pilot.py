"""Two-step native PDF pilot: decide without gold, then score sealed decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.native_pilot import decide_inputs, score_decisions
from biosure.schema import canonical_bytes, loads_json


def _read(path: Path) -> dict:
    return loads_json(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, args in (("decide", ("inputs", "model", "out")),
                       ("score", ("decisions", "gold", "out"))):
        command = sub.add_parser(name)
        for argument in args:
            command.add_argument(argument, type=Path)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError("output already exists")
        if args.command == "decide":
            result = decide_inputs(_read(args.inputs), _read(args.model))
        else:
            result = score_decisions(_read(args.decisions), _read(args.gold))
        args.out.write_bytes(canonical_bytes(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
