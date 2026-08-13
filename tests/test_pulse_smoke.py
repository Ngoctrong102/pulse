"""Smoke tests for pulse (.pulse/ workspace)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def demo(tmp_path: Path):
    root = tmp_path / "Demo"
    root.mkdir()
    env = {**os.environ, "PYTHONPATH": str(KIT)}
    subprocess.check_call(
        [sys.executable, "-m", "pulse", "init", "--force", "--no-venv", "--no-generate", "--no-extension"],
        env=env,
        cwd=str(root),
    )
    assert not (root / "tools").exists()
    assert not (root / "docs").exists()
    assert not (root / ".cursor").exists()
    assert (root / ".pulse" / "bin" / "pulse").is_file()
    return root



def _pulse(demo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PULSE_ROOT": str(demo),
        "PULSE_HOME": str(demo / ".pulse"),
        "PYTHONPATH": str(demo / ".pulse" / "tools"),
    }
    return subprocess.run(
        [sys.executable, str(demo / ".pulse" / "tools" / "pulse-cli" / "__main__.py"), *args],
        cwd=str(demo),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_plugins_load(demo: Path):
    r = _pulse(demo, "plugins", "--json")
    assert r.returncode == 0, r.stderr
    assert "drift" in r.stdout and "mismatch" in r.stdout


def test_generate_and_validate(demo: Path):
    r = _pulse(demo, "generate")
    assert r.returncode == 0, r.stderr
    assert (demo / ".pulse" / "BOARD.md").is_file()
    assert (demo / ".pulse" / "DRIFT.md").is_file()
    r2 = _pulse(demo, "validate")
    assert r2.returncode == 0, r2.stderr


def test_tag_prefix_from_meta(demo: Path):
    env = {
        **os.environ,
        "PULSE_ROOT": str(demo),
        "PULSE_HOME": str(demo / ".pulse"),
        "PYTHONPATH": str(demo / ".pulse" / "tools"),
    }
    code = (
        "from pulse_lib.tag_audit import tag_marker; "
        "print(tag_marker())"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(demo),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert r.stdout.splitlines()[0] == "DEMO:"


def test_mismatch_detect(demo: Path):
    r = _pulse(demo, "mismatch", "detect")
    assert r.returncode in (0, 1), r.stderr
    assert (demo / ".pulse" / "mismatch-report.json").is_file()


def test_hello_host_plugin(demo: Path):
    r = _pulse(demo, "hello", "--name", "test")
    assert r.returncode == 0, r.stderr
    assert "hello, test" in r.stdout


def test_speckit_disabled_by_default(demo: Path):
    env = {
        **os.environ,
        "PULSE_ROOT": str(demo),
        "PULSE_HOME": str(demo / ".pulse"),
        "PYTHONPATH": str(demo / ".pulse" / "tools"),
    }
    code = "from pulse_lib.next_actions import _speckit_enabled; print(_speckit_enabled())"
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(demo),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert r.stdout.strip() == "False"


def test_explain_without_speckit_jargon(demo: Path):
    r = _pulse(demo, "explain")
    assert r.returncode == 0, r.stderr
    assert "Spec Kit (optional brownfield)" not in r.stdout
    assert "Spec Kit disabled" in r.stdout or "Implementation style" in r.stdout


def test_init_does_not_write_gitignore(demo: Path):
    assert not (demo / ".gitignore").exists()
