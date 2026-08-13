"""Canonical paths for a pulse workspace.

Layout (only thing pulse owns inside a host project)::

    <project>/
      .pulse/                 # PULSE_HOME — commit-friendly project OS workspace
        features/             # cards SoT + _meta.yaml
        cleancode/
        tools/                # engine + CLI
        plugins/              # host plugins
        bin/pulse             # entry script
        cursor/               # optional agent rule templates (not auto-linked)
        BOARD.md, DRIFT.md, …

Product code stays wherever the user already keeps it; ``code_roots`` in
``_meta.yaml`` are relative to the **project root** (parent of ``.pulse``).
"""

from __future__ import annotations

import os
from pathlib import Path


def _is_pulse_home(path: Path) -> bool:
    return path.is_dir() and path.name == ".pulse" and (path / "features").exists()


def discover_pulse_home(start: Path | None = None) -> Path:
    """Return ``.pulse`` directory.

    Order: ``PULSE_HOME`` env → walk from cwd for ``.pulse/`` → vendored
    ``.../.pulse/tools/pulse_lib`` layout.
    """
    env = os.environ.get("PULSE_HOME")
    if env:
        return Path(env).expanduser().resolve()

    here = Path(__file__).resolve()
    # .../.pulse/tools/pulse_lib/<file>
    if len(here.parents) >= 3 and here.parents[2].name == ".pulse":
        return here.parents[2]

    cursor = (start or Path.cwd()).resolve()
    for cand in (cursor, *cursor.parents):
        pulse = cand / ".pulse"
        if pulse.is_dir() and (
            (pulse / "features").is_dir() or (pulse / "tools").is_dir()
        ):
            return pulse

    # Fallback: treat parents[2] as pulse home when running from tools/
    if len(here.parents) >= 2:
        return here.parents[2]
    return cursor / ".pulse"


def discover_project_root(pulse_home: Path | None = None) -> Path:
    """Host project root = parent of ``.pulse`` (or ``PULSE_ROOT`` / ``PULSE_PROJECT``)."""
    env = os.environ.get("PULSE_ROOT") or os.environ.get("PULSE_PROJECT")
    if env:
        return Path(env).expanduser().resolve()
    home = pulse_home or discover_pulse_home()
    if home.name == ".pulse":
        return home.parent
    return home


# Resolved at import time for the running CLI process.
PULSE_HOME = discover_pulse_home()
PROJECT_ROOT = discover_project_root(PULSE_HOME)

# Back-compat alias: many modules used REPO_ROOT for *project* root (code_roots).
REPO_ROOT = PROJECT_ROOT

FEATURES_DIR = PULSE_HOME / "features"
META_PATH = FEATURES_DIR / "_meta.yaml"
DEFAULT_REGISTRY = FEATURES_DIR
BOARD_PATH = PULSE_HOME / "BOARD.md"
ID_INDEX_PATH = PULSE_HOME / "id-index.md"
DRIFT_MD_PATH = PULSE_HOME / "DRIFT.md"
DRIFT_JSON_PATH = PULSE_HOME / "docs-drift-report.json"
MISMATCH_REPORT = PULSE_HOME / "mismatch-report.json"
PHASES_PATH = PULSE_HOME / "implementation-phases.md"
TECHDEBT_PATH = PULSE_HOME / "tech-debt.md"
CLEANCODE_DIR = PULSE_HOME / "cleancode"
CLEANCODE_VIEW = PULSE_HOME / "clean-code.md"
PLUGINS_DIR = PULSE_HOME / "plugins"
BIN_PULSE = PULSE_HOME / "bin" / "pulse"
