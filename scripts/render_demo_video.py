"""Optional local browser capture for an evidence-bound BioSURE demo preview."""

from __future__ import annotations

import json
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))


def validate_output(path: Path, source_root: Path) -> Path:
    source = source_root.resolve()
    output = path.resolve()
    if output.suffix.lower() != ".mp4":
        raise ValueError("demo output must end in .mp4")
    if output == source or output.is_relative_to(source):
        raise ValueError("demo output must be outside the source tree")
    if not output.parent.is_dir():
        raise ValueError("demo output parent directory must already exist")
    if output.exists():
        raise ValueError("demo output already exists")
    return output


def parse_policy_summary(text: str) -> dict:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid policy summary JSON") from error
    expected = {"contract_checks": 5, "contract_passed": 5, "exposure_auto_repairs": 0}
    if not isinstance(value, dict) or set(value) != set(expected) or any(
        type(value[key]) is not int or value[key] != expected[key] for key in expected
    ):
        raise ValueError("unexpected policy summary; recheck claims before filming")
    return value


def shot_manifest() -> tuple[dict, ...]:
    return (
        {"id": "intro", "seconds": 10, "caption": "PDF conversion or AI proposals can silently change research text. BioSURE exposes differences and withholds unsupported edits."},
        {"id": "trial-text", "seconds": 24, "caption": "Paste your own text: the real Python workflow and correspondence model run inside this browser. Fictional sample; ABSTAIN, no output applied."},
        {"id": "trial-pdf", "seconds": 42, "caption": "Import a project-authored one-page PDF text layer locally. Extracted page text is unverified. Check the original page; ABSTAIN. No output applied."},
        {"id": "judge-public", "seconds": 12, "caption": "Judge Mode is a separate fixed-case static replay, not a live upload. Its public article sample also abstains."},
        {"id": "policy", "seconds": 15, "caption": "Fictional contract checks 5/5; separate forged-reference control: 0/1 AUTO_REPAIR. Source not authenticated; not 6/6 safety."},
        {"id": "replay", "seconds": 11, "caption": "Reproduce locally: python scripts/verify_reproduction.py . Results are not biological validation or a user study."},
        {"id": "outro", "seconds": 8, "caption": "BioSURE is a review aid, not an automatic correction service. Verify the original source before scientific use."},
    )


def validate_shots(shots: tuple[dict, ...]) -> int:
    required = {"trial-text", "trial-pdf", "judge-public", "policy"}
    if not isinstance(shots, tuple) or any(not isinstance(shot, dict) for shot in shots):
        raise ValueError("invalid demo shot manifest")
    ids = [shot.get("id") for shot in shots]
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("invalid demo shot IDs")
    missing = required - set(ids)
    if missing:
        raise ValueError("missing demo shot: " + ", ".join(sorted(missing)))
    if any(type(shot.get("seconds")) is not int or shot["seconds"] <= 0
           or not isinstance(shot.get("caption"), str) or not shot["caption"].strip()
           for shot in shots):
        raise ValueError("invalid demo shot duration or caption")
    total = sum(shot["seconds"] for shot in shots)
    if total > 180:
        raise ValueError("demo shot budget exceeds 180 seconds")
    by_id = {shot["id"]: shot["caption"] for shot in shots}
    if ("conversion" not in by_id["intro"].lower() or "unsupported" not in by_id["intro"].lower()):
        raise ValueError("demo opening must state the problem and bounded value")
    if ("inside this browser" not in by_id["trial-text"]
            or "ABSTAIN" not in by_id["trial-text"]
            or "PDF text layer locally" not in by_id["trial-pdf"]
            or "unverified" not in by_id["trial-pdf"]
            or "No output applied" not in by_id["trial-pdf"]
            or "static replay" not in by_id["judge-public"].lower()
            or not all(phrase in by_id["policy"] for phrase in ("5/5", "0/1", "AUTO_REPAIR", "forged-reference"))):
        raise ValueError("demo captions conceal the source or policy boundary")
    return total


def write_fictional_pdf(path: Path) -> None:
    """Make the one-page project-authored input used by the recorded PDF trial."""
    from reportlab.pdfgen.canvas import Canvas

    pdf = Canvas(str(path), pagesize=(612, 792))
    pdf.setTitle("BioSURE fictional PDF trial")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, 710, "Fictional document-conversion control")
    pdf.setFont("Helvetica", 13)
    pdf.drawString(72, 665, "Fictional chip inlet closed.")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 90, "Project-authored demonstration. Not a research article or clinical record.")
    pdf.save()


def evidence_card(kind: str, policy: dict) -> str:
    if kind == "policy":
        title = "Actual local policy-audit CLI output"
        body = ("<pre>python scripts/evaluate_policy_boundary.py verify --root .\n"
                + html.escape(json.dumps(policy, sort_keys=True)) + "</pre>"
                "<p>Five fictional contract checks; one separate forged-reference control, with no automatic repair. This is not source authentication or 6/6 safety.</p>")
    elif kind == "replay":
        title = "Reproduce the evidence offline"
        body = ("<pre>python scripts/verify_reproduction.py .</pre>"
                "<p>Replays frozen comparisons, receipts and the policy audit. No paid API or model download.</p>")
    elif kind == "outro":
        title = "Inspect the source and limitations"
        body = ("<pre>github.com/HyunStudio/BioSURE-AI4S</pre>"
                "<p>Offline research-data review aid. Verify the original source before scientific use.</p>")
    else:
        raise ValueError("unknown demo evidence card")
    return ("<!doctype html><html><head><meta charset='utf-8'><title>BioSURE local replay</title>"
            "<style>body{margin:0;background:#091419;color:#e7eff1;font:25px Segoe UI,Arial,sans-serif}"
            "main{max-width:1100px;margin:65px auto;padding:30px}h1{font-size:42px}"
            "pre{white-space:pre-wrap;background:#102126;padding:28px;border:1px solid #527079;"
            "border-radius:12px;font:25px/1.5 Consolas,monospace}</style></head><body><main>"
            "<h1>" + title + "</h1>" + body + "</main></body></html>")


def require_ui_state(label: str, actual: str, expected: str) -> None:
    if expected not in actual:
        raise ValueError(f"{label} displayed {actual!r}, expected {expected!r}")


def require_pdf_review_state(changes: str, gate: str, selected: str) -> None:
    """The authored PDF includes page furniture, so its chunk is CHANGED, not MISSING."""
    if not changes.startswith("CHANGED ·") or not gate.startswith("ABSTAIN") or "No output applied" not in selected:
        raise ValueError("PDF trial did not show the expected changed review and abstention")


@contextmanager
def _local_servers(root: Path):
    from biosure.web_demo import make_server

    app = make_server(root / "fixtures", "127.0.0.1", 0)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

    static_handler = partial(QuietHandler, directory=str(root / "docs"))
    static = ThreadingHTTPServer(("127.0.0.1", 0), static_handler)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (app, static)]
    for thread in threads:
        thread.start()
    try:
        yield (f"http://127.0.0.1:{app.server_address[1]}/",
               f"http://127.0.0.1:{static.server_address[1]}/")
    finally:
        for server in (app, static):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)


def _caption(page: object, text: str) -> None:
    page.evaluate("""text => {
      let box = document.getElementById('biosure-video-caption');
      if (!box) {
        box = document.createElement('div');
        box.id = 'biosure-video-caption';
        box.style.cssText = 'position:fixed;left:24px;right:24px;bottom:20px;z-index:2147483647;'
          + 'padding:13px 18px;background:rgba(2,18,24,.94);border:1px solid #87deb9;'
          + 'border-radius:10px;color:#fff;font:600 22px/1.35 Segoe UI,Arial,sans-serif;'
          + 'box-shadow:0 10px 26px rgba(0,0,0,.38);pointer-events:none;';
        document.body.appendChild(box);
      }
      box.textContent = text;
    }""", text)


def _hold(page: object, shot: dict) -> None:
    _caption(page, shot["caption"])
    page.wait_for_timeout(shot["seconds"] * 1000)


def _policy_output(root: Path) -> dict:
    result = subprocess.run([sys.executable, "-B", "scripts/evaluate_policy_boundary.py", "verify", "--root", "."],
                            cwd=root, text=True, capture_output=True, timeout=30, check=False)
    if result.returncode != 0:
        raise ValueError("policy audit command failed: " + result.stderr.strip()[:300])
    return parse_policy_summary(result.stdout)


def _ffmpeg_validate(ffmpeg: str, mp4: Path) -> float:
    checked = subprocess.run([ffmpeg, "-hide_banner", "-i", str(mp4), "-map", "0:v:0", "-f", "null", os.devnull],
                             text=True, capture_output=True, timeout=240, check=False)
    if checked.returncode != 0:
        raise ValueError("video decode failed: " + checked.stderr[-400:])
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", checked.stderr)
    if not match or "Audio:" in checked.stderr:
        raise ValueError("video duration/audio validation failed")
    duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    if not 0 < duration <= 180:
        raise ValueError("video exceeds the 180-second preview budget")
    return duration


def frame_has_gray_padding(rgb: bytes, width: int, height: int) -> bool:
    """Catch Playwright's gray letterbox around a shrunken browser surface."""
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise ValueError("invalid decoded demo frame")
    points = ((.85, .20), (.85, .75), (.20, .85), (.50, .85))
    gray = 0
    for x, y in points:
        offset = (int(y * (height - 1)) * width + int(x * (width - 1))) * 3
        pixel = rgb[offset:offset + 3]
        if min(pixel) >= 100 and max(pixel) <= 160 and max(pixel) - min(pixel) <= 6:
            gray += 1
    return gray >= 3


def _verify_capture_frame_fill(ffmpeg: str, mp4: Path) -> None:
    for second in (5, 40, 90, 115):
        frame = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(mp4),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            capture_output=True, timeout=30, check=False,
        )
        if frame.returncode != 0 or len(frame.stdout) != 1280 * 720 * 3:
            raise ValueError(f"could not decode demo frame at {second}s")
        if frame_has_gray_padding(frame.stdout, 1280, 720):
            raise ValueError(f"gray recording padding at {second}s; do not publish")


def _publish_video(provisional: Path, destination: Path) -> None:
    """Copy completely, then publish without replacing another file."""
    if destination.exists():
        raise FileExistsError(destination)
    temporary: Path | None = None
    try:
        with provisional.open("rb") as source, tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".biosure-demo-", suffix=".mp4", delete=False
        ) as target:
            temporary = Path(target.name)
            shutil.copyfileobj(source, target)
        # A hard link is atomic and refuses an existing destination on both
        # Windows and POSIX; a rename would replace it on POSIX.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def render(source_root: Path, output: Path, chrome_executable: Path | None = None) -> dict:
    root = source_root.resolve()
    destination = validate_output(output, root)
    if root != SOURCE_ROOT:
        raise ValueError("capture script and --root must use the same source tree")
    shots = shot_manifest()
    validate_shots(shots)
    if not (root / "docs/try/engine.zip").is_file() or not (root / "docs/judge/data.json").is_file():
        raise ValueError("source root lacks the live browser trial or Judge Mode")
    if chrome_executable is not None and not chrome_executable.is_file():
        raise ValueError("Chrome executable not found")
    try:
        from playwright.sync_api import sync_playwright
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError as error:
        raise ValueError("optional video dependencies missing: install playwright and imageio-ffmpeg") from error
    ffmpeg = get_ffmpeg_exe()
    checked_states: list[str] = []
    by_id = {shot["id"]: shot for shot in shots}
    policy = _policy_output(root)
    with tempfile.TemporaryDirectory(prefix="biosure-demo-") as temporary:
        temp = Path(temporary)
        pdf_file = temp / "fictional-chip-conversion.pdf"
        write_fictional_pdf(pdf_file)
        with _local_servers(root) as (_, docs_url):
            with sync_playwright() as playwright:
                launch = {"executable_path": str(chrome_executable)} if chrome_executable else {"channel": "chrome"}
                browser = playwright.chromium.launch(headless=True, **launch)
                try:
                    context = browser.new_context(viewport={"width": 1280, "height": 720},
                                                  record_video_dir=str(temp),
                                                  record_video_size={"width": 1280, "height": 720})
                    page = context.new_page()
                    page.set_viewport_size({"width": 1280, "height": 720})
                    video = page.video
                    try:
                        page.goto(docs_url + "try/", wait_until="domcontentloaded")
                        if page.evaluate("({width: innerWidth, height: innerHeight})") != {"width": 1280, "height": 720}:
                            raise ValueError("demo browser viewport does not match recorded frame")
                        page.locator("#run").wait_for(state="visible")
                        require_ui_state("live trial ready", page.locator("#status").inner_text(), "Ready")
                        _hold(page, by_id["intro"])

                        reference = "Fictional chip inlet closed.\n\nFictional chip flow rate five."
                        observed = "Fictional chip inlet closed."
                        page.locator("#reference").fill(reference)
                        page.locator("#observed").fill(observed)
                        page.locator("#ack").check()
                        page.locator("#run").click()
                        page.locator("#result").wait_for(state="visible", timeout=90000)
                        require_ui_state("pasted-text gate", page.locator("#gate-action").inner_text(), "ABSTAIN")
                        require_ui_state("pasted-text selection", page.locator("#selected").inner_text(), "No output applied")
                        require_ui_state("pasted-text diff", page.locator("#changes").inner_text(), "MISSING")
                        checked_states.append("trial-text")
                        page.locator("#gate-action").scroll_into_view_if_needed()
                        _hold(page, by_id["trial-text"])

                        page.goto(docs_url + "try/", wait_until="domcontentloaded")
                        page.locator("#reference").fill(reference)
                        page.locator("#pdf-file").set_input_files(str(pdf_file))
                        page.locator("#import-pdf").click()
                        page.wait_for_function("document.getElementById('status').textContent.includes('Extracted 1 page-text chunk')", timeout=90000)
                        extracted = page.locator("#observed").input_value()
                        require_ui_state("PDF extraction", extracted, observed)
                        if "Fictional chip flow rate five." in extracted:
                            raise ValueError("PDF unexpectedly contains the missing reference paragraph")
                        _caption(page, "Synthetic one-page PDF imported in browser memory. Extracted page text is not a verified paragraph or source.")
                        page.wait_for_timeout(16000)
                        page.locator("#ack").check()
                        page.locator("#pdf-ack").check()
                        page.locator("#run").click()
                        page.locator("#result").wait_for(state="visible", timeout=90000)
                        require_pdf_review_state(page.locator("#changes").inner_text(),
                                                 page.locator("#gate-action").inner_text(),
                                                 page.locator("#selected").inner_text())
                        checked_states.append("trial-pdf")
                        page.locator("#gate-action").scroll_into_view_if_needed()
                        _caption(page, by_id["trial-pdf"]["caption"])
                        page.wait_for_timeout((by_id["trial-pdf"]["seconds"] - 16) * 1000)

                        page.goto(docs_url + "judge/", wait_until="domcontentloaded")
                        page.locator("#run-audit").wait_for(state="visible")
                        page.wait_for_function("!document.getElementById('run-audit').disabled")
                        page.locator("#run-audit").click()
                        require_ui_state("Judge public replay", page.locator("#workflow-action").inner_text(), "ABSTAIN")
                        require_ui_state("Judge static scope", page.locator("#result-status").inner_text(), "Static replay")
                        checked_states.append("judge-public")
                        page.locator("#workflow-action").scroll_into_view_if_needed()
                        _hold(page, by_id["judge-public"])

                        page.set_content(evidence_card("policy", policy))
                        _hold(page, by_id["policy"])
                        page.set_content(evidence_card("replay", policy))
                        _hold(page, by_id["replay"])
                        page.set_content(evidence_card("outro", policy))
                        _hold(page, by_id["outro"])
                    finally:
                        context.close()
                    webm = Path(video.path())
                finally:
                    browser.close()
        provisional = temp / "demo.mp4"
        encoded = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(webm),
                                  "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                                  "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-n", str(provisional)],
                                 text=True, capture_output=True, timeout=240, check=False)
        if encoded.returncode != 0:
            raise ValueError("video encode failed: " + encoded.stderr[-400:])
        duration = _ffmpeg_validate(ffmpeg, provisional)
        _verify_capture_frame_fill(ffmpeg, provisional)
        digest = hashlib.sha256(provisional.read_bytes()).hexdigest()
        _publish_video(provisional, destination)
        return {"duration_seconds": duration, "sha256": digest,
                "bytes": destination.stat().st_size, "policy_summary": policy,
                "checked_states": checked_states}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chrome-executable", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(render(args.root, args.output, args.chrome_executable), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print("Video preview blocked: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
