"""Safe mismatch heal — downgrade false-done cards from a detect report."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from pulse_lib import (
    DEFAULT_REGISTRY,
    StatusError,
    generate_views,
    load_registry,
    save_registry,
)
from pulse_lib.paths import PROJECT_ROOT


def plan_patches(report: dict[str, Any], data: dict[str, Any]) -> list[tuple[str, str]]:
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


def apply_patches(report: dict[str, Any], data: dict[str, Any]) -> int:
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


def run_heal(
    *,
    from_report: Path,
    apply: bool,
    dry_run: bool,
    registry: Path | None = None,
) -> int:
    """CLI-facing heal. Returns process exit code."""
    import json
    import sys

    if not from_report.is_file():
        print(f"Report not found: {from_report}", file=sys.stderr)
        return 2
    report = json.loads(from_report.read_text(encoding="utf-8"))
    try:
        data = load_registry(registry)
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    planned = plan_patches(report, data)
    if dry_run or not apply:
        if not planned:
            print("No safe critical patches to apply.")
            return 0
        print("Dry-run patch plan:")
        for fid, desc in planned:
            print(f"  - {fid}: {desc}")
        return 0

    changed = apply_patches(report, data)
    if changed:
        data["updated"] = date.today().isoformat()
        save_registry(data, registry)
        if registry is None or Path(registry).resolve() == DEFAULT_REGISTRY.resolve():
            generate_views(data)
            try:
                from pulse_lib.plugin import PulseApp, load_plugins, run_generate_hooks

                app = PulseApp(root=PROJECT_ROOT)
                load_plugins(app)
                run_generate_hooks(app, data)
            except Exception as exc:  # noqa: BLE001
                print(f"pulse: generate hooks warning: {exc}", file=sys.stderr)
        print(f"Applied {changed} patch(es); regenerated views.")
    else:
        print("Nothing to apply.")
    return 0
