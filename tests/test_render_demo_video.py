"""The optional demo recorder must fail closed on false claims and output paths."""

from __future__ import annotations

import copy
import importlib
import json
import os
import sys
from pathlib import Path

import pytest


def test_capture_module_imports_without_optional_video_dependencies(monkeypatch):
    original_import = __import__

    def block_optional(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"playwright", "imageio_ffmpeg"}:
            raise ImportError("optional package intentionally blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", block_optional)
    sys.modules.pop("scripts.render_demo_video", None)
    module = importlib.import_module("scripts.render_demo_video")
    assert callable(module.render)


def test_output_path_rejects_existing_source_internal_and_non_mp4(tmp_path):
    from scripts.render_demo_video import validate_output

    source = tmp_path / "source"
    source.mkdir()
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"keep")
    with pytest.raises(ValueError, match="already exists"):
        validate_output(existing, source)
    assert existing.read_bytes() == b"keep"
    with pytest.raises(ValueError, match="outside the source"):
        validate_output(source / "video.mp4", source)
    with pytest.raises(ValueError, match=".mp4"):
        validate_output(tmp_path / "video.webm", source)
    with pytest.raises(ValueError, match="parent"):
        validate_output(tmp_path / "missing" / "video.mp4", source)
    assert validate_output(tmp_path / "new.mp4", source) == tmp_path / "new.mp4"


def test_policy_summary_requires_exact_contract_and_separate_exposure():
    from scripts.render_demo_video import parse_policy_summary

    valid = {"contract_checks": 5, "contract_passed": 5, "exposure_auto_repairs": 0}
    assert parse_policy_summary(json.dumps(valid)) == valid
    for invalid in ({**valid, "contract_passed": 6},
                    {**valid, "exposure_auto_repairs": 1},
                    {**valid, "safety_passed": 6},
                    {"contract_checks": True, "contract_passed": 5, "exposure_auto_repairs": 0}):
        with pytest.raises(ValueError, match="policy summary"):
            parse_policy_summary(json.dumps(invalid))
    with pytest.raises(ValueError, match="policy summary"):
        parse_policy_summary("not json")


def test_shot_validation_enforces_duration_and_disclosures():
    from scripts.render_demo_video import shot_manifest, validate_shots

    shots = shot_manifest()
    assert validate_shots(shots) <= 180
    assert {shot["id"] for shot in shots} >= {
        "public-abstain", "fictional-omission", "invented-proposal", "judge-public",
        "judge-fictional", "study", "policy"
    }
    by_id = {shot["id"]: shot for shot in shots}
    assert by_id["judge-public"]["seconds"] >= 8
    assert by_id["judge-fictional"]["seconds"] >= 8
    assert [shot["id"] for shot in shots].index("judge-public") < [shot["id"] for shot in shots].index("judge-fictional")
    missing = tuple(shot for shot in shots if shot["id"] != "policy")
    with pytest.raises(ValueError, match="policy"):
        validate_shots(missing)
    overlong = copy.deepcopy(shots)
    overlong[0]["seconds"] = 181
    with pytest.raises(ValueError, match="180"):
        validate_shots(overlong)
    deceptive = copy.deepcopy(shots)
    policy = next(shot for shot in deceptive if shot["id"] == "policy")
    policy["caption"] = "6/6 safe and authenticated"
    with pytest.raises(ValueError, match="boundary"):
        validate_shots(deceptive)
    generic = copy.deepcopy(shots)
    generic[0]["caption"] = "A tool checks text."
    with pytest.raises(ValueError, match="problem"):
        validate_shots(generic)


def test_evidence_cards_separate_policy_from_reproduction_and_close():
    from scripts.render_demo_video import evidence_card

    policy = {"contract_checks": 5, "contract_passed": 5, "exposure_auto_repairs": 0}
    audit = evidence_card("policy", policy)
    replay = evidence_card("replay", policy)
    close = evidence_card("outro", policy)
    assert "exposure_auto_repairs" in audit and "5" in audit and "0" in audit
    assert "verify_reproduction.py" in replay and "exposure_auto_repairs" not in replay
    assert "github.com/HyunStudio/BioSURE-AI4S" in close and "verify_reproduction.py" not in close


def test_ui_claim_guard_rejects_changed_action():
    from scripts.render_demo_video import require_ui_state

    require_ui_state("public case", "NO AUTOMATIC CHANGE", "NO AUTOMATIC CHANGE")
    with pytest.raises(ValueError, match="public case"):
        require_ui_state("public case", "REFERENCE MATCH", "NO AUTOMATIC CHANGE")


def test_frame_fill_guard_rejects_large_gray_recording_padding():
    from scripts.render_demo_video import frame_has_gray_padding

    width = height = 20
    dark = bytes((7, 22, 26)) * (width * height)
    assert frame_has_gray_padding(dark, width, height) is False
    padded = bytearray(dark)
    for y in range(height):
        for x in range(width):
            if x >= 12 or y >= 12:
                index = (y * width + x) * 3
                padded[index:index + 3] = bytes((128, 128, 128))
    assert frame_has_gray_padding(bytes(padded), width, height) is True


def test_render_refuses_existing_destination_before_browser_launch(tmp_path):
    from scripts.render_demo_video import render

    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "keep.mp4"
    destination.write_bytes(b"keep")
    with pytest.raises(ValueError, match="already exists"):
        render(source, destination)
    assert destination.read_bytes() == b"keep"


def test_render_refuses_a_different_source_tree_than_its_own_script(tmp_path):
    from scripts.render_demo_video import render

    source = tmp_path / "different-source"
    source.mkdir()
    with pytest.raises(ValueError, match="same source tree"):
        render(source, tmp_path / "new.mp4")


def test_publish_video_never_leaves_partial_or_overwrites_existing(tmp_path, monkeypatch):
    from scripts.render_demo_video import _publish_video

    source = tmp_path / "encoded.mp4"
    source.write_bytes(b"complete movie")
    destination = tmp_path / "demo.mp4"
    destination.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        _publish_video(source, destination)
    assert destination.read_bytes() == b"existing"

    destination.unlink()
    import shutil

    def fail_after_partial(readable, writable):
        writable.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copyfileobj", fail_after_partial)
    with pytest.raises(OSError, match="disk full"):
        _publish_video(source, destination)
    assert not destination.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["encoded.mp4"]


def test_publish_video_preserves_complete_bytes(tmp_path):
    from scripts.render_demo_video import _publish_video

    source = tmp_path / "encoded.mp4"
    source.write_bytes(b"complete movie")
    destination = tmp_path / "demo.mp4"
    _publish_video(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["demo.mp4", "encoded.mp4"]


@pytest.mark.skipif(os.environ.get("RUN_VIDEO_INTEGRATION") != "1", reason="optional local Chrome capture")
def test_render_records_actual_app_and_static_replay(tmp_path):
    from scripts.render_demo_video import render

    source = Path(__file__).resolve().parents[1]
    chrome = os.environ.get("BIOSURE_CHROME_EXECUTABLE")
    output = tmp_path / "demo.mp4"
    result = render(source, output, Path(chrome) if chrome else None)
    assert output.is_file() and output.stat().st_size > 100_000
    assert 0 < result["duration_seconds"] <= 180
    assert len(result["sha256"]) == 64
    assert result["policy_summary"] == {"contract_checks": 5, "contract_passed": 5,
                                        "exposure_auto_repairs": 0}
    assert result["checked_states"] == ["public-abstain", "fictional-omission",
                                        "invented-proposal", "judge-public", "judge-fictional"]
