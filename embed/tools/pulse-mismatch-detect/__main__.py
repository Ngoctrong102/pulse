#!/usr/bin/env python3
"""Toolkit A — read-only mismatch detect (thin wrapper)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_pulse_home = Path(__file__).resolve().parents[2]
_project = _pulse_home.parent if _pulse_home.name == ".pulse" else Path(os.environ.get("PULSE_ROOT") or _pulse_home).resolve()
if _pulse_home.name != ".pulse":
    _pulse_home = _project / ".pulse"
os.environ["PULSE_HOME"] = str(_pulse_home)
os.environ["PULSE_ROOT"] = str(_project)
sys.path.insert(0, str(_pulse_home / "tools"))
ROOT = _project

from pulse_lib import StatusError  # noqa: E402
from pulse_lib.mismatch import detect, write_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="pulse-mismatch-detect")
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ["PULSE_HOME"]) / "mismatch-report.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Write full findings list (default: top-N truncated on disk)",
    )
    args = parser.parse_args()
    try:
        _findings, report = detect(args.registry)
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_report(report, args.out, verbose=bool(args.verbose))
    print(f"Wrote {args.out} and {args.out.with_suffix('.md')}")
    print(
        f"Summary: critical={report['summary']['critical']} "
        f"warning={report['summary']['warning']} info={report['summary']['info']}"
        + (" (full)" if args.verbose else " (truncated on disk)")
    )
    return 1 if report["summary"]["critical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
