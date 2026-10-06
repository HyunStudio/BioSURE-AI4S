"""Build the public, standard-library-only Python engine for browser execution."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


MODULES = ("__init__.py", "schema.py", "gate.py", "receipts.py", "workflow.py",
           "ml_review.py", "learned_upstream.py")


def _archive(root: Path) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name in MODULES:
            info = ZipInfo(f"biosure/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / "biosure" / name).read_bytes(), compress_type=ZIP_DEFLATED,
                             compresslevel=9)
    return buffer.getvalue()


def build(root: Path, *, check: bool = False) -> None:
    root = root.resolve()
    outputs = {
        root / "docs/try/engine.zip": _archive(root),
        root / "docs/try/model.json": (root / "fixtures/ml_model.json").read_bytes(),
    }
    for path, expected in outputs.items():
        if check:
            if not path.is_file() or path.read_bytes() != expected:
                raise ValueError(f"stale browser engine asset: {path.name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        build(Path(__file__).resolve().parents[1], check=args.check)
    except (OSError, ValueError) as error:
        parser.exit(1, f"BLOCK: {error}\n")
    print("PASS: browser engine assets current" if args.check else "PASS: browser engine assets built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
