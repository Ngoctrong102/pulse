#!/usr/bin/env python3
"""Toolkit B — heal features.yaml from a detect report only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import os
_pulse_home = Path(__file__).resolve().parents[2]
_project = _pulse_home.parent if _pulse_home.name == ".pulse" else Path(os.environ.get("PULSE_ROOT") or _pulse_home).resolve()
if _pulse_home.name != ".pulse":
    _pulse_home = _project / ".pulse"
os.environ["PULSE_HOME"] = str(_pulse_home)
os.environ["PULSE_ROOT"] = str(_project)
sys.path.insert(0, str(_pulse_home / "tools"))
ROOT = _project

from pulse_lib import (  # noqa: E402
    StatusError,
    generate_views,
    load_registry,
    save_registry,
)


def plan_patches(report: dict, data: dict) -> list[tuple[str, str]]:
    """Return list of (feature_id, description) planned edits."""
    planned: list[tuple[str, str]] = []
    by_id = {f.get("id"): f for f in data.get("features") or [] if isinstance(f, dict)}
    for finding in report.get("findings") or []:
        if finding.get("severity") != "critical":
            continue
        if finding.get("code") != "docs_claims_done_but_missing_code":
            continue
        fid = finding.get("feature_id")
        feat = by_id.get(fid)
        if not feat:
            continue
        planned.append((fid, "downgrade done→partial; append remaining note from finding"))
    return planned


def apply_patches(report: dict, data: dict) -> int:
    by_id = {f.get("id"): f for f in data.get("features") or [] if isinstance(f, dict)}
    changed = 0
    for finding in report.get("findings") or []:
        if finding.get("severity") != "critical":
            continue
        if finding.get("code") != "docs_claims_done_but_missing_code":
            continue
        fid = finding.get("feature_id")
        feat = by_id.get(fid)
        if not feat:
            continue
        if feat.get("status") == "done":
            feat["status"] = "partial"
            if isinstance(feat.get("percent"), int) and feat["percent"] == 100:
                feat["percent"] = 90
            rem = list(feat.get("remaining") or [])
            note = finding.get("message") or "detect: evidence missing"
            if note not in rem:
                rem.append(note)
            feat["remaining"] = rem
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(prog="pulse-mismatch-heal")
    parser.add_argument("--from-report", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args()

    if not args.from_report.is_file():
        print(f"Report not found: {args.from_report}", file=sys.stderr)
        return 2
    report = json.loads(args.from_report.read_text(encoding="utf-8"))
    try:
        data = load_registry(args.registry)
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    planned = plan_patches(report, data)
    if args.dry_run:
        if not planned:
            print("No safe critical patches to apply.")
            return 0
        print("Dry-run patch plan:")
        for fid, desc in planned:
            print(f"  - {fid}: {desc}")
        return 0

    changed = apply_patches(report, data)
    if changed:
        data["updated"] = __import__("datetime").date.today().isoformat()
        save_registry(data, args.registry)
        # Only regenerate committed views when healing the live registry
        from pulse_lib import DEFAULT_REGISTRY

        if args.registry is None or Path(args.registry).resolve() == DEFAULT_REGISTRY.resolve():
            generate_views(data)
            try:
                from pulse_lib.plugin import PulseApp, load_plugins, run_generate_hooks
                app = PulseApp(root=ROOT)
                load_plugins(app)
                run_generate_hooks(app, data)
            except Exception as exc:  # noqa: BLE001
                print(f"pulse: generate hooks warning: {exc}", file=sys.stderr)
        print(f"Applied {changed} patch(es); regenerated views.")
    else:
        print("Nothing to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
