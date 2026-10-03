"""The release watch page and text must describe the video actually published."""
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_watch_page_links_latest_code_and_live_app_video():
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert "/releases/latest" in page
    assert "/releases/download/v0.3.8/biosure-demo-v038.mp4" in page
    assert "live app capture" in page.lower()
    assert "two controls and two genuine text-layer errors" in page
    assert "public-scorecard.md" in page
    assert "python -m pip install -e ." in page
    assert "Learned correspondence" in page
    assert "PDF text-layer" in page
    assert "two-source ooc pdf audit" in page.lower()
    assert "Three-source cross-publisher PDF audit" in page
    assert "page-specific review hints" in page
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == "0.3.9"
    assert "pypdf[fonts]==6.19.0" in project["dependencies"]
    assert "fonttools==4.66.1" in project["dependencies"]


def test_handoff_discloses_video_scope_and_article_credit():
    report = (ROOT / "report/public-submission.md").read_text(encoding="utf-8")
    readme = (ROOT / "report/public-readme.md").read_text(encoding="utf-8")
    rights = (ROOT / "report/public-rights.md").read_text(encoding="utf-8")
    storyboard = (ROOT / "video/storyboard.md").read_text(encoding="utf-8")
    assert "releases/latest" in report
    assert "former 2/2 review count inherited the diff flag" in report
    assert "verify_native_source.py" in readme
    assert "under five minutes" in report
    assert "learned review and the PDF warning" in readme
    assert "10.1038/s41467-025-65317-7" in rights
    assert "CC BY 4.0" in rights
    assert "under five minutes" in storyboard
    assert "biosure-demo-v038.mp4" in storyboard
    assert "three-source" in report[report.index("The verifier checks"):].lower()
