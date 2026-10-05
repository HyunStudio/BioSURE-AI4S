"""Validate local BioSURE comparison-study exports without collecting them."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path


FROZEN_MANIFEST_SHA = "dc5d335ec5a6e1b4295cd69d8a7337cfc6a54ada33a2d88442d88038d63f71a0"
MODES = ("manual", "diff", "biosure")
DIFFERENCES = {"yes", "no", "unsure"}
DISPOSITIONS = {"keep", "copy", "escalate"}
BASES = {"fictional-author-key", "independent-adjudication", "source-derived"}
SESSION_SCOPE = "instrument-only; automated or human origin must be reported separately"
SESSION_FIELDS = {"schema_version", "study_scope", "manifest_sha256", "assignment_slot", "records"}
RECORD_FIELDS = {"task_id", "source_kind", "mode", "difference",
                 "first_changed_reference_position", "disposition", "active_ms", "wall_ms"}


def _exact_fields(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"invalid {label} fields")
    return value


def _int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid JSON input") from error


def load_manifest(path: Path) -> dict:
    """Load only the frozen nine-task instrument and verify its task digest."""
    bundle = _read_json(path)
    if not isinstance(bundle, dict) or bundle.get("schema_version") != "biosure.practical-study/1.0":
        raise ValueError("invalid study manifest")
    tasks = bundle.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 9 or not all(isinstance(t, dict) for t in tasks):
        raise ValueError("invalid study manifest tasks")
    digest = hashlib.sha256(_canonical(tasks)).hexdigest()
    if bundle.get("manifest_sha256") != FROZEN_MANIFEST_SHA or digest != FROZEN_MANIFEST_SHA:
        raise ValueError("study manifest digest mismatch")
    ids = [task.get("id") for task in tasks]
    if any(not isinstance(task_id, str) or not task_id for task_id in ids) or len(set(ids)) != 9:
        raise ValueError("invalid study manifest task ids")
    if sum(task.get("kind") == "fictional" for task in tasks) != 6 or sum(
        task.get("kind") == "public-article" for task in tasks
    ) != 3:
        raise ValueError("invalid study manifest task mix")
    for task in tasks:
        paragraphs = task.get("input", {}).get("reference_paragraphs") if isinstance(task.get("input"), dict) else None
        if not isinstance(paragraphs, list) or not paragraphs or not all(
            isinstance(text, str) and text for text in paragraphs
        ):
            raise ValueError("invalid study manifest reference paragraphs")
    return bundle


def validate_session(session: dict, bundle: dict) -> dict:
    """Reject incomplete, altered or identifier-bearing participant exports."""
    _exact_fields(session, SESSION_FIELDS, "session")
    if session["schema_version"] != "biosure.practical-study-session/1.0" or (
        session["study_scope"] != SESSION_SCOPE or
        session["manifest_sha256"] != bundle["manifest_sha256"]
    ):
        raise ValueError("session manifest/schema mismatch")
    slot = session["assignment_slot"]
    if not _int(slot) or slot not in range(6):
        raise ValueError("invalid assignment slot")
    records = session["records"]
    if not isinstance(records, list) or len(records) != 9:
        raise ValueError("session must contain nine records")
    tasks = {task["id"]: (index, task) for index, task in enumerate(bundle["tasks"])}
    seen = set()
    for record in records:
        _exact_fields(record, RECORD_FIELDS, "record")
        task_id = record["task_id"]
        if not isinstance(task_id, str) or task_id not in tasks or task_id in seen:
            raise ValueError("unknown or duplicate study task")
        seen.add(task_id)
        index, task = tasks[task_id]
        if record["source_kind"] != task["kind"]:
            raise ValueError("source kind mismatch")
        if record["mode"] != MODES[(index + slot) % 3]:
            raise ValueError("mode does not match assignment slot")
        difference = record["difference"]
        if (not isinstance(difference, str) or difference not in DIFFERENCES or
            not isinstance(record["disposition"], str) or record["disposition"] not in DISPOSITIONS):
            raise ValueError("invalid study answer")
        position = record["first_changed_reference_position"]
        if difference == "yes":
            if not _int(position) or not 0 <= position <= len(task["input"]["reference_paragraphs"]):
                raise ValueError("invalid changed position")
        elif position is not None:
            raise ValueError("position must be empty for no/unsure")
        active, wall = record["active_ms"], record["wall_ms"]
        if not _int(active) or not _int(wall) or active < 0 or wall < active:
            raise ValueError("invalid active/wall duration")
    return session


def session_fingerprint(session: dict) -> str:
    """Identify content-equivalent re-submissions; not repeated people."""
    payload = {"assignment_slot": session["assignment_slot"],
               "records": sorted(session["records"], key=lambda record: record["task_id"])}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _validate_key(key: dict, bundle: dict) -> dict:
    _exact_fields(key, {"schema_version", "manifest_sha256", "answers"}, "key")
    if key["schema_version"] != "biosure.practical-study-key/1.0" or (
        key["manifest_sha256"] != bundle["manifest_sha256"]
    ) or not isinstance(key["answers"], dict):
        raise ValueError("invalid study key schema or digest")
    tasks = {task["id"]: task for task in bundle["tasks"]}
    for task_id, answer in key["answers"].items():
        if task_id not in tasks or not isinstance(answer, dict) or (
            set(answer) not in ({"difference", "basis"},
                                {"difference", "first_changed_reference_position", "basis"})
        ):
            raise ValueError("invalid study key task or fields")
        if (not isinstance(answer["difference"], str) or answer["difference"] not in {"yes", "no"} or
            not isinstance(answer["basis"], str) or answer["basis"] not in BASES):
            raise ValueError("invalid study key answer")
        position = answer.get("first_changed_reference_position")
        if position is not None and (answer["difference"] != "yes" or not _int(position) or
                                     not 0 <= position <= len(tasks[task_id]["input"]["reference_paragraphs"])):
            raise ValueError("invalid study key position")
    return key


def load_key(path: Path, bundle: dict) -> dict:
    """Read optional analyst-held labels, never embedded in the study UI."""
    return _validate_key(_read_json(path), bundle)


def _empty_group() -> dict:
    return {"records": 0,
            "difference_counts": {"yes": 0, "no": 0, "unsure": 0},
            "disposition_counts": {"keep": 0, "copy": 0, "escalate": 0},
            "difference_scored": 0, "difference_exact": 0,
            "position_scored": 0, "position_exact": 0,
            "_active": [], "_wall": []}


def _time_summary(values: list[int]) -> dict:
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def _finish_group(group: dict) -> dict:
    return {key: value for key, value in group.items() if not key.startswith("_")} | {
        "active_ms": _time_summary(group["_active"]),
        "wall_ms": _time_summary(group["_wall"]),
    }


def summarize_sessions(bundle: dict, sessions: list[dict], key: dict | None = None,
                       withdrawals: int | None = None) -> dict:
    """Describe records; never infer participants, causality, or natural truth."""
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("at least one study session is required")
    if withdrawals is not None and (not _int(withdrawals) or withdrawals < 0):
        raise ValueError("withdrawal count must be a nonnegative integer")
    if key is not None:
        _validate_key(key, bundle)
    task_by_id = {task["id"]: task for task in bundle["tasks"]}
    modes = {mode: _empty_group() for mode in MODES}
    cases = {task["id"]: {"source_kind": task["kind"], **_empty_group()}
             for task in bundle["tasks"]}
    fingerprints = set()
    slots = set()
    for session in sessions:
        validate_session(session, bundle)
        fingerprint = session_fingerprint(session)
        if fingerprint in fingerprints:
            raise ValueError("duplicate study session content")
        fingerprints.add(fingerprint)
        slots.add(session["assignment_slot"])
        for record in session["records"]:
            task_id = record["task_id"]
            task = task_by_id[task_id]
            answer = key["answers"].get(task_id) if key is not None else None
            scored = bool(answer) and (
                answer["basis"] == "independent-adjudication" or
                (task["kind"] == "fictional" and answer["basis"] == "fictional-author-key")
            )
            for group in (modes[record["mode"]], cases[task_id]):
                group["records"] += 1
                group["difference_counts"][record["difference"]] += 1
                group["disposition_counts"][record["disposition"]] += 1
                group["_active"].append(record["active_ms"])
                group["_wall"].append(record["wall_ms"])
                if scored:
                    group["difference_scored"] += 1
                    group["difference_exact"] += record["difference"] == answer["difference"]
                    expected_position = answer.get("first_changed_reference_position")
                    if answer["difference"] == "yes" and expected_position is not None:
                        group["position_scored"] += 1
                        group["position_exact"] += (
                            record["difference"] == "yes" and
                            record["first_changed_reference_position"] == expected_position
                        )
    missing = sorted(set(range(6)) - slots)
    warnings = []
    if len(sessions) < 6 or missing:
        warnings.append("Incomplete six-slot coverage; summaries are descriptive even with all six slots.")
    return {
        "schema_version": "biosure.practical-study-analysis/1.0",
        "manifest_sha256": bundle["manifest_sha256"],
        "scope": "Local descriptive software output; human origin and independent adjudication are not verified by this script.",
        "session_count": len(sessions),
        "slot_coverage": {"present": sorted(slots), "missing": missing},
        "withdrawals_owner_reported": withdrawals,
        "warnings": warnings,
        "modes": {mode: _finish_group(group) for mode, group in modes.items()},
        "cases": {task_id: _finish_group(group) for task_id, group in cases.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze locally held BioSURE study JSON exports")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, nargs="+", required=True)
    parser.add_argument("--key", type=Path, help="Separately held answer/adjudication key")
    parser.add_argument("--withdrawals", type=int, help="Owner-reported count; omitted means unknown")
    parser.add_argument("--out", type=Path, help="New summary JSON path; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        bundle = load_manifest(args.manifest)
        sessions = [_read_json(path) for path in args.sessions]
        key = load_key(args.key, bundle) if args.key else None
        summary = summarize_sessions(bundle, sessions, key, args.withdrawals)
        rendered = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.out is None:
            sys.stdout.write(rendered)
        else:
            with args.out.open("x", encoding="utf-8", newline="\n") as output:
                output.write(rendered)
        return 0
    except FileExistsError:
        print("summary output already exists", file=sys.stderr)
        return 2
    except (ValueError, OSError) as error:
        print(f"study analysis error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
