from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from biosure.web_demo import make_server


def test_default_fixture_path_works_outside_package_working_directory(tmp_path):
    # Wrong cwd-relative defaults or a required --fixtures flag must fail this.
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    process = subprocess.Popen([sys.executable, "-m", "biosure.web_demo", "--port", "0"],
                               cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = queue.Queue()
    reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
    reader.start()
    try:
        line = lines.get(timeout=30)
        assert line.startswith("BioSURE demo: http://"), line
        url = line.strip().removeprefix("BioSURE demo: ")
        assert urlsplit(url).hostname == "127.0.0.1"
        assert urlsplit(url).port > 0
        with urllib.request.urlopen(url + "/api/examples/batch", timeout=4) as response:
            import json
            assert len(json.load(response)) == 6
    finally:
        process.terminate()
        process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
        reader.join(timeout=2)


def test_launch_missing_fixture_directory_is_actionable_error_not_server(tmp_path):
    result = subprocess.run([sys.executable, "-m", "biosure.web_demo", "--fixtures", str(tmp_path / "missing")],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "fixtures" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_launch_port_collision_is_actionable_error_without_traceback():
    server = make_server(ROOT / "fixtures", port=0)
    try:
        result = subprocess.run([sys.executable, "-m", "biosure.web_demo", "--fixtures", str(ROOT / "fixtures"),
                                 "--port", str(server.server_address[1])], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 2
        assert "--port" in result.stderr
        assert "Traceback" not in result.stderr
    finally:
        server.server_close()


@pytest.mark.parametrize("port", [-1, 65536])
def test_launch_out_of_range_port_is_rejected_without_traceback(port):
    result = subprocess.run([sys.executable, "-m", "biosure.web_demo", "--port", str(port)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "--port" in result.stderr
    assert "Traceback" not in result.stderr
