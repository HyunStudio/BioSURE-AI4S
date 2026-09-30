"""Local BioSURE inspection and in-memory paragraph QC server."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .evaluate import decide_case, score_case, summarize
from .schema import canonical_bytes, parse_request, loads_json
from .workflow import decision_payload, run_workflow, run_proposal
from .batch import run_batch
from .pdf_extract import MAX_PDF_BYTES, extract_pdf
from .ml_review import review_paragraphs, validate_model


STATIC = Path(__file__).resolve().parent / "static"


class LocalHTTPServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR can let a second instance bind the same port.
    # A launch collision must fail rather than ambiguously route local inputs.
    allow_reuse_address = False


def make_server(fixtures: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("BioSURE input server must bind to loopback only")
    fixtures = fixtures.resolve()
    model_path = fixtures / "ml_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8")) if model_path.is_file() else None
    if model is not None:
        validate_model(model)
    evaluation_path = fixtures.parent / "results" / "ml_evaluation.json"
    ml_summary = None
    if evaluation_path.is_file():
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        split = evaluation["split"]
        methods = evaluation["held_out"]["correspondence"]
        comparison = evaluation["held_out"]["learned_minus_best_lexical"]
        ml_summary = {"sources": {key: len(split[key + "_sources"]) for key in ("train", "dev", "test")},
                      "queries": methods["learned_logistic"]["queries"],
                      "learned_correct": methods["learned_logistic"]["correct"],
                      "best_lexical_correct": methods[comparison["baseline"]]["correct"],
                      "baseline": comparison["baseline"],
                      "accuracy_delta": comparison["accuracy_delta"],
                      "unit_control_positives": evaluation["held_out"]["critical_alerts"]["UNIT_CHANGED"]["tp"],
                      "scope": "Constructed article-source holdout, not natural PDF-error or clinical validation."}
    datasets = {
        "synthetic": ("challenge", "gold", "Public synthetic challenge",
                      "Project-authored graphs with constructed faults. Two source graphs underlie eight paired cases."),
        "article": ("article_challenge", "article_gold", "Article-derived structural probe",
                    "Three PMC articles with constructed faults. Reference and gold use the same JATS records; this is an exploratory structural probe."),
        "stress": ("stress_challenge", "stress_gold", "Exploratory stress suite",
                   "Twelve project-authored graphs, fourteen conditions each. Deliberately forged reference evidence causes incorrect application; not a real-world error estimate."),
    }
    prior = fixtures.parent / "results" / "dke_prior_aggregate.json"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def respond(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def json(self, value: object, status: int = 200) -> None:
            self.respond(canonical_bytes(value), "application/json; charset=utf-8", status)

        def local_request(self) -> bool:
            try:
                hosts = self.headers.get_all("Host", [])
                if len(hosts) != 1:
                    return False
                host = urlsplit("http://" + hosts[0])
                if host.hostname not in {"127.0.0.1", "localhost"} or host.port != self.server.server_address[1]:
                    return False
                origins = self.headers.get_all("Origin", [])
                if origins and (len(origins) != 1 or origins[0] != "http://" + hosts[0]):
                    return False
                return self.headers.get("Sec-Fetch-Site") != "cross-site"
            except ValueError:
                return False

        def do_POST(self) -> None:
            if not self.local_request():
                self.json({"error": "Local same-origin requests only"}, 403)
                return
            endpoint = urlsplit(self.path).path
            if endpoint not in {"/api/workflow", "/api/proposal", "/api/decide", "/api/batch", "/api/pdf-extract", "/api/ml-review"}:
                self.json({"error": "not found"}, 404)
                return
            pdf_upload = endpoint == "/api/pdf-extract"
            expected_type = "application/pdf" if pdf_upload else "application/json"
            if self.headers.get_content_type() != expected_type:
                self.json({"error": expected_type + " required"}, 415)
                return
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1:
                    self.json({"error": "one Content-Length required"}, 411)
                    return
                length = int(lengths[0])
                if length < 0:
                    raise ValueError("negative length")
                limit = MAX_PDF_BYTES if pdf_upload else 1048576
                if length > limit:
                    self.json({"error": "Input exceeds " + ("16 MiB" if pdf_upload else "1 MiB")}, 413)
                    # Windows can discard the response with a TCP reset if a
                    # normal oversized upload is closed with unread bytes.
                    # Drain only a bounded amount/time; never parse or retain it.
                    self.connection.settimeout(1)
                    try:
                        remaining = min(length, 32 * 1024 * 1024)
                        while remaining:
                            chunk = self.rfile.read(min(remaining, 65536))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    except OSError:
                        pass
                    return
                self.connection.settimeout(5)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("incomplete body")
                if pdf_upload:
                    self.json(extract_pdf(body))
                    return
                payload = loads_json(body.decode("utf-8"))
                if endpoint == "/api/workflow":
                    result = run_workflow(payload)
                elif endpoint == "/api/ml-review":
                    if model is None:
                        self.json({"error": "Learned model unavailable in these fixtures"}, 503)
                        return
                    result = review_paragraphs(payload, model)
                elif endpoint == "/api/proposal":
                    result = run_proposal(payload)
                elif endpoint == "/api/batch":
                    result = run_batch(payload)
                else:
                    request = parse_request(payload)
                    if (len(request.candidates) > 32 or len(request.damaged.blocks) > 128
                            or any(len(item.document.blocks) > 128 for item in request.candidates)
                            or len(request.evidence.trusted_insertions) + len(request.evidence.trusted_identities) > 256):
                        raise ValueError("decision size limit")
                    result = decision_payload(request)
                self.json(result)
            except TimeoutError:
                self.json({"error": "Input read timeout"}, 408)
            except (ValueError, UnicodeError, RecursionError):
                self.json({"error": "Invalid input; check schema and size limits"}, 400)

        def do_GET(self) -> None:
            if not self.local_request():
                self.json({"error": "Local same-origin requests only"}, 403)
                return
            url = urlsplit(self.path)
            path = unquote(url.path)
            try:
                selections = parse_qs(url.query, keep_blank_values=True).get("dataset", ["synthetic"])
                if len(selections) != 1 or selections[0] not in datasets:
                    self.json({"error": "invalid dataset"}, 400)
                    return
                dataset = selections[0]
                if path == "/api/examples/batch":
                    self.json(loads_json((fixtures / "workflow_examples.json").read_text(encoding="utf-8")))
                    return
                if path == "/api/ml-summary":
                    if ml_summary is None:
                        self.json({"error": "Learned evaluation unavailable"}, 404)
                    else:
                        self.json(ml_summary)
                    return
                case_dir, gold_dir, label, note = datasets[dataset]
                cases, gold = fixtures / case_dir, fixtures / gold_dir
                if path == "/api/cases":
                    self.json({"dataset": dataset, "label": label, "note": note,
                               "cases": [file.stem for file in sorted(cases.glob("*.json"))]})
                    return
                if path.startswith("/api/case/"):
                    case_id = path.removeprefix("/api/case/")
                    allowed = {file.stem: file for file in cases.glob("*.json")}
                    if case_id not in allowed:
                        self.json({"error": "case not found"}, 404)
                        return
                    record = decide_case(allowed[case_id])
                    selected = next(
                        (item for item in record.request.candidates if item.candidate_id == record.decision.candidate_id),
                        None,
                    )
                    source = None
                    if dataset == "article":
                        provenance = json.loads((fixtures / "article_provenance.json").read_text(encoding="utf-8"))
                        article = next(item for item in provenance["articles"]
                                       if record.request.damaged.record_id == "article-" + item["pmcid"])
                        source = {key: article[key] for key in ("pmcid", "title", "doi", "article_url", "license_uri")}
                    self.json(
                        {
                            "mode": "candidate_dependent_demo",
                            "case_id": case_id,
                            "dataset": dataset,
                            "source": source,
                            "request": record.request.to_mapping(),
                            "decision": {
                                "action": record.decision.action,
                                "candidate_id": record.decision.candidate_id,
                                "reason_codes": list(record.decision.reason_codes),
                            },
                            "selected_output": selected.document.to_mapping() if selected else None,
                            "receipt": record.receipt,
                        }
                    )
                    return
                if path == "/api/summary":
                    paths = sorted(cases.glob("*.json"))
                    self.json({"mode": "candidate_dependent_public_evaluation", "dataset": dataset,
                               **summarize([score_case(decide_case(file), gold / file.name) for file in paths])})
                    return
                if path == "/api/prior":
                    if not prior.is_file():
                        self.json({"included": False, "error": "Prior data is excluded from this release profile"}, 404)
                        return
                    self.json(json.loads(prior.read_text(encoding="utf-8")))
                    return
                static_files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/workflow.js": ("workflow.js", "text/javascript; charset=utf-8"), "/batch.js": ("batch.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}
                if path in static_files:
                    filename, content_type = static_files[path]
                    self.respond((STATIC / filename).read_bytes(), content_type)
                    return
                self.json({"error": "not found"}, 404)
            except (OSError, ValueError, KeyError, StopIteration, json.JSONDecodeError):
                self.json({"error": "demo data unavailable"}, 500)

    return LocalHTTPServer((host, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local BioSURE demo")
    parser.add_argument("--fixtures", type=Path, default=STATIC.parent.parent / "fixtures")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if not 0 <= args.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if not (args.fixtures / "challenge").is_dir() or not (args.fixtures / "workflow_examples.json").is_file():
            raise ValueError("fixtures directory is missing required challenge/examples")
        server = make_server(args.fixtures, args.host, args.port)
    except (OSError, ValueError) as error:
        print(f"BioSURE could not start: {error}. Check --fixtures or choose a different --port.", file=sys.stderr)
        return 2
    print(f"BioSURE demo: http://{args.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
