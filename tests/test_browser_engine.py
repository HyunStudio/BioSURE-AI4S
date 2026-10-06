"""The browser runs exactly the packaged public Python text engine."""

import json
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("__init__.py", "schema.py", "gate.py", "receipts.py", "workflow.py",
           "ml_review.py", "learned_upstream.py")


def source_tree(tmp_path):
    for name in MODULES:
        path = tmp_path / "biosure" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "biosure" / name, path)
    model = tmp_path / "fixtures" / "ml_model.json"
    model.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "fixtures" / "ml_model.json", model)
    return tmp_path


def test_browser_engine_build_is_repeatable_and_detects_stale_source(tmp_path):
    build = importlib.import_module("scripts.build_browser_engine").build
    root = source_tree(tmp_path)
    build(root)
    first = (root / "docs/try/engine.zip").read_bytes()
    assert (root / "docs/try/model.json").read_bytes() == (root / "fixtures/ml_model.json").read_bytes()
    build(root)
    assert (root / "docs/try/engine.zip").read_bytes() == first
    build(root, check=True)
    path = root / "biosure/workflow.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        build(root, check=True)


def test_packaged_engine_runs_review_only_without_source_authority(tmp_path):
    build = importlib.import_module("scripts.build_browser_engine").build
    root = source_tree(tmp_path)
    build(root)
    archive = root / "docs/try/engine.zip"
    code = """
import json, sys
sys.path.insert(0, sys.argv[1])
from biosure.workflow import run_workflow
result = run_workflow({"record_id":"browser-smoke", "reference_paragraphs":["first", "middle", "last"], "observed_paragraphs":["first", "last"]})
print(json.dumps({"action":result["decision"]["action"], "selected":result["selected_paragraphs"], "status":result["adapter_status"]}))
"""
    completed = subprocess.run([sys.executable, "-I", "-c", code, str(archive)],
                               cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout) == {
        "action": "ABSTAIN", "selected": None, "status": "CANDIDATE_PROPOSED"
    }
