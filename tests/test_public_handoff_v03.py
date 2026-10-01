"""The release watch page and text must describe the video actually published."""
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_v031_watch_page_links_new_code_and_retained_honest_video():
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert "/releases/tag/v0.3.1" in page
    assert "/releases/download/v0.3.0/biosure-demo.mp4" in page
    assert "public-scorecard.md" in page
    assert "python -m pip install -e ." in page
    assert "Learned correspondence" in page
    assert "PDF text-layer" in page
    assert tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == "0.3.1"


def test_v031_handoff_discloses_video_scope_and_article_credit():
    report = (ROOT / "report/public-submission.md").read_text(encoding="utf-8")
    readme = (ROOT / "report/public-readme.md").read_text(encoding="utf-8")
    rights = (ROOT / "report/public-rights.md").read_text(encoding="utf-8")
    storyboard = (ROOT / "video/storyboard.md").read_text(encoding="utf-8")
    assert "v0.3.1 release" in report
    assert "4 minutes 48 seconds" in report
    assert "learned review and PDF warning" in readme
    assert "10.1038/s41467-025-65317-7" in rights
    assert "CC BY 4.0" in rights
    assert "4 minutes 48 seconds" in storyboard
