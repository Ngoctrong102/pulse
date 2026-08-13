"""Regression: _meta.yaml keys survive set / new / generate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


def _load_meta(demo: Path) -> dict:
    path = demo / ".pulse" / "features" / "_meta.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _assert_core_meta(meta: dict) -> None:
    assert meta.get("project") == "Demo"
    assert meta.get("tag_prefix") == "DEMO"
    assert "code_roots" not in meta
    assert meta.get("speckit") is False
    assert "plugins" in meta
    assert isinstance(meta["plugins"], dict)


def test_meta_survives_set_focus_and_feature(demo: Path):
    r = _pulse(demo, "set", "--focus", "getting-started")
    assert r.returncode == 0, r.stderr
    meta = _load_meta(demo)
    _assert_core_meta(meta)
    assert meta.get("focus_id") == "getting-started"

    r2 = _pulse(
        demo,
        "set",
        "--feature",
        "getting-started",
        "--status",
        "partial",
        "--percent",
        "20",
        "--add-remaining",
        "keep meta",
    )
    assert r2.returncode == 0, r2.stderr
    meta2 = _load_meta(demo)
    _assert_core_meta(meta2)
    assert meta2.get("focus_id") == "getting-started"


def test_meta_survives_new_and_generate(demo: Path):
    r = _pulse(
        demo,
        "new",
        "--id",
        "extra-card",
        "--name",
        "Extra",
        "--type",
        "feature",
    )
    assert r.returncode == 0, r.stderr
    meta = _load_meta(demo)
    _assert_core_meta(meta)

    r2 = _pulse(demo, "generate")
    assert r2.returncode == 0, r2.stderr
    meta2 = _load_meta(demo)
    _assert_core_meta(meta2)
