"""Mismatch detect logic (Toolkit A) — shared by CLI script + pulse plugin."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pulse_lib import (
    Finding,
    REPO_ROOT,
    StatusError,
    build_id_catalog,
    load_registry,
    validate_registry,
)
from pulse_lib.tag_audit import (
    audit_evidence_paths_missing_tags,
    audit_orphan_code_tags,
)

# Default on-disk report size (full list only with verbose=True).
REPORT_FINDINGS_LIMIT = 40
_SEV_RANK = {"critical": 0, "warning": 1, "info": 2}


def _path_exists(repo: Path, rel: str) -> bool:
    return (repo / rel).exists()


def detect(registry_path: Path | None = None) -> tuple[list[Finding], dict[str, Any]]:
    data = load_registry(registry_path)
    errors = validate_registry(data)
    findings: list[Finding] = []
    for err in errors:
        findings.append(Finding("critical", "percent_status_incoherent", err))

    for feat in data.get("features") or []:
        fid = feat.get("id")
        status = feat.get("status")
        evidence = feat.get("evidence") or {}
        paths_any = evidence.get("paths_any") or []
        paths_missing = evidence.get("paths_missing_means_todo") or []

        if status == "done":
            if paths_any and not any(_path_exists(REPO_ROOT, p) for p in paths_any):
                findings.append(
                    Finding(
                        "critical",
                        "docs_claims_done_but_missing_code",
                        f"{fid} is done but none of paths_any exist",
                        feature_id=fid,
                        evidence=list(paths_any),
                    )
                )
            if not paths_any and not (evidence.get("pytest") or []):
                findings.append(
                    Finding(
                        "warning",
                        "docs_claims_done_but_missing_code",
                        f"{fid} is done but evidence.paths_any is empty",
                        feature_id=fid,
                    )
                )

        for miss in paths_missing:
            if not _path_exists(REPO_ROOT, miss) and status == "done":
                findings.append(
                    Finding(
                        "critical",
                        "docs_claims_done_but_missing_code",
                        f"{fid} done but required path missing: {miss}",
                        feature_id=fid,
                        evidence=[miss],
                    )
                )

        percent = feat.get("percent")
        if status == "partial" and isinstance(percent, int) and percent in (0, 100):
            findings.append(
                Finding(
                    "warning",
                    "percent_status_incoherent",
                    f"{fid} partial with percent={percent}",
                    feature_id=fid,
                )
            )

    catalog, warnings = build_id_catalog()
    for w in warnings:
        if "missing frontmatter" in w:
            findings.append(Finding("info", "missing_frontmatter_warning", w))
        else:
            findings.append(Finding("warning", "catalog_id_unresolved", w))

    findings.extend(audit_orphan_code_tags(catalog))
    evidence_findings, _rows = audit_evidence_paths_missing_tags(
        list(data.get("features") or [])
    )
    findings.extend(evidence_findings)

    report = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry": str(registry_path) if registry_path else ".pulse/features",
        "summary": {
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "warning": sum(1 for f in findings if f.severity == "warning"),
            "info": sum(1 for f in findings if f.severity == "info"),
            "total": len(findings),
        },
        "findings": [f.as_dict() for f in findings],
    }
    return findings, report


def _sort_finding_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda f: (
            _SEV_RANK.get(str(f.get("severity") or "info"), 9),
            str(f.get("feature_id") or ""),
            str(f.get("code") or ""),
        ),
    )


def truncate_report(
    report: dict[str, Any], *, limit: int = REPORT_FINDINGS_LIMIT
) -> dict[str, Any]:
    """Return a copy with findings capped (critical/warning first)."""
    findings = list(report.get("findings") or [])
    if not isinstance(findings, list):
        findings = []
    ordered = _sort_finding_dicts([f for f in findings if isinstance(f, dict)])
    total = len(ordered)
    capped = ordered if limit <= 0 or total <= limit else ordered[:limit]
    out = dict(report)
    summary = dict(out.get("summary") or {})
    summary["total"] = int(summary.get("total") or total)
    out["summary"] = summary
    out["findings"] = capped
    out["truncated"] = total > len(capped)
    out["findings_total"] = total
    out["findings_shown"] = len(capped)
    return out


def write_report(
    report: dict[str, Any],
    out: Path,
    *,
    verbose: bool = False,
    limit: int = REPORT_FINDINGS_LIMIT,
) -> None:
    """Write JSON + MD. Default truncates findings; ``verbose`` keeps full list."""
    payload = report if verbose else truncate_report(report, limit=limit)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = out.with_suffix(".md")
    summary = payload.get("summary") or {}
    lines = [
        "# Mismatch report",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        f"Critical: **{summary.get('critical', 0)}** · "
        f"Warning: {summary.get('warning', 0)} · Info: {summary.get('info', 0)}"
        + (
            f" · shown {payload.get('findings_shown')}/{payload.get('findings_total')} "
            "(truncated — re-run with `--verbose` for full list)"
            if payload.get("truncated")
            else ""
        ),
        "",
        "| Sev | Code | Feature/ID | Message |",
        "|---|---|---|---|",
    ]
    for f in payload.get("findings") or []:
        if not isinstance(f, dict):
            continue
        lines.append(
            f"| {f.get('severity')} | `{f.get('code')}` | "
            f"{f.get('feature_id') or f.get('req_id') or ''} | {f.get('message')} |"
        )
    lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
