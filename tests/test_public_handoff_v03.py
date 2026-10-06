"""The release watch page and text must describe the video actually published."""
from pathlib import Path
import tomllib
from scripts.audit_release import _allowed


ROOT = Path(__file__).resolve().parents[1]


def test_watch_page_links_latest_code_and_live_app_video():
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert "/releases/latest" in page
    assert "/releases/download/v0.3.22/biosure-demo-v0322.mp4" in page
    assert "actual pasted-text" in page.lower()
    assert "live browser trial" in page.lower()
    assert "no correction is automatically applied" in page.lower()
    assert "two controls and two genuine text-layer errors" in page
    assert "public-scorecard.md" in page
    assert "python -m pip install -e ." in page
    assert "Learned correspondence" in page
    assert "PDF text-layer" in page
    assert "two-source ooc pdf audit" in page.lower()
    assert "Three-source cross-publisher PDF audit" in page
    assert "page-specific review hints" in page
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == "0.3.22"
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
    assert "silent captioned demonstration (under three minutes)" in report
    assert "expand each changed paragraph" in readme
    assert "10.1038/s41467-025-65317-7" in rights
    assert "CC BY 4.0" in rights
    assert "runs under three minutes" in storyboard
    assert "| Time |" not in storyboard
    assert "biosure-demo-v0322.mp4" in storyboard
    assert "three-source" in report[report.index("The verifier checks"):].lower()


def test_current_demo_is_primary_and_old_capture_is_historical():
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    report = (ROOT / "report/public-submission.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    storyboard = (ROOT / "video/storyboard.md").read_text(encoding="utf-8")
    current = "/releases/download/v0.3.22/biosure-demo-v0322.mp4"
    assert f'<video controls preload="metadata" aria-label="BioSURE captioned demonstration" src="https://github.com/HyunStudio/BioSURE-AI4S{current}"' in page
    assert current in report and current in readme
    assert "v0.3.14" in storyboard and "PMC12864593" in storyboard
    assert "14/16" in page and "16/16" in page
    assert "v0.3.8" in page.lower() and "historical" in page.lower()


def test_latest_package_explains_older_demo_and_new_followup():
    page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    report = (ROOT / "report/public-submission.md").read_text(encoding="utf-8")
    assert "v0.3.22" in page and "v0.3.22" in report
    assert "v0.3.19" in page and "v0.3.19" in report
    assert "v0.3.21" in report
    assert "v0.3.14 video" in page
    assert "followup-ooc-audit-protocol.md" in report


def test_judge_mode_is_publicly_linked_and_release_allowlisted():
    url = "https://hyunstudio.github.io/BioSURE-AI4S/judge/"
    for filename in ("docs/index.html", "README.md", "report/public-readme.md", "report/public-submission.md"):
        assert url in (ROOT / filename).read_text(encoding="utf-8")
    for filename in ("docs/judge/index.html", "docs/judge/app.js", "docs/judge/style.css",
                     "docs/judge/data.json", "tests/test_judge_mode.js"):
        assert _allowed(filename), filename


def test_study_instrument_is_linked_but_not_called_a_completed_study():
    url = "https://hyunstudio.github.io/BioSURE-AI4S/study/"
    for filename in ("docs/index.html", "README.md", "report/public-readme.md", "report/public-submission.md"):
        assert url in (ROOT / filename).read_text(encoding="utf-8")
    for filename in ("docs/study/index.html", "docs/study/app.js", "docs/study/style.css",
                     "docs/study/manifest.json", "tests/test_study_runner.js"):
        assert _allowed(filename), filename
    assert not _allowed("results/biosure-study-session.json")
    assert not _allowed("results/participant-01.json")
    report = (ROOT / "report/public-submission.md").read_text(encoding="utf-8")
    assert "no participants" in report.lower()
    summary = report.split("## Project summary\n", 1)[1].split("## Technical report", 1)[0]
    assert 200 <= len(summary.split()) <= 300


def test_owner_analysis_instructions_are_release_allowlisted():
    assert _allowed("OWNER-ACTION-FIRST-PLACE.md")
    assert (ROOT / "OWNER-ACTION-FIRST-PLACE.md").is_file()


def test_owner_checklist_points_to_current_released_video_not_historical_preview():
    owner = (ROOT / "OWNER-ACTION-FIRST-PLACE.md").read_text(encoding="utf-8")
    production = (ROOT / "video/production.md").read_text(encoding="utf-8")
    preview = (ROOT / "video/current-preview.md").read_text(encoding="utf-8")
    current = "/releases/download/v0.3.22/biosure-demo-v0322.mp4"
    assert current in owner
    assert current in production
    assert "current video shows v0.3.14" not in owner.lower()
    assert "historical local preview" in preview.lower()


def test_solo_submission_does_not_require_recruitment_and_discloses_ai_assistance():
    owner = (ROOT / "OWNER-ACTION-FIRST-PLACE.md").read_text(encoding="utf-8")
    report = (ROOT / "report/public-submission.md").read_text(encoding="utf-8")
    assert "optional exploratory" in owner.lower()
    assert "slots 0, 1 and 2" in owner
    assert "not a submission prerequisite" in owner.lower()
    assert "invite at least six" not in owner.lower()
    assert "AI systems are tools, not team members or independent validators" in report
