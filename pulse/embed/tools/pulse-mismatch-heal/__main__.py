#!/usr/bin/env python3
"""Toolkit B — heal features from a detect report (shim → pulse_lib.mismatch_heal)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_pulse_home = Path(__file__).resolve().parents[2]
_project = (
    _pulse_home.parent
    if _pulse_home.name == ".pulse"
    else Path(os.environ.get("PULSE_ROOT") or _pulse_home).resolve()
)
if _pulse_home.name != ".pulse":
    _pulse_home = _project / ".pulse"
os.environ["PULSE_HOME"] = str(_pulse_home)
os.environ["PULSE_ROOT"] = str(_project)
sys.path.insert(0, str(_pulse_home / "tools"))

from pulse_lib.mismatch_heal import run_heal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="pulse-mismatch-heal")
    parser.add_argument("--from-report", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args()
    return run_heal(
        from_report=args.from_report,
        apply=bool(args.apply),
        dry_run=bool(args.dry_run),
        registry=args.registry,
    )


if __name__ == "__main__":
    raise SystemExit(main())
