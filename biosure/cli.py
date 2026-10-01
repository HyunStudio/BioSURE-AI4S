"""Offline BioSURE command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluate import decide_case, score_case, summarize
from .schema import canonical_bytes, loads_json
from .workflow import run_workflow, run_proposal
from .batch import run_batch
from .pdf_extract import MAX_PDF_BYTES, extract_pdf


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_bytes(value))


def blind_evaluate(cases: Path, gold: Path, out: Path) -> dict:
    case_paths = sorted(cases.glob("*.json"))
    if not case_paths:
        raise ValueError("no challenge cases found")
    out.mkdir(parents=True, exist_ok=True)
    decisions = [decide_case(path) for path in case_paths]
    # Persist every outcome-free receipt before opening any gold path.
    (out / "decisions.jsonl").write_bytes(b"".join(canonical_bytes(record.receipt) for record in decisions))
    results = [score_case(record, gold / path.name) for path, record in zip(case_paths, decisions)]
    summary = {"mode": "candidate_dependent_public_evaluation", **summarize(results)}
    _write_json(out / "summary.json", summary)
    _write_json(out / "cases.json", [result.__dict__ for result in results])
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BioSURE offline structural-integrity demo")
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("blind-evaluate")
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--gold", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--case", type=Path, required=True)
    workflow = commands.add_parser("workflow")
    workflow.add_argument("--input", type=Path, required=True)
    proposal = commands.add_parser("proposal", help="Validate untrusted upstream proposed paragraphs offline")
    proposal.add_argument("--input", type=Path, required=True)
    batch = commands.add_parser("batch", help="Triage paragraph records without overwriting inputs")
    batch.add_argument("--input", type=Path, required=True)
    batch.add_argument("--out", type=Path, required=True)
    pdf = commands.add_parser("pdf-extract", help="Inspect a local PDF text layer; review against original pages")
    pdf.add_argument("--input", type=Path, required=True)
    commands.add_parser("legacy-demo")
    args = parser.parse_args(argv)
    try:
        if args.command == "blind-evaluate":
            print(json.dumps(blind_evaluate(args.cases, args.gold, args.out), sort_keys=True))
        elif args.command == "workflow":
            print(json.dumps(run_workflow(loads_json(args.input.read_text(encoding="utf-8"))), sort_keys=True))
        elif args.command == "proposal":
            if args.input.stat().st_size > 1048576:
                raise ValueError("proposal input exceeds 1 MiB")
            print(json.dumps(run_proposal(loads_json(args.input.read_text(encoding="utf-8"))), sort_keys=True))
        elif args.command == "batch":
            if args.input.stat().st_size > 8388608:
                raise ValueError("batch input exceeds 8 MiB")
            result = run_batch(loads_json(args.input.read_text(encoding="utf-8")))
            serialized = canonical_bytes(result)
            with args.out.open("xb") as output:
                output.write(serialized)
            print(json.dumps(result["summary"], sort_keys=True))
        elif args.command == "pdf-extract":
            if args.input.stat().st_size > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds 16 MiB")
            print(json.dumps(extract_pdf(args.input.read_bytes()), sort_keys=True))
        elif args.command == "demo":
            record = decide_case(args.case)
            print(
                json.dumps(
                    {
                        "mode": "candidate_dependent_demo",
                        "case_id": record.request.case_id,
                        "decision": {
                            "action": record.decision.action,
                            "candidate_id": record.decision.candidate_id,
                            "reason_codes": list(record.decision.reason_codes),
                        },
                        "receipt": record.receipt,
                    },
                    sort_keys=True,
                )
            )
        else:
            if not (Path(__file__).parent / "legacy.py").is_file():
                raise ValueError("Legacy diagnostics are not included in this public profile")
            from .legacy import legacy_demo
            print(json.dumps(legacy_demo(), sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"BioSURE input error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
