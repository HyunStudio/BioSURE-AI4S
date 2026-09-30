"""Fail-closed, no-prior public source export. Does not approve or publish anything."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.schema import canonical_bytes, loads_json
from scripts.audit_release import _allowed, audit

MANIFEST = "results/release_manifest.json"
EXCLUDED = {"biosure/legacy.py", "biosure/legacy_benchmark.py", "results/source_manifest.json",
            "results/dke_prior_aggregate.json", MANIFEST}
PUBLIC_DOCS = {"public-submission.md", "workflow-scenario.md", "practical-validation.md",
               "public-readme.md", "public-rights.md"}


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.relative_to(root).parts[0] != ".git"
            and p.relative_to(root).as_posix() != MANIFEST}


def verify_manifest(root: Path) -> None:
    value = loads_json((root / MANIFEST).read_text(encoding="utf-8"))
    if value.get("profile") != "biosure-public-no-prior-v1" or value.get("files") != _files(root):
        raise ValueError("release manifest mismatch")


def prepare(source: Path, destination: Path, *, local_preview: bool = False) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("release destination must be outside source")
    if destination.exists():
        raise ValueError("release destination already exists")
    if not destination.parent.is_dir():
        raise ValueError("release parent must already exist")
    # A unique temporary directory is owned by this invocation and is removed
    # by the context manager. No user directory is recursively cleaned.
    with tempfile.TemporaryDirectory(prefix="biosure-export-") as temp:
        staging = Path(temp)
        for path in sorted(source.rglob("*")):
            if path.is_symlink() or path.is_junction():
                raise ValueError("symlink/junction source is not exportable")
            if not path.is_file():
                continue
            relative = path.relative_to(source).as_posix()
            if relative in EXCLUDED or not _allowed(relative):
                continue
            if relative.startswith("report/") and path.name not in PUBLIC_DOCS:
                continue
            output = staging / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
        for incoming, outgoing in (("report/public-readme.md", "README.md"), ("report/public-rights.md", "RIGHTS.md")):
            if not (source / incoming).is_file():
                raise ValueError("missing public-profile document: " + incoming)
            shutil.copyfile(source / incoming, staging / outgoing)
        readme = staging / "README.md"
        content = readme.read_text(encoding="utf-8")
        for name in PUBLIC_DOCS:
            content = content.replace("(" + name + ")", "(report/" + name + ")")
        content = content.replace("(../RIGHTS.md)", "(RIGHTS.md)")
        readme.write_text(content, encoding="utf-8", newline="\n")
        findings = audit(staging)
        def permission_only(finding: str) -> bool:
            return finding == "missing required file: LICENSE" or finding.startswith("missing rights approval:")
        if findings and (not local_preview or any(not permission_only(f) for f in findings)):
            raise ValueError("release audit blocked: " + "; ".join(findings))
        manifest = {"schema_version": "biosure.release-manifest/1.0", "profile": "biosure-public-no-prior-v1",
                    "cleared_for_public_release": not findings and not local_preview, "audit_findings": findings,
                    "files": _files(staging), "limitations": "Content hashes do not authenticate authorship or source truth."}
        (staging / "results").mkdir(exist_ok=True)
        (staging / MANIFEST).write_bytes(canonical_bytes(manifest))
        final_findings = audit(staging)
        if final_findings and (not local_preview or any(not permission_only(f) for f in final_findings)):
            raise ValueError("release audit blocked after manifest: " + "; ".join(final_findings))
        shutil.copytree(staging, destination)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--local-preview", action="store_true", help="Allow only disclosed pending-permission findings; never a public clearance")
    args = parser.parse_args()
    try:
        value = prepare(args.source, args.destination, local_preview=args.local_preview)
        print(json.dumps({"profile": value["profile"], "files": len(value["files"]), "published": False,
                          "cleared_for_public_release": value["cleared_for_public_release"], "audit_findings": value["audit_findings"]}))
        return 0
    except (OSError, ValueError) as error:
        print("BLOCK: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
