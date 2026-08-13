"""Tests for pulse upgrade and packaged embed templates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def demo(tmp_path: Path):
    env = {**os.environ, "PYTHONPATH": str(KIT)}
    subprocess.check_call(
        [sys.executable, "-m", "pulse", "init", "--force", "--no-venv", "--no-generate", "--no-extension"],
        env=env,
        cwd=str(tmp_path),
    )
    return tmp_path



def test_pip_install_latest_busts_cache(monkeypatch):
    from pulse import __main__ as m

    calls: list[list[str]] = []

    def fake_call(argv, *args, **kwargs):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(m.subprocess, "call", fake_call)
    m._pip_install_latest()
    assert len(calls) == 1
    cmd = calls[0]
    assert "--force-reinstall" in cmd
    assert "--no-cache-dir" in cmd
    assert any(s.endswith("@main") for s in cmd if isinstance(s, str))
    from pulse.__main__ import EMBED_ROOT

    assert EMBED_ROOT.is_dir(), EMBED_ROOT
    assert (EMBED_ROOT / "tools" / "pulse_lib" / "__init__.py").is_file()
    assert (EMBED_ROOT / ".cursor" / "hooks.json").is_file()


def test_upgrade_refreshes_tools_preserves_cards(demo: Path):
    card = demo / ".pulse" / "features" / "getting-started.yaml"
    original = card.read_text(encoding="utf-8")
    card.write_text(original + "# host-note\n", encoding="utf-8")

    marker = demo / ".pulse" / "tools" / "pulse_lib" / "__init__.py"
    assert marker.is_file()
    marker.write_text("# corrupted by host\n", encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": str(KIT), "PULSE_NO_FETCH": "1"}
    subprocess.check_call(
        [sys.executable, "-m", "pulse", "upgrade", "--no-fetch"],
        env=env,
        cwd=str(demo),
    )

    restored = marker.read_text(encoding="utf-8")
    assert "corrupted by host" not in restored
    assert "Shared load/validate" in restored or "StatusError" in restored
    assert "# host-note" in card.read_text(encoding="utf-8")

    cfg = json.loads((demo / ".pulse" / "config.json").read_text(encoding="utf-8"))
    assert "pulse_version" in cfg
    assert "tag_prefix" not in cfg  # SoT stays in _meta.yaml


def test_cursor_hooks_merge_and_unlink(demo: Path):
    env = {**os.environ, "PYTHONPATH": str(KIT)}
    cursor = demo / ".cursor"
    cursor.mkdir()
    (cursor / "hooks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "stop": [{"command": "echo host-hook"}],
                },
            }
        ),
        encoding="utf-8",
    )
    subprocess.check_call(
        [sys.executable, "-m", "pulse", "cursor", "link", str(demo)],
        env=env,
        cwd=str(KIT),
    )
    merged = json.loads((cursor / "hooks.json").read_text(encoding="utf-8"))
    stop = merged["hooks"]["stop"]
    assert any(isinstance(e, dict) and e.get("command") == "echo host-hook" for e in stop)
    assert any(isinstance(e, dict) and e.get("pulse_id") == "pulse-status-sync" for e in stop)

    subprocess.check_call(
        [sys.executable, "-m", "pulse", "cursor", "unlink", str(demo)],
        env=env,
        cwd=str(KIT),
    )
    stripped = json.loads((cursor / "hooks.json").read_text(encoding="utf-8"))
    stop2 = stripped["hooks"]["stop"]
    assert all(not (isinstance(e, dict) and e.get("pulse_id") == "pulse-status-sync") for e in stop2)
    assert any(isinstance(e, dict) and e.get("command") == "echo host-hook" for e in stop2)


def test_github_copilot_link_and_unlink(demo: Path):
    env = {**os.environ, "PYTHONPATH": str(KIT)}
    assert (demo / ".pulse" / "github" / "copilot-instructions.md").is_file()

    gh = demo / ".github"
    gh.mkdir()
    (gh / "copilot-instructions.md").write_text("# Host notes\n\nKeep me.\n", encoding="utf-8")

    subprocess.check_call(
        [sys.executable, "-m", "pulse", "github", "link", str(demo)],
        env=env,
        cwd=str(KIT),
    )
    text = (gh / "copilot-instructions.md").read_text(encoding="utf-8")
    assert "Keep me." in text
    assert "<!-- pulse:begin -->" in text
    assert "Pulse — project operating system" in text
    assert (gh / "instructions" / "pulse-features.instructions.md").is_file()
    assert (gh / "pulse-quality-raise.md").is_file()

    subprocess.check_call(
        [sys.executable, "-m", "pulse", "copilot", "unlink", str(demo)],
        env=env,
        cwd=str(KIT),
    )
    leftover = (gh / "copilot-instructions.md").read_text(encoding="utf-8")
    assert "Keep me." in leftover
    assert "<!-- pulse:begin -->" not in leftover
    assert not (gh / "instructions" / "pulse-features.instructions.md").exists()
    assert not (gh / "pulse-quality-raise.md").exists()


def test_init_does_not_create_host_venv(tmp_path: Path):
    env = {**os.environ, "PYTHONPATH": str(KIT)}
    # Pretend a host project already has its own .venv — pulse must leave it alone.
    host_venv = tmp_path / ".venv" / "bin"
    host_venv.mkdir(parents=True)
    marker = host_venv / "python"
    marker.write_text("#!/bin/sh\necho host\n", encoding="utf-8")
    marker.chmod(0o755)

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pulse",
            "init",
            "--force",
            "--no-generate",
            "--no-extension",
            "--link",
            "none",
        ],
        env=env,
        cwd=str(tmp_path),
    )
    assert marker.read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert (tmp_path / ".pulse" / "bin" / "pulse").is_file()
    bin_text = (tmp_path / ".pulse" / "bin" / "pulse").read_text(encoding="utf-8")
    assert "PROJECT_ROOT}/.venv" not in bin_text
    assert "PULSE_HOME}/venv" not in bin_text
    assert "pulse/venv/bin/python" in bin_text


def test_init_link_both(tmp_path: Path):
    env = {**os.environ, "PYTHONPATH": str(KIT)}
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pulse",
            "init",
            "--force",
            "--no-generate",
            "--no-extension",
            "--link",
            "both",
        ],
        env=env,
        cwd=str(tmp_path),
    )
    assert (tmp_path / ".cursor" / "hooks.json").is_file()
    assert (tmp_path / ".github" / "copilot-instructions.md").is_file()


def test_init_prompt_cursor(monkeypatch, tmp_path: Path):
    from pulse.__main__ import init_project

    answers = iter(["c"])
    monkeypatch.setattr(sys, "stdin", sys.stdin)
    monkeypatch.setattr("pulse.__main__.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("pulse.__main__.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    init_project(tmp_path, force=True, generate=False, install_extension=False)
    assert (tmp_path / ".cursor" / "hooks.json").is_file()
    assert not (tmp_path / ".github").exists()
