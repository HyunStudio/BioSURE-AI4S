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
        {"id": "public-abstain", "seconds": 23, "caption": "Real CC BY 4.0 article excerpt. The JATS reference is declared, not authenticated. No automatic change."},
        {"id": "fictional-omission", "seconds": 21, "caption": "Fictional internal omission: one bounded review candidate, SOURCE UNVERIFIED. No source file is changed or output applied."},
        {"id": "invented-proposal", "seconds": 17, "caption": "Invented upstream wording is rejected; a plausible AI suggestion is not evidence."},
        {"id": "judge-public", "seconds": 12, "caption": "Judge Mode public article title: static replay abstains. The declared source remains unverified."},
        {"id": "judge-fictional", "seconds": 12, "caption": "Judge Mode fictional bounded candidate: static replay abstains; no output is applied."},
        {"id": "study", "seconds": 12, "caption": "Nine-task comparison instrument: no participants or measured time benefit yet."},
        {"id": "policy", "seconds": 18, "caption": "Fictional contract checks 5/5; separate forged-reference control: 0/1 AUTO_REPAIR. Source not authenticated; not 6/6 safety."},
        {"id": "replay", "seconds": 12, "caption": "Reproduce locally: python scripts/verify_reproduction.py .  Results are not biological validation."},
        {"id": "outro", "seconds": 7, "caption": "BioSURE is an offline review aid. Verify the original source before any scientific use."},
    )


def validate_shots(shots: tuple[dict, ...]) -> int:
    required = {"public-abstain", "fictional-omission", "invented-proposal", "judge-public",
                "judge-fictional", "study", "policy"}
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
    if ("not authenticated" not in by_id["public-abstain"].lower()
            or "SOURCE UNVERIFIED" not in by_id["fictional-omission"]
            or "No source file" not in by_id["fictional-omission"]
            or "static replay" not in by_id["judge-public"].lower()
            or "static replay" not in by_id["judge-fictional"].lower()
            or "no participants" not in by_id["study"].lower()
            or not all(phrase in by_id["policy"] for phrase in ("5/5", "0/1", "AUTO_REPAIR", "forged-reference"))):
        raise ValueError("demo captions conceal the source or policy boundary")
    return total


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
    if not (root / "fixtures/workflow_examples.json").is_file() or not (root / "docs/judge/data.json").is_file():
        raise ValueError("source root lacks BioSURE fixtures or Judge Mode")
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
        with _local_servers(root) as (app_url, docs_url):
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
                        page.goto(app_url, wait_until="domcontentloaded")
                        if page.evaluate("({width: innerWidth, height: innerHeight})") != {"width": 1280, "height": 720}:
                            raise ValueError("demo browser viewport does not match recorded frame")
                        page.locator("#paragraph-check").wait_for()
                        _hold(page, by_id["intro"])

                        page.locator("#load-public-extraction").click()
                        page.locator("#public-source-link-row").wait_for(state="visible")
                        page.locator("#reference-ack").check()
                        page.locator("#run-workflow").click()
                        page.wait_for_function("['NO AUTOMATIC CHANGE', 'INPUT NOT ACCEPTED'].some(text => document.getElementById('workflow-status').textContent.includes(text))")
                        require_ui_state("public case", page.locator("#workflow-status").inner_text(), "NO AUTOMATIC CHANGE")
                        require_ui_state("public source", page.locator("#public-source-note").inner_text(), "CC BY 4.0")
                        checked_states.append("public-abstain")
                        page.locator("#workflow-status").scroll_into_view_if_needed()
                        _hold(page, by_id["public-abstain"])

                        page.locator("#load-example").click()
                        page.locator("#reference-ack").check()
                        page.locator("#run-workflow").click()
                        try:
                            page.wait_for_function("['NO AUTOMATIC CHANGE', 'INPUT NOT ACCEPTED'].some(text => document.getElementById('workflow-status').textContent.includes(text))")
                        except Exception as error:
                            raise ValueError("fictional omission did not finish: "
                                             + page.locator("#workflow-status").inner_text() + " / "
                                             + page.locator("#workflow-reason").inner_text()) from error
                        if page.locator("#workflow-status").inner_text() == "INPUT NOT ACCEPTED":
                            raise ValueError("fictional omission rejected: " + page.locator("#workflow-reason").inner_text())
                        require_ui_state("fictional omission", page.locator("#workflow-status").inner_text(), "NO AUTOMATIC CHANGE")
                        require_ui_state("fictional omission output", page.locator("#workflow-output").inner_text(), "No output applied")
                        if not page.locator("#workflow-receipt").inner_text().strip():
                            raise ValueError("fictional omission lacks a visible decision receipt")
                        checked_states.append("fictional-omission")
                        page.locator("#workflow-status").scroll_into_view_if_needed()
                        _hold(page, by_id["fictional-omission"])

                        reference = page.locator("#reference-input").input_value().split("\n\n")
                        if len(reference) != 4:
                            raise ValueError("fictional reference shape changed")
                        page.locator("#proposal-panel").evaluate("element => element.open = true")
                        invented = [reference[0], "Invented detail: the source reports a different assay preparation.",
                                    reference[2], reference[3]]
                        page.locator("#proposal-input").fill("\n\n".join(invented))
                        page.locator("#run-proposal").click()
                        page.wait_for_function("document.getElementById('workflow-reason').textContent.includes('PROPOSAL_REJECTED')")
                        require_ui_state("invented proposal", page.locator("#workflow-status").inner_text(), "NO AUTOMATIC CHANGE")
                        checked_states.append("invented-proposal")
                        page.locator("#workflow-status").scroll_into_view_if_needed()
                        _hold(page, by_id["invented-proposal"])

                        page.goto(docs_url + "judge/", wait_until="domcontentloaded")
                        page.locator("#run-audit").wait_for(state="visible")
                        page.wait_for_function("!document.getElementById('run-audit').disabled")
                        page.locator("#run-audit").click()
                        require_ui_state("Judge public replay", page.locator("#workflow-action").inner_text(), "ABSTAIN")
                        require_ui_state("Judge static scope", page.locator("#result-status").inner_text(), "Static replay")
                        checked_states.append("judge-public")
                        page.locator("#workflow-action").scroll_into_view_if_needed()
                        _hold(page, by_id["judge-public"])
                        page.locator("#scenario").select_option("fictional-omission")
                        page.locator("#run-audit").click()
                        require_ui_state("Judge fictional control", page.locator("#source-type").inner_text(), "FICTIONAL CONTROL")
                        require_ui_state("Judge fictional gate", page.locator("#workflow-action").inner_text(), "ABSTAIN")
                        checked_states.append("judge-fictional")
                        page.locator("#workflow-action").scroll_into_view_if_needed()
                        _hold(page, by_id["judge-fictional"])

                        page.goto(docs_url + "study/", wait_until="domcontentloaded")
                        page.locator("#start").wait_for(state="visible")
                        require_ui_state("study disclosure", page.locator("#intro").inner_text(), "no participants")
                        _hold(page, by_id["study"])

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
